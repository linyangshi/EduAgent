#!/usr/bin/env python3
"""
清理知识库中过于具体的CNN建议

策略：只删除明确提到"卷积神经网络"的VLM建议，
保留抽象的、通用的约束建议
"""

import json
from pathlib import Path

def clean_cnn_suggestions(kb_path: Path):
    """清理CNN相关的VLM建议"""

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

    # 清理每条条目的generator_prompts
    cleaned_entries = []
    total_removed = 0

    for entry in entries:
        cleaned_entry = entry.copy()

        # 清理generator_prompts
        if 'generator_prompts' in cleaned_entry:
            original_prompts = cleaned_entry['generator_prompts']

            # 删除包含"卷积神经网络"的建议（检查prompt和reason字段）
            cleaned_prompts = []
            for p in original_prompts:
                prompt_text = p.get('prompt', '')
                reason_text = p.get('reason', '')

                # 如果是VLM建议且包含"卷积神经网络"，删除
                if p.get('root_cause') == 'vlm' and '卷积神经网络' in prompt_text:
                    continue

                # 如果reason中包含"卷积神经网络"作为负面示例，保留
                # 如果reason中包含"卷积神经网络"作为正面案例，删除
                if '卷积神经网络' in reason_text:
                    # 保留作为负面示例的（如"不要写成..."）
                    if '不要' in reason_text or '避免' in reason_text:
                        cleaned_prompts.append(p)
                    # 删除作为正面案例的
                    else:
                        continue
                else:
                    cleaned_prompts.append(p)

            removed = len(original_prompts) - len(cleaned_prompts)
            if removed > 0:
                print(f"   🗑️  条目 {entry.get('timestamp', 'unknown')}: 删除 {removed} 条CNN VLM建议")
                total_removed += removed

            cleaned_entry['generator_prompts'] = cleaned_prompts

        # 保留所有条目（即使generator_prompts为空）
        cleaned_entries.append(cleaned_entry)

    print(f"\n📊 清理后条目数: {len(cleaned_entries)}")
    print(f"🗑️  共删除 {total_removed} 条CNN VLM建议")

    # 备份原文件
    backup_path = kb_path.with_suffix('.jsonl.cnn_backup')
    import shutil
    shutil.copy(kb_path, backup_path)
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
    print("清理教案知识库中的CNN具体建议")
    print("=" * 80)

    clean_cnn_suggestions(lesson_plan_kb)

    print("\n" + "=" * 80)
    print("✅ 知识库清理完成！")
    print("=" * 80)
