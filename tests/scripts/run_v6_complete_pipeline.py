"""
V6 完整并行流程测试

步骤:
1. DOCX → Markdown
2. V6 并行标注 (10线程 + Qwen-Plus)
3. 字段分析
4. V6 并行内容生成 (10线程 + Qwen-Plus)
5. 应用内容到Markdown
6. Markdown → DOCX

记录所有中间结果
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict  # ✅ 新增类型导入

# 设置使用Qwen模型
os.environ['USE_QWEN_FOR_ANNOTATION'] = 'true'
os.environ['USE_FIREWORKS_FOR_ANNOTATION'] = 'false'
os.environ['GITCODE_MODEL'] = 'qwen-plus'
os.environ['USE_QWEN_FOR_GENERATION'] = 'true'
os.environ['GITCODE_GENERATION_MODEL'] = 'qwen-plus'

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from docuagent.v4.docx_markdown_converter import DocxMarkdownExporter
from docuagent.v6 import parallel_annotate, remove_segment_prefixes, parallel_generate_all_batches
from docuagent.v4.apply_annotations import apply_annotations_to_markdown
from docuagent.v4.markdown_to_docx import rebuild_docx_from_markdown
from docuagent.v4.content_generation.field_analyzer import FieldAnalyzer
from docuagent.v4.content_generation.workflow import group_fields_for_batch
from docuagent.v5.knowledge_base import KnowledgeBase  # ✅ 新增：知识库支持
# from docuagent.v4.content_generation.content_applier import apply_generated_content_to_markdown


def apply_generated_content_to_markdown(markdown_content: str, generated_content: Dict) -> str:
    """应用生成的内容到Markdown，替换占位符"""
    result = markdown_content
    for placeholder, generated_field in generated_content.items():
        # 替换占位符 {{placeholder}} 为生成的内容
        result = result.replace(f"{{{{{placeholder}}}}}", generated_field.content)
    return result


def main():
    """V6 完整并行流程"""

    print("="*80)
    print("V6 完整并行流程: 并行标注 + 并行生成 + DOCX输出")
    print("="*80)

    # 配置
    template_docx = Path(__file__).resolve().parents[2] / "教案模版（未标注）.docx"
    output_base = Path(__file__).parent / "results" / "v6_complete"
    output_base.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_base / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📁 输出目录: {output_dir}")
    print(f"📄 模板文件: {template_docx}")

    if not template_docx.exists():
        print(f"❌ 模板文件不存在: {template_docx}")
        return

    total_start = time.time()

    # ========================================
    # 步骤1: DOCX → Markdown
    # ========================================
    print("\n" + "="*80)
    print("步骤1: DOCX → Markdown 转换")
    print("="*80)

    step1_start = time.time()

    markdown_dir = output_dir / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)

    exporter = DocxMarkdownExporter(str(template_docx))
    markdown_content = exporter.export(str(markdown_dir))

    md_path = markdown_dir / f"{template_docx.stem}_v4.md"
    manifest_path = markdown_dir / f"{template_docx.stem}_v4_manifest.json"

    step1_time = time.time() - step1_start

    print(f"✅ Markdown导出成功")
    print(f"   输出文件: {md_path}")
    print(f"   清单文件: {manifest_path}")
    print(f"   耗时: {step1_time:.2f} 秒")

    # ========================================
    # 步骤2: V6 并行标注 (10线程)
    # ========================================
    print("\n" + "="*80)
    print("步骤2: V6 并行标注 (10线程 + Qwen-Plus)")
    print("="*80)

    step2_start = time.time()

    annotation_result = parallel_annotate(
        md_path=md_path,
        features_path=None,
        kb_insights=None,
        output_dir=output_dir / "annotation",
        max_concurrent=10,
        no_segment=False,
    )

    step2_time = time.time() - step2_start

    # 清理前缀
    annotation_result.combined_annotations = remove_segment_prefixes(
        annotation_result.combined_annotations
    )

    print(f"\n✅ 并行标注完成")
    print(f"   标注数: {len(annotation_result.combined_annotations)}")
    print(f"   耗时: {step2_time:.2f} 秒")

    # 保存标注JSON
    annotations_json_path = output_dir / f"annotations_{timestamp}.json"
    with open(annotations_json_path, 'w', encoding='utf-8') as f:
        json.dump({
            "annotations": annotation_result.combined_annotations,
            "stats": annotation_result.to_dict(),
        }, f, ensure_ascii=False, indent=2)

    print(f"   标注JSON: {annotations_json_path}")

    # ========================================
    # 步骤3: 应用标注到Markdown
    # ========================================
    print("\n" + "="*80)
    print("步骤3: 应用标注到Markdown")
    print("="*80)

    step3_start = time.time()

    annotated_md_path = output_dir / f"annotated_{timestamp}.md"
    apply_annotations_to_markdown(
        md_path=md_path,
        annotations_json_path=annotations_json_path,
        output_md_path=annotated_md_path
    )

    step3_time = time.time() - step3_start

    print(f"✅ 标注已应用")
    print(f"   输出: {annotated_md_path}")
    print(f"   耗时: {step3_time:.2f} 秒")

    # ========================================
    # 步骤4: 字段分析
    # ========================================
    print("\n" + "="*80)
    print("步骤4: 字段分析")
    print("="*80)

    step4_start = time.time()

    analyzer = FieldAnalyzer()
    field_analyses = analyzer.analyze_all_fields(
        annotation_result.combined_annotations,
        context_map=None,  # 可选：上下文映射
    )

    # 组织字段批次（考虑依赖关系）
    field_batches = group_fields_for_batch(field_analyses, batch_size=10)

    step4_time = time.time() - step4_start

    print(f"✅ 字段分析完成")
    print(f"   总字段数: {len(field_analyses)}")
    print(f"   分批数: {len(field_batches)}")
    for i, batch in enumerate(field_batches, 1):
        print(f"   批次 {i}: {len(batch)} 个字段")
    print(f"   耗时: {step4_time:.2f} 秒")

    # 保存字段分析
    field_analysis_path = output_dir / f"field_analysis_{timestamp}.json"
    with open(field_analysis_path, 'w', encoding='utf-8') as f:
        json.dump({
            "total_fields": len(field_analyses),
            "batches": len(field_batches),
            "fields": [fa.__dict__ for fa in field_analyses],
        }, f, ensure_ascii=False, indent=2)

    print(f"   字段分析JSON: {field_analysis_path}")

    # ========================================
    # 步骤5: V6 并行内容生成 (10线程 + 知识库)
    # ========================================
    print("\n" + "="*80)
    print("步骤5: V6 并行内容生成 (10线程 + Qwen-Plus + 知识库)")
    print("="*80)

    step5_start = time.time()

    # ✅ 加载知识库洞察
    print("\n📚 加载知识库洞察...")
    kb = KnowledgeBase.for_doc_type("lesson_plan")
    kb_insights = kb.format_for_generator_prompt(max_entries=30, min_severity="low")
    kb_stats = kb.get_stats()
    print(f"   知识库条目: {kb_stats.get('total_entries', 0)}")
    print(f"   使用条目: {min(30, kb_stats.get('total_entries', 0))}")

    # 准备用户输入（示例数据）
    user_input = {
        "course_name": "人工智能基础",
        "teacher_name": "张三",
        "grade": "大学本科三年级",
        "semester": "2024-2025学年第一学期",
        "class_hours": "2学时",
        "class_type": "理论课",
        "teaching_content": "介绍神经网络的基本原理和应用",
        "teaching_objectives": "1. 理解神经网络的基本概念\n2. 掌握反向传播算法\n3. 能够实现简单的神经网络",
        "teaching_difficulties": "反向传播算法的数学推导",
        "teaching_methods": "讲授法、演示法、实验法",
        "teaching_aids": "PPT、Python代码演示",
    }

    # 并行生成所有批次（✅ 使用知识库洞察）
    generation_result = parallel_generate_all_batches(
        field_batches=field_batches,
        user_input=user_input,
        kb_insights=kb_insights,  # ✅ 传递知识库洞察
        doc_type="lesson_plan",
        output_dir=output_dir / "generation",
        max_concurrent=10,
    )

    step5_time = time.time() - step5_start

    print(f"\n✅ 并行生成完成")
    print(f"   生成字段数: {len(generation_result.generated_content)}")
    print(f"   失败字段数: {len(generation_result.failures)}")
    print(f"   耗时: {step5_time:.2f} 秒")

    # 保存生成内容
    generated_content_path = output_dir / f"generated_content_{timestamp}.json"
    with open(generated_content_path, 'w', encoding='utf-8') as f:
        json.dump({
            "generated_content": {
                k: v.__dict__ for k, v in generation_result.generated_content.items()
            },
            "stats": generation_result.to_dict(),
        }, f, ensure_ascii=False, indent=2)

    print(f"   生成内容JSON: {generated_content_path}")

    # ========================================
    # 步骤6: 应用生成内容到Markdown
    # ========================================
    print("\n" + "="*80)
    print("步骤6: 应用生成内容到Markdown")
    print("="*80)

    step6_start = time.time()

    final_md_path = output_dir / f"final_{timestamp}.md"
    annotated_md_content = annotated_md_path.read_text(encoding='utf-8')

    # 应用生成的内容
    final_md_content = apply_generated_content_to_markdown(
        annotated_md_content,
        generation_result.generated_content
    )

    final_md_path.write_text(final_md_content, encoding='utf-8')

    step6_time = time.time() - step6_start

    print(f"✅ 内容已应用")
    print(f"   输出: {final_md_path}")
    print(f"   耗时: {step6_time:.2f} 秒")

    # ========================================
    # 步骤7: Markdown → DOCX
    # ========================================
    print("\n" + "="*80)
    print("步骤7: Markdown → DOCX 转换")
    print("="*80)

    step7_start = time.time()

    final_docx_path = output_dir / f"教案_V6完整流程_{timestamp}.docx"

    rebuild_docx_from_markdown(
        markdown_path=final_md_path,
        manifest_path=manifest_path,
        output_docx_path=final_docx_path,
        base_docx_path=template_docx,
    )

    step7_time = time.time() - step7_start

    print(f"✅ DOCX生成成功")
    print(f"   输出: {final_docx_path}")
    print(f"   耗时: {step7_time:.2f} 秒")

    # ========================================
    # 总结
    # ========================================
    total_time = time.time() - total_start

    print("\n" + "="*80)
    print("✅ V6 完整流程完成！")
    print("="*80)

    print(f"\n📊 时间统计:")
    print(f"   步骤1 (DOCX→MD):       {step1_time:>8.2f} 秒")
    print(f"   步骤2 (并行标注):      {step2_time:>8.2f} 秒")
    print(f"   步骤3 (应用标注):      {step3_time:>8.2f} 秒")
    print(f"   步骤4 (字段分析):      {step4_time:>8.2f} 秒")
    print(f"   步骤5 (并行生成):      {step5_time:>8.2f} 秒")
    print(f"   步骤6 (应用内容):      {step6_time:>8.2f} 秒")
    print(f"   步骤7 (MD→DOCX):       {step7_time:>8.2f} 秒")
    print(f"   {'─'*35}")
    print(f"   总耗时:               {total_time:>8.2f} 秒 ({total_time/60:.1f} 分钟)")

    print(f"\n📈 处理统计:")
    print(f"   标注数: {len(annotation_result.combined_annotations)}")
    print(f"   字段数: {len(field_analyses)}")
    print(f"   成功生成: {len(generation_result.generated_content)}")
    print(f"   失败生成: {len(generation_result.failures)}")

    print(f"\n🚀 性能提升:")
    ann_stats = annotation_result.to_dict()
    gen_stats = generation_result.to_dict()
    print(f"   标注加速比: {ann_stats.get('speedup_ratio', 1.0):.2f}x")
    print(f"   生成加速比: {gen_stats.get('speedup_ratio', 1.0):.2f}x")

    print(f"\n📁 输出文件:")
    print(f"   工作目录: {output_dir}")
    print(f"   最终DOCX: {final_docx_path}")
    print(f"   标注JSON: {annotations_json_path}")
    print(f"   字段分析: {field_analysis_path}")
    print(f"   生成内容: {generated_content_path}")

    # 保存流程摘要
    summary_path = output_dir / f"pipeline_summary_{timestamp}.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump({
            "template": template_docx.name,
            "timestamp": timestamp,
            "steps": {
                "step1_docx_to_md": {"time": step1_time, "status": "success"},
                "step2_parallel_annotation": {
                    "time": step2_time,
                    "status": "success",
                    "annotations": len(annotation_result.combined_annotations),
                    "speedup": ann_stats.get('speedup_ratio', 1.0),
                },
                "step3_apply_annotations": {"time": step3_time, "status": "success"},
                "step4_field_analysis": {
                    "time": step4_time,
                    "status": "success",
                    "fields": len(field_analyses),
                    "batches": len(field_batches),
                },
                "step5_parallel_generation": {
                    "time": step5_time,
                    "status": "success",
                    "generated": len(generation_result.generated_content),
                    "failed": len(generation_result.failures),
                    "speedup": gen_stats.get('speedup_ratio', 1.0),
                },
                "step6_apply_content": {"time": step6_time, "status": "success"},
                "step7_md_to_docx": {"time": step7_time, "status": "success"},
            },
            "total_time_seconds": total_time,
            "configuration": {
                "max_concurrent_annotation": 10,
                "max_concurrent_generation": 10,
                "model": "qwen-plus",
            },
            "output_files": {
                "final_docx": str(final_docx_path),
                "annotations_json": str(annotations_json_path),
                "field_analysis": str(field_analysis_path),
                "generated_content": str(generated_content_path),
            }
        }, f, ensure_ascii=False, indent=2)

    print(f"   流程摘要: {summary_path}")

    print("\n" + "="*80)


if __name__ == "__main__":
    main()
