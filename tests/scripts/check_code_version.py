"""
检查代码版本和修复是否生效
"""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

print("=" * 80)
print("检查代码修复状态")
print("=" * 80)

# 检查1: workflow.py是否有enrichment函数
print("\n1. 检查workflow.py中的enrichment函数...")
try:
    from docuagent.v4.content_generation.workflow import _enrich_annotations_with_markers, _build_marker_index
    print("   ✅ enrichment函数存在")
except ImportError as e:
    print(f"   ❌ enrichment函数不存在: {e}")

# 检查2: prompts.py是否有位置提取函数
print("\n2. 检查prompts.py中的位置提取函数...")
try:
    from docuagent.v4.content_generation.prompts import _extract_position_from_marker, _build_position_hint
    print("   ✅ 位置提取函数存在")
except ImportError as e:
    print(f"   ❌ 位置提取函数不存在: {e}")

# 检查3: 读取flask_app.py的关键行
print("\n3. 检查flask_app.py的修改...")
with open(Path(__file__).resolve().parents[2] / "interface/flask_app.py", 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 检查第2328行（应该是manifest_path）
line_2328 = lines[2327].strip() if len(lines) > 2327 else ""
if "manifest_path = exporter.export" in line_2328:
    print("   ✅ 第2328行：正确使用manifest_path")
else:
    print(f"   ❌ 第2328行有问题: {line_2328}")

# 检查第2336行（应该是json.load）
line_2336 = lines[2335].strip() if len(lines) > 2335 else ""
if "manifest = json.load" in line_2336:
    print("   ✅ 第2336行：正确加载manifest数据")
else:
    print(f"   ❌ 第2336行有问题: {line_2336}")

# 检查第2351行（应该是manifest_path）
line_2351 = lines[2350].strip() if len(lines) > 2350 else ""
if "manifest_path" in line_2351 and "features_path" in line_2351:
    print("   ✅ 第2351行：正确使用manifest_path作为features_path")
else:
    print(f"   ❌ 第2351行有问题: {line_2351}")

# 检查第2469行（应该是manifest=manifest）
line_2469 = lines[2468].strip() if len(lines) > 2468 else ""
if "manifest=manifest" in line_2469:
    print("   ✅ 第2469行：正确传递manifest字典")
else:
    print(f"   ❌ 第2469行有问题: {line_2469}")

# 检查第2640行（应该是manifest_path）
line_2640 = lines[2639].strip() if len(lines) > 2639 else ""
if "manifest_path=PathLib(manifest_path)" in line_2640:
    print("   ✅ 第2640行：正确使用manifest_path")
else:
    print(f"   ❌ 第2640行有问题: {line_2640}")

print("\n" + "=" * 80)
print("检查完成")
print("=" * 80)

# 测试enrichment功能
print("\n4. 测试enrichment功能...")
test_manifest = {
    "tables": [{
        "rows": [[
            {"text": "教学环节", "marker": "[[DOCX-CELL table=T0000 row=0 grid_col=0]]"}
        ]]
    }]
}

test_annotations = [
    {"placeholder": "test1", "original_text": "教学环节"}
]

try:
    from docuagent.v4.content_generation.workflow import _enrich_annotations_with_markers
    enriched = _enrich_annotations_with_markers(test_annotations, test_manifest)
    if "marker" in enriched[0]:
        print("   ✅ enrichment功能正常工作")
        print(f"   关联成功: {enriched[0]['marker'][:50]}...")
    else:
        print("   ❌ enrichment未能关联marker")
except Exception as e:
    print(f"   ❌ enrichment测试失败: {e}")

# 测试位置提取功能
print("\n5. 测试位置提取功能...")
test_marker = "[[DOCX-CELL table=T0000 row=1 grid_col=0 cell_id=T0000-R001-C000]]"
try:
    from docuagent.v4.content_generation.prompts import _extract_position_from_marker, _build_position_hint
    pos_info = _extract_position_from_marker(test_marker)
    if pos_info and pos_info.get("is_first_column"):
        print("   ✅ 位置提取功能正常工作")
        print(f"   提取结果: {pos_info}")

        # 测试hint构建
        field_analysis = {
            "annotation": {"marker": test_marker},
            "field_type": "basic_info"
        }
        hint = _build_position_hint(field_analysis)
        if "第一列" in hint:
            print("   ✅ 位置提示包含第一列警告")
        else:
            print("   ⚠️ 位置提示缺少第一列警告")
    else:
        print("   ❌ 位置提取失败")
except Exception as e:
    print(f"   ❌ 位置提取测试失败: {e}")

print("\n" + "=" * 80)
print("总结")
print("=" * 80)
print("\n如果以上所有检查都通过，说明代码修复正确。")
print("如果仍然没有位置信息，可能原因：")
print("  1. Flask服务未重启，还在运行旧代码")
print("  2. manifest在传递过程中丢失或为空")
print("  3. annotation的original_text与manifest中的text不匹配")
print("\n请重启Flask服务并查看终端输出：")
print("  - 应该看到：'Manifest加载成功: X 个表格, Y 个段落'")
print("  - 应该看到：'🔗 成功关联 X/Y 个字段的marker信息'")
print()
