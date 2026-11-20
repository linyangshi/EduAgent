"""
使用V6标注结果 + 串行生成流程
参考V4逻辑,在V6中实现简洁的串行生成,与V6批量生成对比
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from docuagent.v4.content_generation.content_generator import ContentGenerator
from docuagent.v4.content_generation.state import FieldAnalysis, GeneratedField
from run_v4_content_generation import load_user_input_example

# 简化版: 先只生成内容并保存JSON,DOCX重建稍后实现
def serial_generate_content(
    field_analyses: Dict[str, Dict],
    user_input: Dict,
    kb_insights: str = "",
) -> Dict[str, GeneratedField]:
    """
    串行生成所有字段内容

    Args:
        field_analyses: V6的字段分析结果
        user_input: 用户输入
        kb_insights: 知识库洞察

    Returns:
        生成的字段内容字典 {placeholder: GeneratedField}
    """
    generator = ContentGenerator()
    generated_content = {}

    # 按优先级排序字段
    fields = []
    for placeholder, analysis in field_analyses.items():
        # 将字典转为FieldAnalysis对象
        field = FieldAnalysis(
            placeholder=placeholder,
            field_type=analysis.get("field_type", "unknown"),
            content_type=analysis.get("content_type", ""),
            length_requirement=analysis.get("length_requirement", {}),
            style=analysis.get("style", "formal"),
            generation_strategy=analysis.get("generation_strategy", "paragraph_generation"),
            dependencies=analysis.get("dependencies", []),
            priority=analysis.get("priority", 5),
            location_context=analysis.get("location_context"),
            surrounding_text=analysis.get("surrounding_text"),
            annotation=analysis.get("annotation"),
        )
        fields.append(field)

    # 按优先级排序(priority越小越优先)
    fields.sort(key=lambda f: f.priority)

    total = len(fields)
    print(f"\n📊 总字段数: {total}")
    print(f"🔄 开始串行生成...\n")

    start_time = time.perf_counter()

    for i, field in enumerate(fields, 1):
        field_start = time.perf_counter()

        # 获取已生成内容(用于依赖字段)
        generated_dict = {
            ph: gf.content for ph, gf in generated_content.items()
        }

        print(f"[{i}/{total}] 生成字段: {field.placeholder}")
        print(f"   类型: {field.content_type}")
        print(f"   策略: {field.generation_strategy}")

        try:
            # 调用V4的生成器
            generated_field = generator.generate_content(
                field_analysis=field,
                user_input=user_input,
                generated_content=generated_dict,
                kb_insights=kb_insights,
            )

            generated_content[field.placeholder] = generated_field

            field_duration = time.perf_counter() - field_start
            print(f"   ✅ 完成 ({field_duration:.2f}秒) - {len(generated_field.content)}字符\n")

        except Exception as e:
            print(f"   ❌ 生成失败: {e}\n")
            # 使用默认占位符
            generated_content[field.placeholder] = GeneratedField(
                placeholder=field.placeholder,
                content=f"[待填写: {field.content_type}]",
                passed_checks=False,
            )

    total_duration = time.perf_counter() - start_time

    print("\n" + "="*80)
    print(f"✅ 串行生成完成!")
    print(f"   总耗时: {total_duration:.2f}秒 = {total_duration/60:.2f}分钟")
    print(f"   平均每字段: {total_duration/total:.2f}秒")
    print("="*80 + "\n")

    return generated_content


def inject_content_to_markdown(
    generated_content: Dict[str, GeneratedField],
    annotated_md_path: Path,
    output_dir: Path,
    timestamp: str,
) -> Path:
    """
    将生成的内容注入到Markdown (暂时只生成MD,DOCX重建后续实现)

    Returns:
        填充后的Markdown文件路径
    """
    print("📝 注入内容到Markdown...")

    # 读取annotated markdown
    with open(annotated_md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    # 替换占位符
    for placeholder, field in generated_content.items():
        # 处理各种占位符格式
        patterns = [
            f"{{{{{placeholder}}}}}",  # {{placeholder}}
            f"[{placeholder}]",  # [placeholder]
        ]

        for pattern in patterns:
            if pattern in md_text:
                md_text = md_text.replace(pattern, field.content)

    # 保存填充后的markdown
    filled_md_path = output_dir / f"filled_{timestamp}.md"
    with open(filled_md_path, "w", encoding="utf-8") as f:
        f.write(md_text)

    print(f"   ✅ 已保存填充markdown: {filled_md_path}")
    print(f"   文件大小: {filled_md_path.stat().st_size / 1024:.1f}KB\n")

    return filled_md_path


def main():
    print("\n" + "="*80)
    print("🔄 V6标注 + 串行生成 对比测试")
    print("="*80 + "\n")

    # V6标注结果路径
    v6_dir = Path(__file__).resolve().parents[2] / "results/v6_complete/20251117_011456"
    annotations_path = v6_dir / "annotations_20251117_011456.json"
    annotated_md_path = v6_dir / "annotated_20251117_011456.md"
    field_analysis_path = v6_dir / "field_analysis_20251117_011456.json"

    # 检查文件
    for path in [annotations_path, annotated_md_path, field_analysis_path]:
        if not path.exists():
            print(f"❌ 文件不存在: {path}")
            return 1

    # 创建输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("results/v6_serial_generation") / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📂 输出目录: {output_dir}")
    print(f"📥 V6标注结果: {v6_dir}\n")

    # 加载数据
    with open(annotations_path, "r", encoding="utf-8") as f:
        ann_data = json.load(f)
        annotations = ann_data.get("annotations", [])

    with open(field_analysis_path, "r", encoding="utf-8") as f:
        field_analysis = json.load(f)

    # 加载用户输入(使用示例)
    user_input = load_user_input_example()

    print(f"📊 数据统计:")
    print(f"   标注数量: {len(annotations)}")
    print(f"   字段数量: {len(field_analysis)}\n")

    # 串行生成内容
    generated_content = serial_generate_content(
        field_analyses=field_analysis,
        user_input=user_input,
        kb_insights="",  # 暂不使用知识库
    )

    # 保存生成内容
    content_path = output_dir / "generated_content_serial.json"
    with open(content_path, "w", encoding="utf-8") as f:
        content_dict = {}
        for ph, field in generated_content.items():
            content_dict[ph] = {
                "content": field.content,
                "char_count": len(field.content),
                "passed_checks": field.passed_checks,
            }
        json.dump(content_dict, f, ensure_ascii=False, indent=2)

    print(f"💾 生成内容已保存: {content_path}\n")

    # 注入内容到Markdown
    filled_md = inject_content_to_markdown(
        generated_content=generated_content,
        annotated_md_path=annotated_md_path,
        output_dir=output_dir,
        timestamp=timestamp,
    )

    # 生成对比报告
    print("="*80)
    print("📊 对比报告")
    print("="*80 + "\n")

    v6_batch_docx = v6_dir / "教案_V6完整流程_20251117_011456.docx"

    print(f"V6批量生成结果: {v6_batch_docx}")
    if v6_batch_docx.exists():
        print(f"   文件大小: {v6_batch_docx.stat().st_size / 1024:.1f}KB")

    print(f"\n串行生成结果(Markdown): {filled_md}")
    print(f"   文件大小: {filled_md.stat().st_size / 1024:.1f}KB")

    # 字符数统计
    total_chars_serial = sum(len(f.content) for f in generated_content.values())
    print(f"\n串行生成总字符数: {total_chars_serial}")

    # 读取V6批量生成内容
    v6_content_path = v6_dir / "generated_content_20251117_011456.json"
    if v6_content_path.exists():
        with open(v6_content_path, "r", encoding="utf-8") as f:
            v6_content = json.load(f)
        total_chars_v6 = sum(len(v["content"]) for v in v6_content.values())
        print(f"V6批量生成总字符数: {total_chars_v6}")

        diff = total_chars_serial - total_chars_v6
        diff_pct = ((total_chars_serial / total_chars_v6 - 1) * 100) if total_chars_v6 > 0 else 0
        print(f"字符数差异: {diff:+d} ({diff_pct:+.1f}%)")

    print("\n💡 提示: 打开两个DOCX文件对比字段长度控制效果")
    print("="*80 + "\n")

    return 0


if __name__ == "__main__":
    exit(main())
