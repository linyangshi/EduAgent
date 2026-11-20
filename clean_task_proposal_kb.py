#!/usr/bin/env python3
"""
知识库清理脚本 - 移除任务书KB中的教案相关条目
"""
import json
import shutil
from pathlib import Path
from datetime import datetime

def clean_task_proposal_kb():
    """清理任务书知识库中的教案污染"""

    kb_path = Path("knowledge/task_proposal/experiences.jsonl")

    if not kb_path.exists():
        print(f"❌ 知识库文件不存在: {kb_path}")
        return

    # 备份原始文件
    backup_path = kb_path.with_suffix(f'.jsonl.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
    shutil.copy2(kb_path, backup_path)
    print(f"✅ 已备份原始文件: {backup_path}")

    # 教学相关关键词(教案特征)
    lesson_keywords = [
        "教学设计", "教学目标", "教学重点", "教学难点",
        "教学过程", "教学方法", "教学资源", "教学实施",
        "单次授课", "授课单元", "课堂活动", "教学活动",
        "教案", "课程设计", "教学计划"
    ]

    # 读取所有条目
    entries = []
    with open(kb_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    print(f"\n📊 原始条目数: {len(entries)}")

    # 过滤污染条目
    clean_entries = []
    removed_entries = []

    for entry in entries:
        entry_text = json.dumps(entry, ensure_ascii=False)

        # 检查是否包含教学关键词
        is_contaminated = any(keyword in entry_text for keyword in lesson_keywords)

        if is_contaminated:
            removed_entries.append(entry)
            print(f"\n🗑️  移除污染条目:")
            print(f"   时间戳: {entry.get('timestamp', 'N/A')}")

            # 显示包含的关键词
            found_keywords = [kw for kw in lesson_keywords if kw in entry_text]
            print(f"   包含关键词: {', '.join(found_keywords[:5])}")

            # 显示部分prompt示例
            if 'generator_prompts' in entry and entry['generator_prompts']:
                sample_prompt = entry['generator_prompts'][0]['prompt'][:50]
                print(f"   示例prompt: {sample_prompt}...")
        else:
            clean_entries.append(entry)

    print(f"\n📊 清理后条目数: {len(clean_entries)}")
    print(f"📊 移除条目数: {len(removed_entries)}")

    # 写入清理后的数据
    if len(clean_entries) < len(entries):
        with open(kb_path, 'w', encoding='utf-8') as f:
            for entry in clean_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

        print(f"\n✅ 知识库已清理!")
        print(f"✅ 备份文件: {backup_path}")
        print(f"✅ 原始条目: {len(entries)} → 清理后: {len(clean_entries)}")

        # 显示保留条目的概要
        if clean_entries:
            print(f"\n📋 保留的条目:")
            for i, entry in enumerate(clean_entries, 1):
                timestamp = entry.get('timestamp', 'N/A')
                severity = entry.get('severity', 'unknown')
                gen_count = len(entry.get('generator_prompts', []))
                ann_count = len(entry.get('annotator_prompts', []))
                print(f"   {i}. {timestamp} | {severity} | gen:{gen_count} ann:{ann_count}")
    else:
        print("\n✅ 未发现教学相关污染,知识库干净!")

    return len(entries) - len(clean_entries)

if __name__ == "__main__":
    print("=" * 60)
    print("🧹 任务书知识库清理工具")
    print("=" * 60)

    removed_count = clean_task_proposal_kb()

    print("\n" + "=" * 60)
    print(f"🎉 清理完成! 共移除 {removed_count} 条污染条目")
    print("=" * 60)
