"""
使用V6标注结果 + V4串行生成流程
用于对比V6批量生成和V4串行生成的字段长度控制效果
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from docuagent.v4.content_generation.state import ContentGenerationState
from docuagent.v4.content_generation.workflow import build_content_generation_graph, reinject_with_existing_generation
from run_v4_content_generation import load_user_input_example


def main():
    print("\n" + "=" * 80)
    print("🔄 V6标注 + V4串行生成 对比测试")
    print("=" * 80)

    # V6标注结果路径
    v6_dir = Path(__file__).resolve().parents[2] / "results/v6_complete/20251117_011456"
    annotations_path = v6_dir / "annotations_20251117_011456.json"
    annotated_md_path = v6_dir / "annotated_20251117_011456.md"
    field_analysis_path = v6_dir / "field_analysis_20251117_011456.json"

    # 检查文件是否存在
    for path in [annotations_path, annotated_md_path, field_analysis_path]:
        if not path.exists():
            print(f"❌ 文件不存在: {path}")
            return 1

    # 创建输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("results/v4_with_v6_annotations") / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📂 输出目录: {output_dir}")
    print(f"📥 标注文件: {annotations_path}")
    print(f"📝 Markdown: {annotated_md_path}")
    print(f"📊 字段分析: {field_analysis_path}")

    # 加载数据
    with open(annotations_path, "r", encoding="utf-8") as f:
        ann_data = json.load(f)
        annotations = ann_data.get("annotations", [])

    with open(field_analysis_path, "r", encoding="utf-8") as f:
        field_analysis = json.load(f)

    # 加载用户输入（使用示例）
    user_input = load_user_input_example()

    print(f"\n📊 数据统计:")
    print(f"   - 标注数量: {len(annotations)}")
    print(f"   - 字段数量: {len(field_analysis)}")

    # 创建内容生成状态
    state = ContentGenerationState(
        annotations=annotations,
        user_input=user_input,
        markdown_path=str(annotated_md_path),
        field_analyses=field_analysis,
        kb_insights="",  # 暂不使用知识库
        doc_type="lesson_plan",
    )

    # 构建V4工作流（串行生成，不使用批量生成）
    print("\n🔧 构建V4串行生成工作流...")
    workflow = build_content_generation_graph(use_batch_generation=False)

    # 运行生成流程
    print("\n🚀 开始V4串行生成...")
    print("=" * 80)

    start_time = time.perf_counter()

    try:
        final_state = workflow.invoke(state)
    except Exception as e:
        print(f"\n❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    end_time = time.perf_counter()
    duration = end_time - start_time

    print("\n" + "=" * 80)
    print(f"✅ 生成完成! 耗时: {duration:.2f}秒")
    print("=" * 80)

    # 保存生成结果
    generated_content_path = output_dir / "generated_content_v4.json"
    with open(generated_content_path, "w", encoding="utf-8") as f:
        # 将生成的内容转换为可序列化的格式
        content_dict = {}
        for ph, field in final_state.generated_content.items():
            content_dict[ph] = {
                "content": field.content,
                "field_type": field.field_type,
                "placeholder": field.placeholder,
                "generation_strategy": field.generation_strategy,
                "quality_score": field.quality_score,
                "passed_checks": field.passed_checks,
            }
        json.dump(content_dict, f, ensure_ascii=False, indent=2)

    print(f"\n💾 生成内容已保存: {generated_content_path}")

    # 注入内容到DOCX
    print("\n📝 注入内容到DOCX...")

    template_docx = Path("教案模版（未标注）.docx")
    if not template_docx.exists():
        print(f"⚠️  模板文件不存在: {template_docx}")
        print("   使用V6的markdown和manifest重建DOCX...")
        # 从V6结果中获取manifest
        manifest_path = v6_dir / "markdown" / "manifest.json"
    else:
        # 生成manifest（需要从原始DOCX）
        from docuagent.v4.feature_markdown import generate_feature_markdown
        _, manifest_path, _ = generate_feature_markdown(
            docx_path=template_docx,
            output_dir=output_dir / "temp_md",
            reuse_existing=False
        )

    reinject_result = reinject_content(
        annotations=annotations,
        generated_content=final_state.generated_content,
        markdown_path=annotated_md_path,
        manifest_path=manifest_path,
        output_dir=output_dir,
    )

    final_docx = Path(reinject_result["final_docx_path"])
    print(f"\n✅ 最终DOCX: {final_docx}")
    print(f"   文件大小: {final_docx.stat().st_size / 1024:.1f}KB")

    # 生成对比报告
    print("\n" + "=" * 80)
    print("📊 对比报告")
    print("=" * 80)
    print(f"\nV6批量生成结果: {v6_dir / '教案_V6完整流程_20251117_011456.docx'}")
    print(f"V4串行生成结果: {final_docx}")
    print(f"\nV6生成时间: ~5-6分钟 (批量API)")
    print(f"V4生成时间: {duration:.2f}秒 = {duration/60:.2f}分钟 (串行生成)")
    print(f"\n字段总数: {len(final_state.generated_content)}")

    # 字段长度统计
    total_chars_v4 = sum(len(f.content) for f in final_state.generated_content.values())
    print(f"V4总字符数: {total_chars_v4}")

    # 读取V6生成内容
    v6_content_path = v6_dir / "generated_content_20251117_011456.json"
    if v6_content_path.exists():
        with open(v6_content_path, "r", encoding="utf-8") as f:
            v6_content = json.load(f)
        total_chars_v6 = sum(len(v["content"]) for v in v6_content.values())
        print(f"V6总字符数: {total_chars_v6}")
        print(f"字符数差异: {total_chars_v4 - total_chars_v6} ({((total_chars_v4/total_chars_v6 - 1)*100):.1f}%)")

    print("\n💡 提示: 打开两个DOCX文件对比字段长度控制效果")
    print("\n" + "=" * 80)

    return 0


if __name__ == "__main__":
    exit(main())
