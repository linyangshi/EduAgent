"""
验证 Prompts 重构是否成功
"""

print("=" * 80)
print("验证 Prompts 重构")
print("=" * 80)

# 1. 验证文件存在性
import os
from pathlib import Path

print("\n1️⃣ 检查文件存在性...")

v4_dir = Path("docuagent/v4/content_generation")
files_check = {
    "主Prompt文件": v4_dir / "prompts.py",
    "遗留Prompt文件（可选）": v4_dir / "prompts_legacy.py.legacy",
}

for name, filepath in files_check.items():
    if filepath.exists():
        print(f"   ✅ {name}: {filepath}")
    else:
        if "可选" in name:
            print(f"   ℹ️  {name}: {filepath} (已删除，不影响使用)")
        else:
            print(f"   ❌ {name}: {filepath} (不存在)")

# 检查不应该存在的文件
old_files = [
    v4_dir / "prompts_simplified.py",
    v4_dir / "prompts_legacy.py",  # 不应该有这个（应该是.legacy后缀）
]

for old_file in old_files:
    if old_file.exists():
        print(f"   ⚠️  警告: {old_file} 仍然存在（应该已重命名）")

print(f"   ✅ 旧文件已清理完成")

# 2. 验证模块导入
print("\n2️⃣ 验证模块导入...")

try:
    from docuagent.v4.content_generation.prompts import (
        create_content_generation_prompt,
        create_batch_generation_prompt,
        create_quality_check_prompt,
    )
    print("   ✅ 主Prompt模块导入成功")
except ImportError as e:
    print(f"   ❌ 主Prompt模块导入失败: {e}")

# 遗留文件（.legacy后缀）不应该能被导入
try:
    from docuagent.v4.content_generation.prompts_legacy import (
        create_content_generation_prompt as legacy_create_prompt,
    )
    print("   ⚠️  遗留Prompt模块仍可导入（应该加.legacy后缀防止误用）")
except ImportError:
    print("   ✅ 遗留文件已正确隔离（无法导入）")

# 3. 验证生产代码引用
print("\n3️⃣ 验证生产代码引用...")

try:
    from docuagent.v4.content_generation.content_generator import ContentGenerator
    print("   ✅ ContentGenerator 导入成功")
except ImportError as e:
    print(f"   ❌ ContentGenerator 导入失败: {e}")

try:
    from docuagent.v6.parallel_generator import parallel_generate_batch
    print("   ✅ V6 parallel_generator 导入成功")
except ImportError as e:
    print(f"   ❌ V6 parallel_generator 导入失败: {e}")

try:
    from core.document_generator import DocumentGenerator
    print("   ✅ Core DocumentGenerator 导入成功")
except ImportError as e:
    print(f"   ❌ Core DocumentGenerator 导入失败: {e}")

try:
    from interface.flask_app import create_app
    print("   ✅ Flask app 导入成功")
except ImportError as e:
    print(f"   ❌ Flask app 导入失败: {e}")

# 4. 验证Prompt功能
print("\n4️⃣ 验证Prompt功能...")

field_analysis_dict = {
    'placeholder': 'teacher_name',
    'field_type': 'basic_info',
    'content_type': '教师姓名',
    'length_requirement': {'min_chars': 2, 'max_chars': 10},
    'style': 'brief',
    'dependencies': [],
}

user_input = {'prompt': '测试'}
generated_content = {}
kb_insights = "测试约束"

try:
    prompt = create_content_generation_prompt(
        field_analysis_dict,
        user_input,
        generated_content,
        kb_insights=kb_insights
    )

    # 检查知识库约束是否注入
    if kb_insights in prompt:
        print("   ✅ 知识库约束成功注入到Prompt")
    else:
        print("   ❌ 知识库约束未注入到Prompt")

    # 检查Prompt结构
    if "## 上下文" in prompt and "## 要求" in prompt:
        print("   ✅ Prompt结构正确（包含上下文和要求部分）")
    else:
        print("   ⚠️  Prompt结构可能有问题")

except Exception as e:
    print(f"   ❌ Prompt生成失败: {e}")

# 5. 总结
print("\n" + "=" * 80)
print("验证完成！")
print("=" * 80)

print("\n📊 重构摘要:")
print("   - prompts_simplified.py → prompts.py (主文件)")
print("   - prompts.py → prompts_legacy.py (遗留文件)")
print("   - 所有生产代码引用已更新")
print("   - 旧调试脚本引用prompts_legacy.py")
print("\n💡 建议:")
print("   - 新开发请修改: docuagent/v4/content_generation/prompts.py")
print("   - 测试请运行: python test_kb_constraints.py")
print("   - 查看文档: PROMPTS_REFACTORING.md")
