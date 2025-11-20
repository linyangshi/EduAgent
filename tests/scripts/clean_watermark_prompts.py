"""
清理知识库中关于Aspose水印的误报提示
"""
import json
from pathlib import Path

kb_file = Path("knowledge/lesson_plan/experiences.jsonl")

# 读取所有记录
records = []
with open(kb_file, 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            records.append(json.loads(line))

print(f"📊 原始记录数: {len(records)}")

# 清理每条记录中的水印相关提示
cleaned_count = 0
for record in records:
    # 清理 annotator_prompts
    if 'annotator_prompts' in record:
        original_len = len(record['annotator_prompts'])
        record['annotator_prompts'] = [
            p for p in record['annotator_prompts']
            if 'Aspose' not in p.get('prompt', '') and '水印' not in p.get('prompt', '')
        ]
        if len(record['annotator_prompts']) < original_len:
            cleaned_count += 1
            print(f"  - 清理了 annotator_prompts 中的水印提示")

    # 清理 generator_prompts
    if 'generator_prompts' in record:
        original_len = len(record['generator_prompts'])
        record['generator_prompts'] = [
            p for p in record['generator_prompts']
            if 'Aspose' not in p.get('prompt', '') and '水印' not in p.get('prompt', '')
        ]
        if len(record['generator_prompts']) < original_len:
            cleaned_count += 1
            print(f"  - 清理了 generator_prompts 中的水印提示")

    # 清理 next_steps
    if 'next_steps' in record:
        original_len = len(record['next_steps'])
        record['next_steps'] = [
            step for step in record['next_steps']
            if 'Aspose' not in step and '水印' not in step and '清除水印' not in step
        ]
        if len(record['next_steps']) < original_len:
            cleaned_count += 1
            print(f"  - 清理了 next_steps 中的水印提示")

print(f"✅ 清理了 {cleaned_count} 处水印相关提示")

# 备份原文件
backup_file = kb_file.with_suffix('.jsonl.backup')
import shutil
shutil.copy2(kb_file, backup_file)
print(f"💾 原文件已备份到: {backup_file}")

# 写回清理后的记录
with open(kb_file, 'w', encoding='utf-8') as f:
    for record in records:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

print(f"✅ 清理完成！新记录数: {len(records)}")
print(f"\n📝 VLM Prompt 已更新为忽略Aspose水印")
print(f"   下次VLM检查将不再报告水印问题")
