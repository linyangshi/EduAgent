"""
标准字段定义 - 用于标注器和约束验证的统一字段命名
"""

# 标准字段映射表（按文档类型）
STANDARD_FIELDS = {
    "task_proposal": {
        # 基础信息
        "title": "论文题目",
        "college": "二级学院",
        "major": "专业",
        "grade_class": "年级班级",
        "student_name": "学生姓名",
        "student_id": "学号",

        # 内容字段
        "purpose_significance": "研究目的与意义",
        "conception_content": "研究构思与内容",
        "references": "参考文献",

        # 时间信息
        "start_date": "开始日期",
        "end_date": "结束日期",
        "supervisor_signature_date": "指导教师签名日期",
        "director_signature_date": "系主任签名日期",

        # 进度计划
        "task_schedule_1": "进度计划第1项",
        "task_schedule_2": "进度计划第2项",
        "task_schedule_3": "进度计划第3项",
        "task_schedule_4": "进度计划第4项",
        "task_schedule_5": "进度计划第5项",
        "task_schedule_6": "进度计划第6项",
        "task_schedule_7": "进度计划第7项",
    },

    "lesson_plan": {
        # 基础信息
        "lesson_title": "课题名称",
        "course_name": "课程名称",
        "teacher_name": "教师姓名",
        "grade": "年级",
        "subject": "学科/科目",
        "textbook_version": "教材版本",
        "work_unit": "工作单位",
        "district_county": "地市区县",

        # 教学设计
        "teaching_objectives": "教学目标",
        "content_analysis": "教学内容分析",
        "student_analysis": "学情分析",
        "key_difficult_points": "教学重点难点",
        "teaching_strategy": "教学策略",

        # 教学过程
        "teaching_step_1": "教学环节1",
        "teaching_step_2": "教学环节2",
        "teaching_step_3": "教学环节3",
        "teaching_step_4": "教学环节4",
        "teaching_step_5": "教学环节5",

        "teacher_activity_1": "教师活动1",
        "teacher_activity_2": "教师活动2",
        "teacher_activity_3": "教师活动3",
        "teacher_activity_4": "教师活动4",
        "teacher_activity_5": "教师活动5",

        "student_activity_1": "学生活动1",
        "student_activity_2": "学生活动2",
        "student_activity_3": "学生活动3",
        "student_activity_4": "学生活动4",
        "student_activity_5": "学生活动5",

        "design_intent_1": "设计意图1",
        "design_intent_2": "设计意图2",
        "design_intent_3": "设计意图3",
        "design_intent_4": "设计意图4",
        "design_intent_5": "设计意图5",

        # 其他
        "blackboard_design": "板书设计",
        "post_lesson_reflection": "课后反思",
        "teaching_evaluation": "教学评价",
    }
}


# 字段别名映射（用于归一化不同的命名）
FIELD_ALIASES = {
    # 题目相关
    "title": ["title", "thesis_title", "topic", "subject_title"],

    # 姓名相关
    "student_name": ["student_name", "name", "student"],
    "teacher_name": ["teacher_name", "instructor", "teacher"],

    # 年级相关
    "grade": ["grade", "grade_level"],
    "grade_class": ["grade_class", "class"],

    # 地区相关
    "district_county": ["district_county", "city_county"],

    # 课程相关
    "lesson_title": ["lesson_title", "course_name"],

    # 教学相关
    "content_analysis": ["content_analysis", "teaching_content_analysis"],
    "key_difficult_points": ["key_difficult_points", "key_points", "difficult_points"],
    "post_lesson_reflection": ["post_lesson_reflection", "after_class_reflection"],

    # 任务书相关
    "conception_content": ["conception_content", "concept_content"],
}


def get_standard_field_name(placeholder: str, doc_type: str = "lesson_plan") -> str:
    """
    获取标准字段名

    Args:
        placeholder: 原始placeholder
        doc_type: 文档类型

    Returns:
        标准化的字段名（如果找到匹配），否则返回原名
    """
    # 1. 检查是否已经是标准字段
    if placeholder in STANDARD_FIELDS.get(doc_type, {}):
        return placeholder

    # 2. 检查别名映射
    for standard_name, aliases in FIELD_ALIASES.items():
        if placeholder in aliases:
            # 确认这个标准字段在当前文档类型中存在
            if standard_name in STANDARD_FIELDS.get(doc_type, {}):
                return standard_name

    # 3. 返回原名（未找到匹配）
    return placeholder


def create_field_mapping_prompt(doc_type: str) -> str:
    """
    创建标注器的字段映射提示

    Args:
        doc_type: 文档类型

    Returns:
        包含标准字段列表的prompt片段
    """
    standard_fields = STANDARD_FIELDS.get(doc_type, {})

    if not standard_fields:
        return ""

    prompt = f"""
## 📋 标准占位符命名规范

⚠️ 重要：请优先使用以下预定义的标准字段名，确保命名一致性：

"""

    # 按类别组织字段
    categories = {
        "基础信息": ["title", "student_name", "student_id", "teacher_name", "grade", "college", "major"],
        "教学设计": ["teaching_objectives", "content_analysis", "student_analysis", "key_difficult_points"],
        "教学过程": ["teaching_step", "teacher_activity", "student_activity", "design_intent"],
        "研究内容": ["purpose_significance", "conception_content", "references"],
    }

    for category, field_prefixes in categories.items():
        matching_fields = {k: v for k, v in standard_fields.items()
                          if any(k.startswith(prefix) for prefix in field_prefixes)}

        if matching_fields:
            prompt += f"\n### {category}\n"
            for field_name, description in matching_fields.items():
                prompt += f"- `{{{{{field_name}}}}}` : {description}\n"

    prompt += """
### 📝 命名规则

1. **优先匹配**：如果字段语义与上述标准字段相同，必须使用标准名称
   - ✅ 正确：论文题目 → `{{title}}`
   - ❌ 错误：论文题目 → `{{thesis_topic}}`

2. **自定义字段**：只有在找不到匹配时才自定义
   - 使用snake_case格式（小写+下划线）
   - 语义清晰，避免缩写
   - 示例：`{{research_background}}`

3. **序号字段**：多个同类字段用数字后缀
   - 示例：`{{task_schedule_1}}`, `{{task_schedule_2}}`
"""

    return prompt


if __name__ == "__main__":
    # 测试
    print("=== 标准字段映射测试 ===\n")

    # 测试1: 直接匹配
    print("测试1: 直接匹配")
    print(f"title → {get_standard_field_name('title', 'task_proposal')}")

    # 测试2: 别名匹配
    print("\n测试2: 别名匹配")
    print(f"thesis_title → {get_standard_field_name('thesis_title', 'task_proposal')}")
    print(f"grade_level → {get_standard_field_name('grade_level', 'lesson_plan')}")

    # 测试3: 未匹配
    print("\n测试3: 未匹配")
    print(f"custom_field → {get_standard_field_name('custom_field', 'lesson_plan')}")

    # 测试4: 生成prompt
    print("\n测试4: 生成标注prompt")
    prompt = create_field_mapping_prompt("task_proposal")
    print(prompt[:500] + "...")
