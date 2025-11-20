#!/usr/bin/env python3
"""
更新知识库：添加字段长度控制规则
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
                experiences.append(json.loads(line))

print(f"现有经验条数: {len(experiences)}")

# 添加新的字段长度控制规则
new_experience = {
    "timestamp": datetime.now().isoformat(),
    "doc_type": "lesson_plan",
    "severity": "high",
    "annotator_prompts": [],
    "generator_prompts": [
        {
            "prompt": "【字段类型识别】根据字段名称和位置判断字段类型：\\n- 基础信息字段（如：姓名、教师、年级、班级、学科、地市、区县、单位、日期、学时等）→ 2-20字\\n- 内容字段（如：教学目标、教学重点、教学难点、教学过程、教学反思等）→ 100-500字\\n- 标题字段（如：课程名称、教材版本、章节标题等）→ 5-30字",
            "reason": "LLM需要明确的字段分类规则来判断生成内容的长度",
            "root_cause": "generator"
        },
        {
            "prompt": "【基础信息字段严格约束】对于姓名、年级、学科、地市区县、工作单位等基础信息字段：\\n1. 只填写事实信息，不要添加任何描述、解释或背景\\n2. 严格控制在2-20字符以内\\n3. 示例：姓名应该是'张三'而不是'张三博士从事...'\\n4. 示例：年级应该是'2023级'而不是'本课程面向专业的...'",
            "reason": "避免基础信息字段被填充大段描述性文字",
            "root_cause": "generator"
        },
        {
            "prompt": "【表格单元格字段识别】如果字段出现在文档表格的前几行，特别是表头附近的单元格，这通常是基础信息字段，必须简短（2-20字）。不要为表格单元格生成段落性的描述文本。",
            "reason": "表格单元格通常是基础信息，需要简洁",
            "root_cause": "generator"
        },
        {
            "prompt": "【常见错误示例】\\n错误：姓名字段生成'张伟博士现任某重点大学...'\\n正确：姓名字段生成'张伟'\\n错误：地市区县生成'在本课程的设计中district字段...'\\n正确：地市区县生成'海淀区'\\n错误：年级生成'本课程面向计算机专业的高年级本科生...'\\n正确：年级生成'大三'或'2023级'",
            "reason": "通过反例帮助LLM理解正确的生成方式",
            "root_cause": "generator"
        }
    ],
    "key_insights": [
        "基础信息字段（姓名、年级、学科等）必须简短（2-20字），只填写事实，不添加描述"
    ],
    "next_steps": [
        "在生成前先判断字段类型",
        "基础信息字段严格限制长度",
        "避免在简短字段中生成描述性段落"
    ]
}

# 添加到经验列表
experiences.append(new_experience)

# 写回文件
with open(kb_file, 'w', encoding='utf-8') as f:
    for exp in experiences:
        f.write(json.dumps(exp, ensure_ascii=False) + '\\n')

print(f"✅ 已添加新的字段长度控制规则")
print(f"更新后经验条数: {len(experiences)}")
print("\\n新增规则内容:")
for i, prompt in enumerate(new_experience['generator_prompts'], 1):
    print(f"\\n{i}. {prompt['prompt'][:80]}...")
