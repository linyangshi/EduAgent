"""
调试：查看workflow执行时是否真的调用了analyze_fields
"""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 创建一个测试manifest和annotations
test_manifest = {
    "tables": [{
        "rows": [[
            {"text": "教学环节", "marker": "[[DOCX-CELL table=T0000 row=0 grid_col=0 cell_id=T0000-R000-C000]]"},
            {"text": "学生活动", "marker": "[[DOCX-CELL table=T0000 row=0 grid_col=1 cell_id=T0000-R000-C001]]"}
        ]]
    }],
    "paragraphs": []
}

test_annotations = [
    {
        "placeholder": "teaching_phase",
        "original_text": "教学环节",
        "action": "replace",
        "location_type": "table_cell"
    },
    {
        "placeholder": "student_activities",
        "original_text": "学生活动",
        "action": "replace",
        "location_type": "table_cell"
    }
]

test_user_input = {
    "prompt": "卷积神经网络",
    "basic_info": {},
    "teaching_context": {},
    "content_preferences": {
        "style": "formal",
        "detail_level": "detailed"
    }
}

print("=" * 80)
print("测试workflow执行")
print("=" * 80)

# 导入workflow
from docuagent.v4.content_generation.state import ContentGenerationState
from docuagent.v4.content_generation.workflow import build_content_generation_graph

# 创建state
state = ContentGenerationState(
    annotations=test_annotations,
    user_input=test_user_input,
    manifest=test_manifest,
    markdown_path="/tmp/test.md",
    total_fields=len(test_annotations),
    kb_insights="",
    doc_type="lesson_plan"
)

print(f"\n创建的state:")
print(f"  - annotations数量: {len(state.annotations)}")
print(f"  - manifest有tables: {'tables' in state.manifest}")
print(f"  - manifest tables数量: {len(state.manifest.get('tables', []))}")

# 构建graph
print(f"\n构建workflow graph...")
graph = build_content_generation_graph(batch_mode=True, batch_size=5)
print(f"✅ Graph构建成功")

# 检查graph中的节点
print(f"\n Graph节点列表:")
for node_name in graph.nodes:
    print(f"  - {node_name}")

print(f"\n⚠️ 注意：我们不会实际执行graph（因为需要LLM调用）")
print(f"\n但是，我们可以手动测试analyze_fields函数:")

# 手动测试analyze_fields
print("\n" + "=" * 80)
print("手动测试analyze_fields函数")
print("=" * 80)

from docuagent.v4.content_generation.workflow import analyze_fields

print(f"\n调用analyze_fields...")
try:
    new_state = analyze_fields(state)
    print(f"\n✅ analyze_fields执行成功")
    print(f"  - analyzed_fields数量: {len(new_state.analyzed_fields)}")
    print(f"  - field_order: {new_state.field_order}")

    # 检查第一个字段是否有marker
    if new_state.analyzed_fields:
        first_field = new_state.analyzed_fields[0]
        has_marker = "marker" in first_field.annotation
        print(f"\n第一个字段:")
        print(f"  - placeholder: {first_field.placeholder}")
        print(f"  - has marker: {has_marker}")
        if has_marker:
            print(f"  - marker: {first_field.annotation['marker'][:60]}...")
        else:
            print(f"  ⚠️ 第一个字段的annotation没有marker！")
            print(f"  - annotation keys: {first_field.annotation.keys()}")
except Exception as e:
    print(f"\n❌ analyze_fields执行失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("结论")
print("=" * 80)
print("\n如果上面显示'🔗 成功关联 X/Y 个字段的marker信息'，")
print("说明analyze_fields函数正常工作。")
print("\n如果Flask运行时没有显示这条消息，可能原因：")
print("  1. analyze_fields节点没有执行（被跳过）")
print("  2. 输出被重定向或缓冲了")
print("  3. state.manifest在传递过程中变成了空字典")
print()
