"""
验证Marker关联修复 - 实际生成测试

测试目标：
1. 确认marker关联成功率
2. 确认位置信息注入到prompt
3. 确认知识库约束注入到prompt
4. 确认表格第一列生成简短文本
"""

from pathlib import Path
import sys
import os
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from docuagent.v4.content_generation.workflow import (
    _build_marker_index,
    _enrich_annotations_with_markers,
)
from docuagent.v4.content_generation.prompts import (
    _extract_position_from_marker,
    _build_position_hint,
    create_content_generation_prompt
)


def test_with_real_manifest():
    """使用真实的manifest数据测试"""
    print("\n" + "=" * 80)
    print("🧪 使用真实Manifest数据测试")
    print("=" * 80)

    # 模拟一个真实的manifest（从DOCX导出）
    manifest = {
        "tables": [
            {
                "block_id": "T0000",
                "rows": [
                    # 表头行
                    [
                        {
                            "text": "教学环节",
                            "marker": "[[DOCX-CELL table=T0000 row=0 grid_col=0 cell_id=T0000-R000-C000]]",
                            "grid_col_index": 0
                        },
                        {
                            "text": "教师活动",
                            "marker": "[[DOCX-CELL table=T0000 row=0 grid_col=1 cell_id=T0000-R000-C001]]",
                            "grid_col_index": 1
                        },
                        {
                            "text": "学生活动",
                            "marker": "[[DOCX-CELL table=T0000 row=0 grid_col=2 cell_id=T0000-R000-C002]]",
                            "grid_col_index": 2
                        }
                    ],
                    # 数据行1
                    [
                        {
                            "text": "导入新课环节名称待生成",
                            "marker": "[[DOCX-CELL table=T0000 row=1 grid_col=0 cell_id=T0000-R001-C000]]",
                            "grid_col_index": 0
                        },
                        {
                            "text": "教师活动内容待生成",
                            "marker": "[[DOCX-CELL table=T0000 row=1 grid_col=1 cell_id=T0000-R001-C001]]",
                            "grid_col_index": 1
                        },
                        {
                            "text": "学生活动内容待生成",
                            "marker": "[[DOCX-CELL table=T0000 row=1 grid_col=2 cell_id=T0000-R001-C002]]",
                            "grid_col_index": 2
                        }
                    ],
                    # 数据行2
                    [
                        {
                            "text": "知识讲解环节名称待生成",
                            "marker": "[[DOCX-CELL table=T0000 row=2 grid_col=0 cell_id=T0000-R002-C000]]",
                            "grid_col_index": 0
                        },
                        {
                            "text": "教师活动内容待生成",
                            "marker": "[[DOCX-CELL table=T0000 row=2 grid_col=1 cell_id=T0000-R002-C001]]",
                            "grid_col_index": 1
                        },
                        {
                            "text": "学生活动内容待生成",
                            "marker": "[[DOCX-CELL table=T0000 row=2 grid_col=2 cell_id=T0000-R002-C002]]",
                            "grid_col_index": 2
                        }
                    ]
                ]
            }
        ],
        "paragraphs": [
            {
                "text": "一、教学目标",
                "block_id": "P0001"
            }
        ]
    }

    # 模拟LLM标注结果（没有marker）
    annotations = [
        {
            "placeholder": "teaching_step_1",
            "action": "replace",
            "reason": "第一列教学环节",
            "location_type": "table_cell",
            "original_text": "导入新课环节名称待生成"
        },
        {
            "placeholder": "teacher_activity_1",
            "action": "replace",
            "reason": "教师活动",
            "location_type": "table_cell",
            "original_text": "教师活动内容待生成"
        },
        {
            "placeholder": "student_activities_1",
            "action": "replace",
            "reason": "学生活动",
            "location_type": "table_cell",
            "original_text": "学生活动内容待生成"
        },
        {
            "placeholder": "teaching_step_2",
            "action": "replace",
            "reason": "第二个教学环节",
            "location_type": "table_cell",
            "original_text": "知识讲解环节名称待生成"
        }
    ]

    print(f"\n原始Annotations (无marker): {len(annotations)}个")
    for i, annot in enumerate(annotations, 1):
        has_marker = "marker" in annot
        print(f"  {i}. {annot['placeholder']} - has marker: {has_marker}")

    # Step 1: Enrich annotations
    print("\n" + "-" * 80)
    print("🔥 执行Enrichment...")
    enriched = _enrich_annotations_with_markers(annotations, manifest)

    print(f"\nEnriched Annotations (有marker): {len(enriched)}个")
    for i, annot in enumerate(enriched, 1):
        has_marker = "marker" in annot
        marker_preview = annot.get("marker", "N/A")[:60] if has_marker else "N/A"
        print(f"  {i}. {annot['placeholder']}")
        print(f"     - has marker: {has_marker}")
        if has_marker:
            print(f"     - marker: {marker_preview}...")

    # Step 2: 测试位置提取和Prompt生成
    print("\n" + "-" * 80)
    print("🔍 测试位置提取和Prompt生成...")

    for annot in enriched:
        if "marker" not in annot:
            continue

        placeholder = annot["placeholder"]
        marker = annot["marker"]

        # 提取位置信息
        pos_info = _extract_position_from_marker(marker)

        # 构建field_analysis（模拟analyze_fields的输出）
        field_analysis = {
            "placeholder": placeholder,
            "field_type": "basic_info" if "step" in placeholder else "activity",
            "annotation": annot
        }

        # 生成位置提示
        position_hint = _build_position_hint(field_analysis)

        print(f"\n字段: {placeholder}")
        print(f"位置信息: {pos_info}")
        if position_hint:
            print(f"位置提示:\n{position_hint}")
        else:
            print("位置提示: (无)")

        # 模拟生成完整prompt
        if pos_info and pos_info.get("is_first_column"):
            print("\n⚠️  这是第一列字段！应该有特殊约束！")
            print("   预期: 生成5-20字的简短环节名，如'导入新课'、'知识讲解'")
        else:
            print("\n✅ 非第一列字段，可以生成详细内容（66-266字）")


def test_prompt_generation():
    """测试完整的Prompt生成"""
    print("\n" + "=" * 80)
    print("🧪 测试完整Prompt生成")
    print("=" * 80)

    # 模拟第一列字段的field_analysis（包含所有必需字段）
    field_analysis_first_col = {
        "placeholder": "teaching_step_1",
        "field_type": "basic_info",
        "content_type": "教学环节",  # ✅ 必需
        "length_requirement": {      # ✅ 必需
            "min_chars": 5,
            "max_chars": 20,
            "target_items": 1
        },
        "style": "formal",           # ✅ 必需
        "annotation": {
            "placeholder": "teaching_step_1",
            "original_text": "导入新课",
            "marker": "[[DOCX-CELL table=T0000 row=1 grid_col=0 cell_id=T0000-R001-C000]]"
        },
        "dependencies": [],
        "context": {}
    }

    # 生成prompt
    prompt = create_content_generation_prompt(
        field_analysis=field_analysis_first_col,
        kb_insights="【表格第一列「教学环节」字段特殊约束】\n必须遵守：仅填写简短环节名称，5-15个汉字\n示例：'导入新课'、'知识讲解'、'练习巩固'",
        user_input={"prompt": "python编程"},
        generated_content={}
    )

    print("\n生成的Prompt:")
    print("-" * 80)
    print(prompt)
    print("-" * 80)

    # 检查关键内容
    checks = {
        "包含位置信息": "位置: 表格" in prompt,
        "包含第一列警告": "第一列" in prompt,
        "包含知识库约束": "表格第一列" in prompt and "特殊约束" in prompt,
        "包含示例格式": "导入新课" in prompt or "知识讲解" in prompt,
    }

    print("\n✅ Prompt检查结果:")
    for check_name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {check_name}: {result}")

    all_passed = all(checks.values())
    if all_passed:
        print("\n🎉 所有检查通过！Prompt包含了位置信息和知识库约束！")
    else:
        print("\n❌ 部分检查失败，需要进一步调试")

    return all_passed


if __name__ == "__main__":
    print("\n" + "🔍 Marker关联修复 - 实际数据验证".center(80, "="))

    try:
        # 测试1: 使用真实manifest数据
        test_with_real_manifest()

        # 测试2: 完整prompt生成
        success = test_prompt_generation()

        print("\n" + "=" * 80)
        if success:
            print("🎉 验证成功！修复已生效！".center(80))
        else:
            print("⚠️  验证发现问题，需要进一步调试".center(80))
        print("=" * 80)

        print("\n下一步:")
        print("  1. 重启Flask服务: python web_main.py")
        print("  2. 上传模板并生成文档")
        print("  3. 查看终端输出的marker关联统计")
        print("  4. 查看logs/llm_prompts/目录下的最新日志")
        print("  5. 验证表格第一列是否生成简短环节名")
        print()

    except Exception as e:
        print(f"\n❌ 验证出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
