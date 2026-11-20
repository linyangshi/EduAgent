#!/usr/bin/env python3
"""
清理知识库中硬编码主题的条目

背景：
VLM反思学习会记录具体主题的建议（如"卷积神经网络"），
导致这些建议在处理其他主题时被检索到，污染生成结果。

清理策略：
1. 删除包含具体主题词的建议（如"卷积神经网络"）
2. 保留抽象的、通用的建议（如"教学内容分析必须充分详细"）
"""

import json
import re
from pathlib import Path

# 需要清理的硬编码主题关键词
HARDCODED_TOPICS = [
    "卷积神经网络",
    "卷积层",
    "池化层",
    "激活函数",
    "全连接层",
    "CNN",
    "深度学习",
]

def is_hardcoded_prompt(prompt_dict: dict) -> bool:
    """检查是否包含硬编码主题（检查prompt和reason字段）"""
    # 检查prompt字段
    prompt_text = prompt_dict.get('prompt', '')
    for topic in HARDCODED_TOPICS:
        if topic in prompt_text:
            return True

    # 检查reason字段
    reason_text = prompt_dict.get('reason', '')
    for topic in HARDCODED_TOPICS:
        if topic in reason_text:
            return True

    return False

def clean_knowledge_base(kb_path: Path):
    """清理知识库"""

    if not kb_path.exists():
        print(f"❌ 知识库不存在: {kb_path}")
        return

    # 读取所有条目
    entries = []
    with open(kb_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    print(f"\n📊 原始条目数: {len(entries)}")

    # 清理每条条目
    cleaned_entries = []
    removed_count = 0

    for entry in entries:
        cleaned_entry = entry.copy()

        # 清理 annotator_prompts
        if 'annotator_prompts' in cleaned_entry:
            original_count = len(cleaned_entry['annotator_prompts'])
            cleaned_entry['annotator_prompts'] = [
                p for p in cleaned_entry['annotator_prompts']
                if not is_hardcoded_prompt(p)
            ]
            removed = original_count - len(cleaned_entry['annotator_prompts'])
            if removed > 0:
                print(f"   🗑️  删除 {removed} 条标注器硬编码提示")
                removed_count += removed

        # 清理 generator_prompts
        if 'generator_prompts' in cleaned_entry:
            original_count = len(cleaned_entry['generator_prompts'])
            cleaned_entry['generator_prompts'] = [
                p for p in cleaned_entry['generator_prompts']
                if not is_hardcoded_prompt(p)
            ]
            removed = original_count - len(cleaned_entry['generator_prompts'])
            if removed > 0:
                print(f"   🗑️  删除 {removed} 条生成器硬编码提示")
                removed_count += removed

        # 只保留非空条目
        if (cleaned_entry.get('annotator_prompts') or
            cleaned_entry.get('generator_prompts')):
            cleaned_entries.append(cleaned_entry)

    print(f"\n📊 清理后条目数: {len(cleaned_entries)}")
    print(f"🗑️  共删除 {removed_count} 条硬编码提示")

    # 备份原文件
    backup_path = kb_path.with_suffix('.jsonl.backup')
    kb_path.rename(backup_path)
    print(f"\n💾 备份原文件: {backup_path}")

    # 写入清理后的条目
    with open(kb_path, 'w', encoding='utf-8') as f:
        for entry in cleaned_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"✅ 清理完成: {kb_path}")

if __name__ == "__main__":
    # 清理教案知识库
    lesson_plan_kb = Path(__file__).resolve().parent / "knowledge/lesson_plan/experiences.jsonl"

    print("=" * 80)
    print("清理教案知识库中的硬编码主题条目")
    print("=" * 80)

    clean_knowledge_base(lesson_plan_kb)

    print("\n" + "=" * 80)
    print("✅ 知识库清理完成！")
    print("=" * 80)
