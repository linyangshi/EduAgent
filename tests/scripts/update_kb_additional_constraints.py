#!/usr/bin/env python3
"""
更新知识库：添加课题名称、教学环节等字段的长度约束
"""
import json
from datetime import datetime
from pathlib import Path

# 读取现有知识库
kb_file = Path("knowledge/lesson_plan/experiences.jsonl")
experiences = []

if kb_file.exists():
    with open(kb_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    experiences.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"⚠️  跳过损坏的行: {e}")
                    continue

print(f"现有经验条数: {len(experiences)}")

# 添加新的约束规则
new_experience = {
    "timestamp": datetime.now().isoformat(),
    "doc_type": "lesson_plan",
    "severity": "high",
    "annotator_prompts": [],
    "generator_prompts": [
        {
            "prompt": "【课题/标题字段特殊约束】对于包含'课题''标题''title''名称'等关键词的字段：\n1. 必须控制在5-30字符\n2. 只写核心主题，不添加背景、理由、目标等描述\n3. 示例：'Python基础：变量与数据类型'（正确）\n4. 示例：'在2023级课程框架下由张老师承担的Python基础...'（错误，太长）",
            "reason": "课题名称字段生成了485字符的长篇描述，需要严格限制",
            "root_cause": "generator"
        },
        {
            "prompt": "【教学环节字段约束】对于包含'teaching_step''教学环节''环节'等关键词的字段：\n1. 控制在10-50字符\n2. 只写环节名称，不写具体步骤\n3. 示例：'导入新课'（正确）、'知识讲解'（正确）\n4. 示例：'张伟老师首先将全班2023级同学按4人一组...'（错误，太详细）",
            "reason": "教学环节字段生成了280+字符的详细步骤描述，应该只是简短环节名",
            "root_cause": "generator"
        },
        {
            "prompt": "【内容主题一致性】生成所有字段内容时，必须严格遵循用户需求(user_requirement)中指定的主题：\n1. 仔细阅读user_requirement，提取核心主题关键词\n2. 所有字段内容必须围绕该主题展开\n3. 示例：如果requirement是'Python基础-变量和数据类型'，不要生成'卷积神经网络CNN'相关内容\n4. 板书设计、教学目标、教学过程等所有字段都要保持主题一致",
            "reason": "用户要求生成Python基础内容，但实际生成了CNN神经网络内容，主题完全偏离",
            "root_cause": "generator"
        },
        {
            "prompt": "【字段名称模式识别增强】识别特定模式的字段名：\n- 包含'title'/'名称'/'课题' → 5-30字\n- 包含'step'/'环节' → 10-50字  \n- 包含'name'/'姓名' → 2-10字\n- 包含'activity'/'活动' → 30-150字\n- 包含'design'/'设计'/'analysis'/'分析' → 100-300字\n- 包含'process'/'过程' → 200-500字",
            "reason": "需要更细粒度的字段类型识别规则",
            "root_cause": "generator"
        }
    ],
    "key_insights": [
        "课题名称类字段必须5-30字，只写核心主题",
        "教学环节类字段必须10-50字，只写环节名称不写详细步骤",
        "必须严格遵循user_requirement中的主题，保持所有字段内容一致性"
    ],
    "next_steps": [
        "生成前先提取user_requirement的核心主题",
        "根据字段名模式判断合适的长度范围",
        "生成后自检内容是否与主题一致"
    ]
}

# 添加到经验列表
experiences.append(new_experience)

# 写回文件
with open(kb_file, 'w', encoding='utf-8') as f:
    for exp in experiences:
        f.write(json.dumps(exp, ensure_ascii=False) + '\n')

print(f"✅ 已添加课题名称和教学环节约束规则")
print(f"更新后经验条数: {len(experiences)}")
print("\n新增规则内容:")
for i, prompt in enumerate(new_experience['generator_prompts'], 1):
    print(f"\n{i}. {prompt['prompt'][:80]}...")
    print(f"   原因: {prompt['reason']}")
