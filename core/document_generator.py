"""
文档生成服务 - Document Generation Service
整合V6 pipeline的核心功能，提供统一的文档生成API

功能特性:
1. 自动文档类型分类 (LLM classification)
2. 知识库加载与历史经验注入
3. 多线程并行模板标注 (1.4-2x加速)
4. V4内容生成workflow (保留格式)
5. VLM质量检查 (可选, training模式)
6. 反思学习与知识库存储

使用方式:
    from core.document_generator import DocumentGenerator

    generator = DocumentGenerator()
    result = generator.generate(
        template_path="template.docx",
        user_requirement="生成Python课程教案",
        mode="inference",  # 或 "training"
        output_dir="results/output"
    )
    print(f"生成完成: {result['final_docx']}")
"""

import os
import json
import time
import importlib
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from datetime import datetime

# 导入V4/V5/V6核心模块
from docuagent.v4.docx_markdown_converter import DocxMarkdownExporter
from docuagent.v6.parallel_annotator import parallel_annotate
from docuagent.v6.doc_classifier import classify_from_markdown_file
from docuagent.v6.knowledge_base import KnowledgeBase
from docuagent.v6.vlm_checker import check_docx_quality
from docuagent.v6.reflection import analyze_errors
from docuagent.v6.json_fixer import JSONFixer


class DocumentGenerationResult:
    """文档生成结果"""

    def __init__(self, success: bool, data: Dict):
        self.success = success
        self.doc_type = data.get("doc_type")
        self.doc_type_name = data.get("doc_type_name")
        self.final_docx = data.get("final_docx")
        self.annotation_json = data.get("annotation_json")
        self.markdown = data.get("markdown")
        self.statistics = data.get("statistics", {})
        self.performance = data.get("performance", {})
        self.error = data.get("error")

    def __repr__(self):
        if self.success:
            return f"<DocumentGenerationResult success={self.success} doc_type={self.doc_type} final_docx={self.final_docx}>"
        else:
            return f"<DocumentGenerationResult success={self.success} error={self.error}>"

    def to_dict(self):
        """转为字典格式"""
        return {
            "success": self.success,
            "doc_type": self.doc_type,
            "doc_type_name": self.doc_type_name,
            "final_docx": self.final_docx,
            "annotation_json": self.annotation_json,
            "markdown": self.markdown,
            "statistics": self.statistics,
            "performance": self.performance,
            "error": self.error,
        }


class DocumentGenerator:
    """
    文档生成器 - 统一的文档生成服务

    完整流程:
    1. DOCX → Markdown转换
    2. LLM文档类型分类
    3. 加载对应知识库
    4. 多线程并行标注 (V6)
    5. JSON格式修正
    6. V4内容生成workflow
    7. VLM质量检查 (training模式)
    8. 反思学习存储
    """

    DOC_TYPE_NAMES = {
        "lesson_plan": "教案",
        "task_proposal": "任务书",
        "thesis": "论文",
        "report": "报告",
        "other": "其他",
    }

    def __init__(
        self,
        max_concurrent_annotate: int = 3,
        max_concurrent_generate: int = 10,
        vlm_max_iterations: int = 3,
        vlm_quality_threshold: float = 0.7,
        enable_background_learning: bool = True,
        generation_backend: Optional[str] = "qwen",
        generation_model: Optional[str] = "qwen3-8b",
        generation_batch_size: int = 10,
    ):
        """
        初始化文档生成器

        Args:
            max_concurrent_annotate: 并行标注最大线程数
            max_concurrent_generate: 并行生成最大线程数
            vlm_max_iterations: VLM检查最大迭代次数
            vlm_quality_threshold: VLM质量阈值
            enable_background_learning: 是否启用后台学习（VLM评审+知识库更新）
        """
        self.max_concurrent_annotate = max_concurrent_annotate
        self.max_concurrent_generate = max_concurrent_generate
        self.vlm_max_iterations = vlm_max_iterations
        self.vlm_quality_threshold = vlm_quality_threshold
        self.enable_background_learning = enable_background_learning
        self.generation_backend = (generation_backend or os.environ.get("DOC_GEN_GENERATION_BACKEND"))
        self.generation_model = (generation_model or os.environ.get("DOC_GEN_GENERATION_MODEL"))
        self.generation_batch_size = generation_batch_size

    def _normalize_user_requirement(self, user_requirement: Any) -> Dict[str, Any]:
        """将用户需求统一转为workflow可接受的字典结构。"""
        if isinstance(user_requirement, dict):
            return user_requirement
        if isinstance(user_requirement, str):
            return {
                "prompt": user_requirement.strip(),
                "request": user_requirement.strip(),
            }
        return {
            "prompt": json.dumps(user_requirement, ensure_ascii=False),
        }

    def _guess_doc_type(self, template_path: Path, user_requirement: Any) -> Optional[str]:
        """根据模板文件名或需求文本猜测文档类型."""
        text_parts = [template_path.name]
        if isinstance(user_requirement, str):
            text_parts.append(user_requirement)
        elif isinstance(user_requirement, dict):
            try:
                text_parts.append(json.dumps(user_requirement, ensure_ascii=False))
            except Exception:
                pass
        text = " ".join(text_parts).lower()

        heuristics = {
            "lesson_plan": ["教案", "lesson", "教学设计"],
            "task_proposal": ["任务书", "proposal", "课题", "task"],
            "thesis": ["论文", "thesis"],
            "report": ["报告", "report"],
        }

        for doc_type, keywords in heuristics.items():
            if any(keyword.lower() in text for keyword in keywords):
                return doc_type
        return None

    def _prepare_generation_backend(self):
        """配置生成阶段所需的LLM后端环境变量。"""
        backend = (self.generation_backend or "").strip().lower()
        if backend == "fireworks":
            os.environ["USE_FIREWORKS_FOR_ANNOTATION"] = "true"
            os.environ["USE_QWEN_FOR_ANNOTATION"] = "false"
            if self.generation_model:
                os.environ["FIREWORKS_GENERATION_MODEL"] = self.generation_model
        elif backend == "packy":
            os.environ["USE_PACKY_FOR_ANNOTATION"] = "true"
            os.environ["USE_FIREWORKS_FOR_ANNOTATION"] = "false"
            os.environ["USE_QWEN_FOR_ANNOTATION"] = "false"
            if self.generation_model:
                os.environ["PACKY_GENERATION_MODEL"] = self.generation_model
        elif backend == "qwen":
            os.environ["USE_FIREWORKS_FOR_ANNOTATION"] = "false"
            os.environ["USE_PACKY_FOR_ANNOTATION"] = "false"
            os.environ["USE_QWEN_FOR_ANNOTATION"] = "true"
            if self.generation_model:
                os.environ["QWEN_GENERATION_MODEL"] = self.generation_model
        elif backend == "kimi":
            os.environ["USE_FIREWORKS_FOR_ANNOTATION"] = "false"
            os.environ["USE_PACKY_FOR_ANNOTATION"] = "false"
            os.environ["USE_QWEN_FOR_ANNOTATION"] = "false"
            if self.generation_model:
                os.environ["KIMI_GENERATION_MODEL"] = self.generation_model
        elif backend == "gpt":
            os.environ["USE_FIREWORKS_FOR_ANNOTATION"] = "false"
            os.environ["USE_PACKY_FOR_ANNOTATION"] = "false"
            os.environ["USE_QWEN_FOR_ANNOTATION"] = "false"
            os.environ["USE_GPT_FOR_ANNOTATION"] = "true"
            if self.generation_model:
                os.environ["GPT_GENERATION_MODEL"] = self.generation_model
        else:
            if self.generation_model:
                os.environ["GITCODE_GENERATION_MODEL"] = self.generation_model

    def _load_generation_workflow(self):
        """根据配置加载最新的内容生成workflow。"""
        self._prepare_generation_backend()

        llm_module = importlib.import_module("docuagent.v4.llm_annotator")
        content_module = importlib.import_module("docuagent.v4.content_generation.content_generator")
        workflow_module = importlib.import_module("docuagent.v4.content_generation.workflow")

        # 重新加载，使环境变量切换立即生效
        importlib.reload(llm_module)
        importlib.reload(content_module)
        workflow_module = importlib.reload(workflow_module)

        return workflow_module.run_content_generation

    def generate(
        self,
        template_path: str,
        user_requirement: str,
        mode: str = "inference",
        output_dir: Optional[str] = None,
        no_segment: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> DocumentGenerationResult:
        """
        生成文档主入口

        Args:
            template_path: 模板文档路径 (.docx)
            user_requirement: 用户需求描述
            mode: 运行模式 ("inference" 或 "training")
                  - inference: 跳过VLM检查，快速生成
                  - training: 执行VLM检查和反思学习
            output_dir: 输出目录 (可选，默认自动生成)
            no_segment: 是否禁用分段标注 (默认False)
            progress_callback: 进度回调函数 (可选)
                  - 签名: callback(stage: str, progress: int, message: str)
                  - stage: "markdown" | "classification" | "annotation" | "generation" | "vlm" | "reflection" | "completed"
                  - progress: 0-100 百分比
                  - message: 状态描述

        Returns:
            DocumentGenerationResult: 生成结果对象
        """
        template_path = Path(template_path)
        if not template_path.exists():
            return DocumentGenerationResult(
                success=False,
                data={"error": f"模板文件不存在: {template_path}"}
            )

        # 创建输出目录
        if output_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path(f"results/{template_path.stem}_{timestamp}")
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # 性能计时
        perf = {}
        total_start = time.time()

        # Helper function for progress callbacks
        def _report_progress(stage: str, progress: int, message: str):
            """报告进度（如果提供了回调函数）"""
            if progress_callback:
                try:
                    progress_callback(stage, progress, message)
                except Exception as e:
                    print(f"⚠️  进度回调失败: {e}")

        try:
            # ============================================================
            # 阶段1: DOCX → Markdown 转换
            # ============================================================
            print("\n" + "="*80)
            print("🚀 文档生成服务启动")
            print("="*80)
            print(f"📄 输入模板: {template_path.name}")
            print(f"📝 用户需求: {user_requirement}")
            print(f"🔧 运行模式: {mode}")
            print(f"📁 输出目录: {output_dir}")
            print("="*80 + "\n")

            _report_progress("markdown", 5, "开始DOCX→Markdown转换")

            print("─" * 80)
            print("📄 阶段1: DOCX → Markdown 转换")
            print("─" * 80)

            stage_start = time.time()

            markdown_dir = output_dir / "markdown"
            markdown_dir.mkdir(exist_ok=True)

            # 使用V4 DocxMarkdownExporter
            exporter = DocxMarkdownExporter(str(template_path))
            # ✅ 修复: exporter.export()期望目录路径，会自动生成文件名
            returned_md_path, returned_manifest_path = exporter.export(str(markdown_dir))

            md_path = Path(returned_md_path)
            manifest_path = Path(returned_manifest_path)

            perf["docx_to_markdown"] = time.time() - stage_start
            print(f"✅ 转换完成: {md_path.name} ({perf['docx_to_markdown']:.2f}秒)\n")

            _report_progress("markdown", 10, f"Markdown转换完成: {md_path.name}")

            # ============================================================
            # 阶段2: LLM文档类型分类
            # ============================================================
            _report_progress("classification", 15, "开始文档类型分类")

            print("─" * 80)
            print("🔍 阶段2: LLM文档类型分类")
            print("─" * 80)

            stage_start = time.time()

            classification = classify_from_markdown_file(md_path)
            doc_type = classification["type"]
            doc_type_name = self.DOC_TYPE_NAMES.get(doc_type, "未知类型")

            fallback_doc_type = None
            if doc_type == "other" and (classification.get("confidence", 0) == 0 or "分类失败" in classification.get("reason", "")):
                fallback_doc_type = self._guess_doc_type(template_path, user_requirement)
                if fallback_doc_type:
                    doc_type = fallback_doc_type
                    doc_type_name = self.DOC_TYPE_NAMES.get(doc_type, doc_type_name)
                    print(f"   ⚠️ 分类失败，使用启发式推断类型: {doc_type_name} ({doc_type})")

            perf["doc_classification"] = time.time() - stage_start

            print(f"📋 文档类型: {doc_type_name} ({doc_type})")
            print(f"   置信度: {classification['confidence']*100:.2f}%")
            print(f"   理由: {classification['reason']}")
            print(f"   耗时: {perf['doc_classification']:.2f}秒\n")

            _report_progress("classification", 20, f"文档分类完成: {doc_type_name}")

            # ============================================================
            # 阶段3: 加载对应知识库
            # ============================================================
            _report_progress("annotation", 25, f"加载{doc_type_name}知识库")

            print("─" * 80)
            print(f"📚 阶段3: 加载 {doc_type_name} 知识库")
            print("─" * 80)

            stage_start = time.time()

            kb = KnowledgeBase.for_doc_type(doc_type)
            kb_insights_annotator = kb.format_for_annotator_prompt(max_entries=30)
            kb_insights_generator = kb.format_for_generator_prompt(max_entries=30)

            perf["load_knowledge_base"] = time.time() - stage_start

            print(f"✅ 知识库加载完成: {kb.kb_path}")
            print(f"   标注器洞察: {len(kb_insights_annotator)} 字符")
            print(f"   生成器洞察: {len(kb_insights_generator)} 字符")
            if kb_insights_generator:
                print(f"   生成器洞察前100字符: {kb_insights_generator[:100]}")
            else:
                print(f"   ⚠️ 生成器洞察为空！")
            print(f"   耗时: {perf['load_knowledge_base']:.2f}秒\n")

            # ============================================================
            # 阶段4: 多线程并行标注
            # ============================================================
            _report_progress("annotation", 30, "开始并行标注模板")

            print("─" * 80)
            print(f"🔄 阶段4: 多线程并行标注 (并发数: {self.max_concurrent_annotate})")
            print("─" * 80)

            stage_start = time.time()

            annotation_dir = output_dir / "annotation"
            annotation_dir.mkdir(exist_ok=True)

            anno_result = parallel_annotate(
                md_path=md_path,
                kb_insights=kb_insights_annotator,
                output_dir=annotation_dir,
                max_concurrent=self.max_concurrent_annotate,
                no_segment=no_segment,
                doc_type=doc_type,
            )

            perf["parallel_annotation"] = time.time() - stage_start

            print(f"✅ 并行标注完成:")
            print(f"   总标注数: {len(anno_result.combined_annotations)}")
            print(f"   失败数量: {len(anno_result.failures)}")  # ✅ 修复: failures而不是failed_segments
            print(f"   总耗时: {perf['parallel_annotation']:.2f}秒")

            # ✅ 计算加速比（如果有性能数据）
            stats = anno_result.to_dict()
            if 'speedup_ratio' in stats:
                print(f"   🚀 加速比: {stats['speedup_ratio']:.2f}x\n")
            else:
                print()

            _report_progress("annotation", 50, f"标注完成: {len(anno_result.combined_annotations)}个字段")

            # ============================================================
            # 阶段5: JSON格式修正
            # ============================================================
            print("─" * 80)
            print("🔧 阶段5: JSON格式修正")
            print("─" * 80)

            stage_start = time.time()

            annotation_json_path = annotation_dir / "annotations.json"

            # 使用JSON Fixer修复标注格式
            fixer = JSONFixer()
            fixed_annotations = fixer.fix_annotations(anno_result.combined_annotations)

            # 保存修正后的标注
            with open(annotation_json_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "annotations": fixed_annotations,
                    "metadata": {
                        "doc_type": doc_type,
                        "total_annotations": len(fixed_annotations),
                        "parallel_speedup": stats.get("speedup_ratio"),
                    }
                }, f, ensure_ascii=False, indent=2)

            perf["json_fix"] = time.time() - stage_start

            print(f"✅ JSON修正完成: {annotation_json_path.name}")
            print(f"   有效标注: {len(fixed_annotations)}")
            print(f"   耗时: {perf['json_fix']:.2f}秒\n")

            # ============================================================
            # 阶段6: V4内容生成workflow
            # ============================================================
            _report_progress("generation", 55, "开始内容生成")

            print("─" * 80)
            print("📝 阶段6: 内容生成 + DOCX构建（V4 workflow）")
            print("─" * 80)

            stage_start = time.time()

            generation_dir = output_dir / "generation"
            generation_dir.mkdir(exist_ok=True)

            run_content_generation = self._load_generation_workflow()
            normalized_user_input = self._normalize_user_requirement(user_requirement)

            gen_summary = run_content_generation(
                annotation_path=str(annotation_json_path),
                user_input=normalized_user_input,
                markdown_path=str(md_path),
                manifest_path=str(manifest_path),
                output_dir=str(generation_dir),
                batch_mode=True,
                batch_size=self.generation_batch_size,
                kb_insights=kb_insights_generator,
                doc_type=doc_type,
            )

            perf["content_generation"] = time.time() - stage_start

            final_docx_path = generation_dir / "final.docx"

            print(f"✅ 内容生成完成:")
            print(f"   总耗时: {perf['content_generation']:.2f}秒")
            print(f"✅ 最终文档: {final_docx_path.name}\n")

            _report_progress("generation", 85, f"文档构建完成: {final_docx_path.name}")

            # ============================================================
            # 阶段7: VLM质量检查与后台学习
            # ============================================================
            vlm_issues = 0

            # 判断是否需要运行VLM检查
            # training模式：同步运行（阻塞）
            # inference模式 + 后台学习开启：异步运行（不阻塞）
            should_run_vlm_sync = (mode == "training")
            should_run_vlm_async = (mode == "inference" and self.enable_background_learning)

            if should_run_vlm_sync:
                _report_progress("vlm", 88, "开始VLM质量检查")

                print("─" * 80)
                print("👁️  阶段7: VLM质量检查")
                print("─" * 80)

                stage_start = time.time()

                # 使用VLM检查生成的DOCX质量
                vlm_result = check_docx_quality(
                    docx_path=str(final_docx_path),
                    annotation_json_path=str(annotation_json_path),
                )

                perf["vlm_check"] = time.time() - stage_start
                vlm_issues = vlm_result.get("total_issues", 0)

                print(f"✅ VLM检查完成:")
                print(f"   最终质量: {vlm_result.get('final_quality', 0):.2%}")
                print(f"   迭代次数: {vlm_result.get('iteration', 0)}")
                print(f"   发现问题: {vlm_issues} 个")
                print(f"   耗时: {perf['vlm_check']:.2f}秒\n")

                _report_progress("vlm", 92, f"VLM检查完成: 发现{vlm_issues}个问题")

                # ============================================================
                # 阶段8: 反思学习存储
                # ============================================================
                if vlm_issues > 0 and vlm_result.get("issues"):
                    _report_progress("reflection", 94, "开始反思学习分析")

                    print("─" * 80)
                    print("🧠 阶段8: 反思学习存储")
                    print("─" * 80)

                    stage_start = time.time()

                    reflection = analyze_errors(
                        issues=vlm_result["issues"],
                        doc_type=doc_type
                    )
                    kb.add_experience(reflection)

                    perf["reflection"] = time.time() - stage_start

                    print(f"✅ 反思存储完成:")
                    print(f"   标注器建议: {len(reflection.get('annotator_prompts', []))} 条")
                    print(f"   生成器建议: {len(reflection.get('generator_prompts', []))} 条")
                    print(f"   耗时: {perf['reflection']:.2f}秒\n")

                    _report_progress("reflection", 98, "反思学习完成")
            elif should_run_vlm_async:
                # ============================================================
                # 后台异步学习（不阻塞用户）
                # ============================================================
                print("─" * 80)
                print("🔄 启动后台学习线程（VLM评审 + 知识库更新）")
                print("─" * 80)
                print("⚡ 文档已生成完成，后台学习不影响返回速度")
                print("📚 系统将在后台分析质量并更新知识库\n")

                # 准备后台学习所需的参数
                background_params = {
                    'final_docx_path': str(final_docx_path),
                    'annotation_json_path': str(annotation_json_path),
                    'doc_type': doc_type,
                    'kb': kb,
                    'output_dir': output_dir,
                    'user_requirement': user_requirement,
                }

                # 启动后台线程
                import threading
                background_thread = threading.Thread(
                    target=self._background_learning_worker,
                    args=(background_params,),
                    daemon=True,  # 守护线程，主程序退出时自动结束
                    name=f"BackgroundLearning-{doc_type}"
                )
                background_thread.start()
                print(f"✅ 后台学习线程已启动: {background_thread.name}\n")
            else:
                print("⏭️  推理模式，跳过VLM审查\n")

            # ============================================================
            # 完成 - 生成报告
            # ============================================================
            total_time = time.time() - total_start
            perf["total_time"] = total_time

            _report_progress("completed", 100, f"生成完成: {final_docx_path.name}")

            print("="*80)
            print("✅ 文档生成完成！")
            print("="*80)
            print(f"\n📊 统计:")
            print(f"   文档类型: {doc_type_name} ({doc_type})")
            print(f"   标注数: {len(anno_result.combined_annotations)}")
            print(f"   生成字段: {gen_summary.get('completed_fields', 0)}/{gen_summary.get('total_fields', 0)}")
            print(f"   总耗时: {total_time:.2f}秒 ({total_time/60:.1f}分钟)")

            print(f"\n📁 输出文件:")
            print(f"   最终文档: {final_docx_path}")
            print(f"   标注JSON: {annotation_json_path}")
            print(f"   知识库: {kb.kb_path}")
            print("="*80 + "\n")

            # 保存运行报告
            report = {
                "success": True,
                "doc_type": doc_type,
                "doc_type_name": doc_type_name,
                "input_docx": str(template_path),
                "requirement": user_requirement,
                "mode": mode,
                "outputs": {
                    "markdown": str(md_path),
                    "annotation_json": str(annotation_json_path),
                    "final_docx": str(final_docx_path),
                    "knowledge_base": str(kb.kb_path),
                },
                "statistics": {
                    "total_annotations": len(anno_result.combined_annotations),
                    "generation_summary": gen_summary,
                    "vlm_issues": vlm_issues,
                },
                "performance": perf,
                "timestamp": datetime.now().isoformat(),
            }

            report_path = output_dir / f"generation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            return DocumentGenerationResult(success=True, data=report)

        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"

            print("\n" + "="*80)
            print("❌ 生成失败")
            print("="*80)
            print(f"错误: {error_msg}")
            print("="*80 + "\n")

            return DocumentGenerationResult(
                success=False,
                data={"error": error_msg}
            )

    def generate_batch(
        self,
        templates: list,
        requirements: list,
        mode: str = "inference",
        output_base_dir: Optional[str] = None,
    ) -> list:
        """
        批量生成文档

        Args:
            templates: 模板路径列表
            requirements: 需求描述列表 (与templates一一对应)
            mode: 运行模式
            output_base_dir: 输出基础目录

        Returns:
            list[DocumentGenerationResult]: 结果列表
        """
        if len(templates) != len(requirements):
            raise ValueError("模板数量与需求数量不匹配")

        results = []
        for i, (template, requirement) in enumerate(zip(templates, requirements)):
            print(f"\n{'='*80}")
            print(f"📦 批量生成 [{i+1}/{len(templates)}]")
            print(f"{'='*80}\n")

            if output_base_dir:
                output_dir = Path(output_base_dir) / f"batch_{i+1:03d}"
            else:
                output_dir = None

            result = self.generate(
                template_path=template,
                user_requirement=requirement,
                mode=mode,
                output_dir=output_dir,
            )
            results.append(result)

        return results

    def _background_learning_worker(self, params: dict):
        """
        后台学习worker（在独立线程中运行）

        Args:
            params: 包含以下键值的字典
                - final_docx_path: 最终生成的DOCX路径
                - annotation_json_path: 标注JSON路径
                - doc_type: 文档类型
                - kb: 知识库对象
                - output_dir: 输出目录
        """
        import time
        start_time = time.time()

        try:
            print(f"\n{'='*80}")
            print(f"🔬 后台学习任务开始")
            print(f"{'='*80}")
            print(f"📄 文档类型: {params['doc_type']}")
            print(f"📁 DOCX路径: {params['final_docx_path']}")
            print(f"⏰ 开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

            # ============================================================
            # 步骤1: VLM质量检查
            # ============================================================
            print("─" * 80)
            print("👁️  步骤1: VLM质量检查")
            print("─" * 80)

            vlm_start = time.time()
            vlm_result = check_docx_quality(
                docx_path=Path(params['final_docx_path']),
                user_requirement=str(params.get('user_requirement', '')),
                outdir=params.get('output_dir'),
            )
            vlm_time = time.time() - vlm_start
            vlm_issues = vlm_result.get("total_issues", 0)

            print(f"✅ VLM检查完成:")
            print(f"   最终质量: {vlm_result.get('final_quality', 0):.2%}")
            print(f"   迭代次数: {vlm_result.get('iteration', 0)}")
            print(f"   发现问题: {vlm_issues} 个")
            print(f"   耗时: {vlm_time:.2f}秒\n")

            # ============================================================
            # 步骤2: 反思学习与知识库更新
            # ============================================================
            if vlm_issues > 0 and vlm_result.get("issues"):
                print("─" * 80)
                print("🧠 步骤2: 反思学习与知识库更新")
                print("─" * 80)

                reflection_start = time.time()
                reflection = analyze_errors(
                    issues=vlm_result["issues"],
                    doc_type=params['doc_type']
                )
                params['kb'].add_experience(reflection)
                reflection_time = time.time() - reflection_start

                print(f"✅ 反思学习完成:")
                print(f"   标注器建议: {len(reflection.get('annotator_prompts', []))} 条")
                print(f"   生成器建议: {len(reflection.get('generator_prompts', []))} 条")
                print(f"   耗时: {reflection_time:.2f}秒\n")

                # 保存反思结果到输出目录
                reflection_path = params['output_dir'] / 'background_reflection.json'
                with open(reflection_path, 'w', encoding='utf-8') as f:
                    json.dump(reflection, f, ensure_ascii=False, indent=2)
                print(f"📝 反思结果已保存: {reflection_path}\n")
            else:
                print("─" * 80)
                print("✅ 步骤2: 未发现问题，无需反思学习")
                print("─" * 80)
                print("🎉 文档质量良好，跳过知识库更新\n")

            # ============================================================
            # 完成
            # ============================================================
            total_time = time.time() - start_time
            print(f"{'='*80}")
            print(f"✅ 后台学习任务完成")
            print(f"{'='*80}")
            print(f"⏰ 完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"⏱️  总耗时: {total_time:.2f}秒")
            print(f"📚 知识库: {params['kb'].kb_path}")
            print(f"{'='*80}\n")

        except Exception as e:
            print(f"\n{'='*80}")
            print(f"❌ 后台学习任务失败")
            print(f"{'='*80}")
            print(f"错误: {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"{'='*80}\n")


# ============================================================
# 便捷函数 - 快速使用
# ============================================================

def generate_document(
    template_path: str,
    user_requirement: str,
    mode: str = "inference",
    output_dir: Optional[str] = None,
    **kwargs
) -> DocumentGenerationResult:
    """
    快速生成文档 (便捷函数)

    Args:
        template_path: 模板文档路径
        user_requirement: 用户需求描述
        mode: 运行模式 ("inference" 或 "training")
        output_dir: 输出目录 (可选)
        **kwargs: 其他参数传递给DocumentGenerator

    Returns:
        DocumentGenerationResult: 生成结果

    Example:
        >>> from core.document_generator import generate_document
        >>> result = generate_document(
        ...     template_path="template.docx",
        ...     user_requirement="生成Python课程教案",
        ...     mode="inference"
        ... )
        >>> print(f"生成完成: {result.final_docx}")
    """
    generator = DocumentGenerator(**kwargs)
    return generator.generate(
        template_path=template_path,
        user_requirement=user_requirement,
        mode=mode,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    # 测试示例
    import sys

    if len(sys.argv) < 3:
        print("用法: python document_generator.py <template.docx> <需求描述> [mode]")
        print("示例: python document_generator.py template.docx '生成Python课程教案' inference")
        sys.exit(1)

    template = sys.argv[1]
    requirement = sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "inference"

    result = generate_document(
        template_path=template,
        user_requirement=requirement,
        mode=mode,
    )

    if result.success:
        print(f"\n✅ 生成成功！")
        print(f"📄 最终文档: {result.final_docx}")
    else:
        print(f"\n❌ 生成失败: {result.error}")
        sys.exit(1)
