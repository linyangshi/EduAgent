"""
使用已有的Markdown文件进行V6并行标注，并转换回DOCX
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# 设置使用Qwen模型
os.environ['USE_QWEN_FOR_ANNOTATION'] = 'true'
os.environ['USE_FIREWORKS_FOR_ANNOTATION'] = 'false'
os.environ['GITCODE_MODEL'] = 'qwen-plus'

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from docuagent.v6.parallel_annotator import parallel_annotate, remove_segment_prefixes
from docuagent.v4.markdown_to_docx import rebuild_docx_from_markdown


def main():
    """使用已有Markdown进行并行标注"""

    print("="*80)
    print("V6 并行标注 + DOCX生成")
    print("="*80)

    # 使用已生成的文件
    md_dir = Path(__file__).resolve().parents[2] / "results/v6_annotation_test/20251116_013235/markdown"
    md_path = md_dir / "教案模版（未标注）_v4.md"
    manifest_path = md_dir / "教案模版（未标注）_v4_manifest.json"
    original_docx = Path(__file__).resolve().parents[2] / "教案模版（未标注）.docx"

    output_dir = Path(__file__).parent / "results" / "v6_final"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\n📁 工作目录: {output_dir}")
    print(f"📄 Markdown: {md_path}")
    print(f"📄 Manifest: {manifest_path}")
    print(f"📄 原始DOCX: {original_docx}")

    # ========================================
    # 步骤1: V6 并行标注
    # ========================================
    print("\n" + "-"*80)
    print("步骤1: V6 并行标注（10线程 + Qwen-Plus）")
    print("-"*80)

    step1_start = time.time()

    annotation_result = parallel_annotate(
        md_path=md_path,
        features_path=None,
        kb_insights=None,
        output_dir=output_dir / "annotation",
        max_concurrent=10,
        no_segment=False,
    )

    step1_time = time.time() - step1_start

    print(f"\n✅ 并行标注完成")
    print(f"   标注数: {len(annotation_result.combined_annotations)}")
    print(f"   耗时: {step1_time:.2f} 秒")

    # 清理前缀
    annotation_result.combined_annotations = remove_segment_prefixes(
        annotation_result.combined_annotations
    )

    # ========================================
    # 步骤2: 保存标注JSON并应用到Markdown
    # ========================================
    print("\n" + "-"*80)
    print("步骤2: 保存标注JSON并应用到Markdown")
    print("-"*80)

    # 先保存标注JSON(包含统计信息)
    annotations_json_path = output_dir / f"annotations_{timestamp}.json"
    with open(annotations_json_path, 'w', encoding='utf-8') as f:
        json.dump({
            "annotations": annotation_result.combined_annotations,
            "stats": annotation_result.to_dict(),
        }, f, ensure_ascii=False, indent=2)

    print(f"✅ 标注JSON已保存: {annotations_json_path}")
    print(f"   包含 {len(annotation_result.combined_annotations)} 个标注")

    # 应用标注到Markdown
    from docuagent.v4.apply_annotations import apply_annotations_to_markdown

    annotated_md_path = output_dir / f"annotated_{timestamp}.md"
    apply_annotations_to_markdown(
        md_path=md_path,
        annotations_json_path=annotations_json_path,
        output_md_path=annotated_md_path
    )

    print(f"✅ 标注已应用到Markdown")
    print(f"   输出: {annotated_md_path}")

    # ========================================
    # 步骤3: 转换回DOCX
    # ========================================
    print("\n" + "-"*80)
    print("步骤3: 生成标注后的DOCX")
    print("-"*80)

    final_docx_path = output_dir / f"教案模版_已标注_v6_{timestamp}.docx"

    rebuild_docx_from_markdown(
        markdown_path=annotated_md_path,
        manifest_path=manifest_path,
        output_docx_path=final_docx_path,
        base_docx_path=original_docx,
    )

    print(f"✅ DOCX生成成功")
    print(f"   输出: {final_docx_path}")

    print("\n" + "="*80)
    print("✅ 完成！")
    print("="*80)
    print(f"\n最终输出:")
    print(f"  📄 标注后的DOCX: {final_docx_path}")
    print(f"  📄 标注JSON: {annotations_json_path}")
    print(f"  📊 总标注数: {len(annotation_result.combined_annotations)}")
    print(f"  ⏱️  标注耗时: {step1_time:.2f} 秒")


if __name__ == "__main__":
    main()
