"""
运行V6改进版Pipeline测试脚本

特点:
1. 并行标注 (10线程) - 速度快
2. JSON修复器 - 自动修复LLM返回的格式问题
3. 串行生成 - 质量好,字段长度可控
"""

from pathlib import Path

from docuagent.v6.pipeline_improved import run_improved_pipeline


def main():
    # 模板文件
    template_docx = Path("教案模版（未标注）.docx")

    if not template_docx.exists():
        print(f"❌ 模板文件不存在: {template_docx}")
        return 1

    # 输出目录
    output_dir = Path("results/v6_improved")

    # 运行改进版pipeline
    results = run_improved_pipeline(
        template_docx=template_docx,
        output_dir=output_dir,
        user_input=None,  # 使用默认用户输入
    )

    # 打印结果摘要
    print("\n" + "="*80)
    print("📊 结果摘要")
    print("="*80)
    print(f"✅ 标注数量: {len(results['annotations'])}")
    print(f"✅ 字段数量: {len(results['field_analyses'])}")
    print(f"✅ 生成数量: {len(results['generated_content'])}")
    print(f"✅ 最终文档: {results['final_docx']}")
    print("="*80 + "\n")

    return 0


if __name__ == "__main__":
    exit(main())
