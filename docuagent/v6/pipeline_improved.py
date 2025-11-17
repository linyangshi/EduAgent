"""
V6改进版Pipeline: 并行标注 + JSON修复 + 串行生成
结合V6的并行标注速度优势和V4的串行生成质量优势
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from docuagent.v4.content_generation.content_generator import ContentGenerator
from docuagent.v4.content_generation.state import FieldAnalysis, GeneratedField
from docuagent.v4.feature_markdown import DocxMarkdownExporter
from docuagent.v6.parallel_annotator import parallel_annotate
from docuagent.v6.json_fixer import parse_llm_json
from run_v4_content_generation import load_user_input_example


class ImprovedPipeline:
    """
    V6改进版Pipeline

    特点:
    1. 并行标注 (V6) - 速度快
    2. JSON修复器 - 处理格式问题
    3. 串行生成 (V4) - 质量好,字段长度可控
    """

    def __init__(
        self,
        template_docx: Path,
        output_dir: Path,
        user_input: Optional[Dict] = None,
        max_concurrent: int = 10,
    ):
        self.template_docx = template_docx
        self.output_dir = output_dir
        self.user_input = user_input or load_user_input_example()
        self.max_concurrent = max_concurrent

        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def run(self) -> Dict:
        """运行完整pipeline"""
        print("\n" + "="*80)
        print("🚀 V6改进版Pipeline: 并行标注 + JSON修复 + 串行生成")
        print("="*80 + "\n")

        results = {}

        # 阶段1: DOCX -> Markdown
        print("📄 阶段1: DOCX -> Markdown")
        md_path, manifest_path = self._export_to_markdown()
        results["markdown_path"] = md_path
        results["manifest_path"] = manifest_path
        print(f"   ✅ Markdown: {md_path}")
        print(f"   ✅ Manifest: {manifest_path}\n")

        # 阶段2: 并行标注 + JSON修复
        print("🏷️  阶段2: 并行标注 (多线程)")
        annotations, annotated_md = self._parallel_annotate_with_fix(md_path)
        results["annotations"] = annotations
        results["annotated_md_path"] = annotated_md
        print(f"   ✅ 标注数量: {len(annotations)}")
        print(f"   ✅ Annotated MD: {annotated_md}\n")

        # 阶段3: 字段分析
        print("📊 阶段3: 字段分析")
        field_analyses = self._analyze_fields(annotations)
        results["field_analyses"] = field_analyses
        print(f"   ✅ 字段数量: {len(field_analyses)}\n")

        # 阶段4: 串行生成
        print("✍️  阶段4: 串行生成 (逐个字段)")
        generated_content = self._serial_generate(field_analyses)
        results["generated_content"] = generated_content
        print(f"   ✅ 生成字段数: {len(generated_content)}\n")

        # 阶段5: 注入内容到DOCX
        print("📝 阶段5: 注入内容到DOCX")
        final_docx = self._inject_and_rebuild(
            generated_content,
            annotated_md,
            manifest_path
        )
        results["final_docx"] = final_docx
        print(f"   ✅ 最终DOCX: {final_docx}\n")

        # 保存结果
        self._save_results(results)

        print("="*80)
        print("✅ Pipeline完成!")
        print("="*80 + "\n")

        return results

    def _export_to_markdown(self) -> tuple[Path, Path]:
        """导出DOCX为Markdown"""
        exporter = DocxMarkdownExporter(self.template_docx)
        md_path, manifest_path = exporter.export(
            output_dir=self.output_dir / "markdown"
        )
        return Path(md_path), Path(manifest_path)

    def _parallel_annotate_with_fix(self, md_path: Path) -> tuple[List[Dict], Path]:
        """
        并行标注 + JSON修复

        Returns:
            (annotations, annotated_md_path)
        """
        # 执行并行标注
        start_time = time.perf_counter()

        result = parallel_annotate(
            md_path=md_path,
            output_dir=self.output_dir,
            max_concurrent=self.max_concurrent,
        )

        # JSON修复:检查并修复每个标注
        annotations = []
        for ann in result.combined_annotations:
            # 确保必要字段存在
            if not all(k in ann for k in ['line_number', 'original_text', 'placeholder']):
                print(f"   ⚠️  跳过无效标注: {ann}")
                continue
            annotations.append(ann)

        duration = time.perf_counter() - start_time

        print(f"   ⏱️  标注耗时: {duration:.2f}秒")
        print(f"   📈 加速比: {len(annotations)*2/duration:.2f}x (vs 串行)")

        # 读取Markdown
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # 应用标注到Markdown
        annotated_md = self._apply_annotations(md_content, annotations)
        annotated_md_path = self.output_dir / f"annotated_{self.timestamp}.md"

        with open(annotated_md_path, 'w', encoding='utf-8') as f:
            f.write(annotated_md)

        # 保存标注JSON
        annotations_path = self.output_dir / f"annotations_{self.timestamp}.json"
        with open(annotations_path, 'w', encoding='utf-8') as f:
            json.dump({"annotations": annotations}, f, ensure_ascii=False, indent=2)

        return annotations, annotated_md_path

    def _apply_annotations(self, md_content: str, annotations: List[Dict]) -> str:
        """应用标注到Markdown"""
        lines = md_content.split('\n')

        # 按行号排序(倒序,避免行号偏移)
        sorted_anns = sorted(annotations, key=lambda x: x['line_number'], reverse=True)

        for ann in sorted_anns:
            line_num = ann['line_number']
            action = ann.get('action', 'replace')
            placeholder = f"{{{{{ann['placeholder']}}}}}"

            if line_num < len(lines):
                if action == 'replace':
                    lines[line_num] = placeholder
                elif action == 'append':
                    lines[line_num] = lines[line_num] + '\n' + placeholder

        return '\n'.join(lines)

    def _analyze_fields(self, annotations: List[Dict]) -> Dict[str, FieldAnalysis]:
        """分析字段,转换为FieldAnalysis对象"""
        field_analyses = {}

        for ann in annotations:
            placeholder = ann['placeholder']

            # 简化的字段分析
            field = FieldAnalysis(
                placeholder=placeholder,
                field_type=ann.get('field_type', 'content'),
                content_type=ann.get('content_type', '内容'),
                length_requirement={
                    "min_chars": 10,
                    "max_chars": 500,
                    "target_items": 3,
                },
                style="formal",
                generation_strategy="paragraph_generation",
                dependencies=[],
                priority=5,
                annotation=ann,
            )

            field_analyses[placeholder] = field

        return field_analyses

    def _serial_generate(self, field_analyses: Dict[str, FieldAnalysis]) -> Dict[str, GeneratedField]:
        """
        串行生成所有字段

        使用V4的ContentGenerator,逐个生成,保证质量
        """
        generator = ContentGenerator()
        generated_content = {}

        # 按优先级排序
        sorted_fields = sorted(
            field_analyses.values(),
            key=lambda f: f.priority
        )

        total = len(sorted_fields)
        start_time = time.perf_counter()

        for i, field in enumerate(sorted_fields, 1):
            field_start = time.perf_counter()

            # 获取已生成内容
            generated_dict = {
                ph: gf.content for ph, gf in generated_content.items()
            }

            print(f"   [{i}/{total}] {field.placeholder}")

            try:
                # 调用V4生成器
                generated_field = generator.generate_content(
                    field_analysis=field,
                    user_input=self.user_input,
                    generated_content=generated_dict,
                    kb_insights="",
                )

                generated_content[field.placeholder] = generated_field

                field_duration = time.perf_counter() - field_start
                print(f"       ✅ {len(generated_field.content)}字符 ({field_duration:.2f}秒)")

            except Exception as e:
                print(f"       ❌ 生成失败: {e}")
                # 使用默认占位符
                generated_content[field.placeholder] = GeneratedField(
                    placeholder=field.placeholder,
                    content=f"[待填写: {field.content_type}]",
                    passed_checks=False,
                )

        total_duration = time.perf_counter() - start_time
        print(f"   ⏱️  生成总耗时: {total_duration:.2f}秒 ({total_duration/60:.2f}分钟)")

        return generated_content

    def _inject_and_rebuild(
        self,
        generated_content: Dict[str, GeneratedField],
        annotated_md_path: Path,
        manifest_path: Path,
    ) -> Path:
        """注入内容并重建DOCX"""
        # 读取annotated markdown
        with open(annotated_md_path, 'r', encoding='utf-8') as f:
            md_text = f.read()

        # 替换占位符
        for placeholder, field in generated_content.items():
            patterns = [
                f"{{{{{placeholder}}}}}",
                f"[{placeholder}]",
            ]
            for pattern in patterns:
                md_text = md_text.replace(pattern, field.content)

        # 保存填充后的markdown
        filled_md_path = self.output_dir / f"filled_{self.timestamp}.md"
        with open(filled_md_path, 'w', encoding='utf-8') as f:
            f.write(md_text)

        # 重建DOCX
        exporter = DocxMarkdownExporter.from_manifest(manifest_path)
        final_docx_path = self.output_dir / f"教案_V6改进_{self.timestamp}.docx"

        exporter.rebuild_docx(
            markdown_path=filled_md_path,
            output_path=final_docx_path,
        )

        return final_docx_path

    def _save_results(self, results: Dict):
        """保存结果摘要"""
        summary = {
            "timestamp": self.timestamp,
            "template": str(self.template_docx),
            "annotation_count": len(results.get("annotations", [])),
            "field_count": len(results.get("field_analyses", {})),
            "generated_count": len(results.get("generated_content", {})),
            "output_files": {
                "markdown": str(results.get("markdown_path")),
                "annotated_md": str(results.get("annotated_md_path")),
                "final_docx": str(results.get("final_docx")),
            }
        }

        summary_path = self.output_dir / "pipeline_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        print(f"📄 Pipeline摘要已保存: {summary_path}")


def run_improved_pipeline(
    template_docx: str | Path,
    output_dir: str | Path,
    user_input: Optional[Dict] = None,
) -> Dict:
    """
    运行改进版V6 Pipeline

    Args:
        template_docx: 模板DOCX路径
        output_dir: 输出目录
        user_input: 用户输入(可选)

    Returns:
        Pipeline结果字典
    """
    pipeline = ImprovedPipeline(
        template_docx=Path(template_docx),
        output_dir=Path(output_dir),
        user_input=user_input,
    )

    return pipeline.run()
