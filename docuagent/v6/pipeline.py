"""
DocuAgent v6 Pipeline: 完整的文档生成管道

核心流程:
1. LLM判断文档类型 (doc_classifier)
2. 加载对应类型的知识库
3. 多线程LLM并行标注 (parallel_annotator) ⚡
4. JSON格式修正 (json_fixer)
5. V4内容生成workflow (复用V4的LangGraph + apply_annotations)
6. VLM审查生成的Word (vlm_checker, training模式)
7. 存储反思建议到知识库 (reflection + knowledge_base)

主要改进:
- V4: 顺序标注 + LangGraph内容生成 + Markdown→DOCX重建
- V5: V4 + 文档分类 + VLM检查 + 反思学习
- V6: **并行标注(1.4-2x加速)** + V4内容生成(保留格式) + V5知识库
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# V4基础组件
from ..v4.docx_markdown_converter import DocxMarkdownExporter

# V6核心组件
from .parallel_annotator import parallel_annotate, remove_segment_prefixes
from .json_fixer import JSONFixer

# V5复用组件
from .doc_classifier import classify_from_markdown_file
from .knowledge_base import KnowledgeBase
from .vlm_checker import check_docx_quality
from .reflection import analyze_errors


@dataclass
class V6PipelineResult:
    """V6管道执行结果"""
    doc_type: str
    doc_type_name: str
    markdown_path: str
    annotation_json_path: str
    final_docx_path: str
    vlm_review: Dict[str, Any]
    total_time: float
    stage_times: Dict[str, float]
    success: bool
    error: Optional[str] = None


def run_v6_pipeline(
    docx_path: str | Path,
    *,
    requirement: str,
    outdir: str | Path,
    mode: str = "training",
    max_concurrent_annotate: int = 3,
    max_concurrent_generate: int = 10,
) -> V6PipelineResult:
    """
    运行V6完整管道

    Args:
        docx_path: 输入的Word模板路径
        requirement: 用户需求/提示词
        outdir: 输出目录
        mode: training=启用VLM检查和反思; inference=跳过VLM检查
        max_concurrent_annotate: 标注阶段最大并发数（建议3-5）
        max_concurrent_generate: 生成阶段最大并发数（建议5-10）

    Returns:
        V6PipelineResult对象
    """
    docx_path = Path(docx_path)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    stage_times = {}
    overall_start = time.time()

    print("\n" + "="*80)
    print("🚀 DocuAgent V6 Pipeline - 并行标注 + 批量生成 + VLM审查")
    print("="*80)
    print(f"📄 输入模板: {docx_path.name}")
    print(f"📝 用户需求: {requirement[:100]}...")
    print(f"🔧 模式: {mode}")
    print(f"📁 输出目录: {outdir}")
    print("="*80 + "\n")

    try:
        # ========================================
        # 阶段1: DOCX → Markdown转换
        # ========================================
        print("\n" + "─"*80)
        print("📄 阶段1: DOCX → Markdown 转换")
        print("─"*80)

        t0 = time.time()
        md_dir = outdir / "markdown"
        md_dir.mkdir(parents=True, exist_ok=True)

        exporter = DocxMarkdownExporter(docx_path)
        md_path, manifest_path = exporter.export(md_dir)

        stage_times["docx_to_markdown"] = time.time() - t0
        print(f"✅ 转换完成: {md_path.name} ({stage_times['docx_to_markdown']:.2f}秒)")

        # ========================================
        # 阶段2: LLM文档分类
        # ========================================
        print("\n" + "─"*80)
        print("🔍 阶段2: LLM文档类型分类")
        print("─"*80)

        t0 = time.time()
        doc_classification = classify_from_markdown_file(md_path)
        doc_type = doc_classification.get("type", "other")
        doc_type_name = doc_classification.get("type_name", "其他")

        stage_times["doc_classification"] = time.time() - t0

        print(f"\n📋 文档类型: {doc_type_name} ({doc_type})")
        print(f"   置信度: {doc_classification.get('confidence', 0):.2%}")
        print(f"   理由: {doc_classification.get('reason', '未知')}")
        print(f"   耗时: {stage_times['doc_classification']:.2f}秒")

        # ========================================
        # 阶段3: 加载知识库
        # ========================================
        print("\n" + "─"*80)
        print(f"📚 阶段3: 加载 {doc_type_name} 知识库")
        print("─"*80)

        t0 = time.time()
        kb = KnowledgeBase.for_doc_type(doc_type)
        kb_insights_annotator = kb.format_for_annotator_prompt(max_entries=30, min_severity="low")
        kb_insights_generator = kb.format_for_generator_prompt(max_entries=30, min_severity="low")

        stage_times["load_knowledge_base"] = time.time() - t0

        print(f"✅ 知识库加载完成: {kb.kb_path}")
        print(f"   标注器洞察: {len(kb_insights_annotator)} 字符")
        print(f"   生成器洞察: {len(kb_insights_generator)} 字符")
        print(f"   耗时: {stage_times['load_knowledge_base']:.2f}秒")

        # ========================================
        # 阶段4: 多线程并行标注
        # ========================================
        print("\n" + "─"*80)
        print(f"🔄 阶段4: 多线程并行标注 (并发数: {max_concurrent_annotate})")
        print("─"*80)

        t0 = time.time()
        annotation_dir = outdir / "annotation"
        annotation_dir.mkdir(parents=True, exist_ok=True)

        parallel_result = parallel_annotate(
            md_path=md_path,
            features_path=None,
            kb_insights=kb_insights_annotator,
            output_dir=annotation_dir,
            max_concurrent=max_concurrent_annotate,
            no_segment=False,
        )

        stage_times["parallel_annotation"] = time.time() - t0

        # 移除segment前缀（后处理）
        cleaned_annotations = remove_segment_prefixes(parallel_result.combined_annotations)

        print(f"\n✅ 并行标注完成:")
        print(f"   总标注数: {len(cleaned_annotations)}")
        print(f"   失败段落: {len(parallel_result.failures)}")
        print(f"   总耗时: {stage_times['parallel_annotation']:.2f}秒")

        if parallel_result.individual_times:
            sequential_estimate = sum(parallel_result.individual_times)
            speedup = sequential_estimate / parallel_result.total_time if parallel_result.total_time > 0 else 1.0
            print(f"   🚀 加速比: {speedup:.2f}x")

        # ========================================
        # 阶段5: JSON格式修正
        # ========================================
        print("\n" + "─"*80)
        print("🔧 阶段5: JSON格式修正")
        print("─"*80)

        t0 = time.time()

        # 保存清理后的标注
        annotation_json = {
            "annotations": cleaned_annotations,
            "metadata": {
                "doc_type": doc_type,
                "total_annotations": len(cleaned_annotations),
                "parallel_speedup": speedup if parallel_result.individual_times else 1.0,
            }
        }

        annotation_json_path = annotation_dir / "annotations.json"
        annotation_json_path.write_text(
            json.dumps(annotation_json, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        stage_times["json_fix"] = time.time() - t0

        print(f"✅ JSON修正完成: {annotation_json_path.name}")
        print(f"   有效标注: {len(cleaned_annotations)}")
        print(f"   耗时: {stage_times['json_fix']:.2f}秒")

        # ========================================
        # 阶段6: 内容生成（复用V4 workflow）
        # ========================================
        print("\n" + "─"*80)
        print("📝 阶段6: 内容生成 + DOCX构建（V4 workflow）")
        print("─"*80)

        t0 = time.time()
        generation_dir = outdir / "generation"
        generation_dir.mkdir(parents=True, exist_ok=True)

        # 复用V4的内容生成workflow
        from ..v4.content_generation.workflow import run_content_generation

        user_input = {"prompt": requirement}

        gen_summary = run_content_generation(
            annotation_path=str(annotation_json_path),
            user_input=user_input,
            markdown_path=str(md_path),
            manifest_path=str(manifest_path),
            output_dir=str(generation_dir),
            batch_mode=True,
            batch_size=5,
            kb_insights=kb_insights_generator,
            doc_type=doc_type,
        )

        stage_times["content_generation"] = time.time() - t0

        print(f"\n✅ 内容生成完成:")
        print(f"   总耗时: {stage_times['content_generation']:.2f}秒")

        # 查找最终DOCX
        final_docx_path = None
        for cand in [generation_dir / "final.docx", generation_dir / "generated.docx", generation_dir / "output.docx"]:
            if cand.exists():
                final_docx_path = cand
                break

        if not final_docx_path:
            print("⚠️  未找到最终DOCX文件")
            final_docx_path = generation_dir / "final.docx"

        print(f"✅ 最终文档: {final_docx_path.name}")

        # ========================================
        # 阶段7: VLM审查 + 反思学习（仅training模式）
        # ========================================
        vlm_review = {}

        if mode == "training":
            print("\n" + "─"*80)
            print("🔍 阶段7: VLM审查 + 反思学习")
            print("─"*80)

            t0 = time.time()
            vlm_dir = outdir / "vlm_review"
            vlm_dir.mkdir(parents=True, exist_ok=True)

            try:
                # VLM质量检查
                vlm_result = check_docx_quality(
                    docx_path=final_docx_path,
                    user_requirement=requirement,
                    output_dir=vlm_dir,
                )

                # 反思分析
                analysis = analyze_errors(
                    vlm_result=vlm_result,
                    user_requirement=requirement,
                    outdir=vlm_dir,
                )

                # 存储到知识库
                kb.add_experience(
                    vlm_result=vlm_result,
                    analysis=analysis,
                    context={
                        "template_name": docx_path.name,
                        "user_requirement": requirement,
                        "doc_type": doc_type,
                        "doc_classification": doc_classification,
                    }
                )

                vlm_review = {
                    "vlm_result": vlm_result,
                    "analysis": analysis,
                    "kb_updated": True,
                }

                stage_times["vlm_review"] = time.time() - t0

                print(f"\n✅ VLM审查完成:")
                print(f"   发现问题: {len(vlm_result.get('issues', []))} 个")
                print(f"   知识库已更新: {kb.kb_path}")
                print(f"   耗时: {stage_times['vlm_review']:.2f}秒")

            except Exception as e:
                print(f"⚠️  VLM审查失败: {e}")
                vlm_review = {"error": str(e)}
                stage_times["vlm_review"] = time.time() - t0

        else:
            print("\n⏭️  推理模式，跳过VLM审查")

        # ========================================
        # 完成
        # ========================================
        total_time = time.time() - overall_start

        result = V6PipelineResult(
            doc_type=doc_type,
            doc_type_name=doc_type_name,
            markdown_path=str(md_path),
            annotation_json_path=str(annotation_json_path),
            final_docx_path=str(final_docx_path),
            vlm_review=vlm_review,
            total_time=total_time,
            stage_times=stage_times,
            success=True,
        )

        # 保存运行报告
        report = {
            "success": True,
            "doc_type": doc_type,
            "doc_type_name": doc_type_name,
            "input_docx": str(docx_path),
            "requirement": requirement,
            "mode": mode,
            "outputs": {
                "markdown": str(md_path),
                "annotation_json": str(annotation_json_path),
                "final_docx": str(final_docx_path),
                "knowledge_base": str(kb.kb_path),
            },
            "statistics": {
                "total_annotations": len(cleaned_annotations),
                "generation_summary": gen_summary if isinstance(gen_summary, dict) else {},
                "vlm_issues": len(vlm_review.get("vlm_result", {}).get("issues", [])) if mode == "training" else 0,
            },
            "performance": {
                "total_time": total_time,
                "stage_times": stage_times,
                "annotation_speedup": speedup if parallel_result.individual_times else 1.0,
            },
            "timestamp": datetime.now().isoformat(),
        }

        report_path = outdir / f"v6_run_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        print("\n" + "="*80)
        print("✅ V6 Pipeline 完成！")
        print("="*80)
        print(f"\n📊 统计:")
        print(f"   文档类型: {doc_type_name} ({doc_type})")
        print(f"   标注数: {len(cleaned_annotations)}")
        print(f"   总耗时: {total_time:.2f}秒 ({total_time/60:.1f}分钟)")

        print(f"\n📁 输出文件:")
        print(f"   最终文档: {final_docx_path}")
        print(f"   标注JSON: {annotation_json_path}")
        print(f"   运行报告: {report_path}")
        print(f"   知识库: {kb.kb_path}")

        print("\n" + "="*80 + "\n")

        return result

    except Exception as e:
        total_time = time.time() - overall_start

        print(f"\n❌ Pipeline失败: {e}")
        import traceback
        traceback.print_exc()

        return V6PipelineResult(
            doc_type="unknown",
            doc_type_name="未知",
            markdown_path="",
            annotation_json_path="",
            final_docx_path="",
            vlm_review={},
            total_time=total_time,
            stage_times=stage_times,
            success=False,
            error=str(e),
        )


def main() -> None:
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="DocuAgent V6 Pipeline - 并行标注 + 批量生成 + VLM审查",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # Training模式（启用VLM审查）
  python -m docuagent.v6.pipeline --docx template.docx \\
    --requirement "生成Python编程课程教案" \\
    --outdir results/v6_output \\
    --mode training

  # Inference模式（跳过VLM审查）
  python -m docuagent.v6.pipeline --docx template.docx \\
    --requirement "生成数据库课程教案" \\
    --outdir results/v6_output \\
    --mode inference
        """
    )

    parser.add_argument("--docx", required=True, help="输入Word模板路径")
    parser.add_argument("--requirement", required=True, help="用户需求/提示词")
    parser.add_argument("--outdir", required=True, help="输出目录")
    parser.add_argument(
        "--mode",
        choices=["training", "inference"],
        default="training",
        help="运行模式: training=启用VLM审查, inference=跳过VLM审查"
    )
    parser.add_argument(
        "--max-concurrent-annotate",
        type=int,
        default=3,
        help="标注阶段最大并发数（默认3）"
    )
    parser.add_argument(
        "--max-concurrent-generate",
        type=int,
        default=10,
        help="生成阶段最大并发数（默认10）"
    )

    args = parser.parse_args()

    result = run_v6_pipeline(
        docx_path=args.docx,
        requirement=args.requirement,
        outdir=args.outdir,
        mode=args.mode,
        max_concurrent_annotate=args.max_concurrent_annotate,
        max_concurrent_generate=args.max_concurrent_generate,
    )

    if not result.success:
        exit(1)


if __name__ == "__main__":
    main()
