"""
字段约束定义 - 为不同文档类型的字段定义强制约束规则
"""

from typing import Dict, Any, Optional, List
import re


# 任务书字段约束定义
TASK_PROPOSAL_CONSTRAINTS = {
    # 基础信息字段 - 应该简短
    "college": {
        "type": "basic_info",
        "min_chars": 5,
        "max_chars": 20,
        "example": "计算机科学与技术学院",
        "description": "二级学院名称",
        "validation_rules": [
            {"type": "length", "max": 20, "message": "学院名称不应超过20字符"},
            {"type": "no_description", "message": "只填写学院名称，不要添加描述性内容"},
        ]
    },
    "major": {
        "type": "basic_info",
        "min_chars": 2,
        "max_chars": 15,
        "example": "人工智能",
        "description": "专业名称",
        "validation_rules": [
            {"type": "length", "max": 15, "message": "专业名称不应超过15字符"},
        ]
    },
    "grade_class": {
        "type": "basic_info",
        "min_chars": 5,
        "max_chars": 20,
        "example": "2023级1班",
        "description": "年级班级",
        "validation_rules": [
            {"type": "length", "max": 20, "message": "年级班级不应超过20字符"},
        ]
    },
    "student_name": {
        "type": "basic_info",
        "min_chars": 2,
        "max_chars": 10,
        "example": "张三",
        "description": "学生姓名",
        "validation_rules": [
            {"type": "length", "max": 10, "message": "姓名不应超过10字符"},
        ]
    },
    "student_id": {
        "type": "basic_info",
        "min_chars": 8,
        "max_chars": 15,
        "example": "2023010101",
        "description": "学号",
        "validation_rules": [
            {"type": "length", "max": 15, "message": "学号不应超过15字符"},
        ]
    },
    "thesis_title": {
        "type": "basic_info",
        "min_chars": 10,
        "max_chars": 50,
        "example": "基于卷积神经网络的图像分类算法研究",
        "description": "论文题目",
        "validation_rules": [
            {"type": "length", "min": 10, "max": 50, "message": "题目应在10-50字符之间"},
            {"type": "no_filler_words", "message": "题目应简洁明了，避免冗长描述"},
        ]
    },
    "title": {  # 添加title别名，与标注器输出的placeholder匹配
        "type": "basic_info",
        "min_chars": 10,
        "max_chars": 50,
        "example": "基于卷积神经网络的图像分类算法研究",
        "description": "论文题目",
        "validation_rules": [
            {"type": "length", "min": 10, "max": 50, "message": "题目应在10-50字符之间"},
            {"type": "no_filler_words", "message": "题目应简洁明了，避免冗长描述"},
        ]
    },

    # 内容字段 - 应该详细
    # 🔥 知识库优先：任务书要求目的与意义约800字，构思与内容约800字
    "purpose_significance": {
        "type": "content",
        "min_chars": 600,  # 知识库要求800字，允许600-1000范围
        "max_chars": 1000,
        "example": "本研究旨在...具有重要的理论价值和实践意义...",
        "description": "研究目的与意义",
        "validation_rules": [
            {"type": "length", "min": 600, "max": 1000, "message": "目的与意义应在600-1000字符之间（任务书约800字）"},
            {"type": "must_include", "keywords": ["研究", "目的", "意义"], "message": "必须包含研究目的和意义的描述"},
        ]
    },
    "purpose_and_significance": {  # 添加别名，匹配标注器输出
        "type": "content",
        "min_chars": 600,
        "max_chars": 1000,
        "example": "本研究旨在...具有重要的理论价值和实践意义...",
        "description": "研究目的与意义",
        "validation_rules": [
            {"type": "length", "min": 600, "max": 1000, "message": "目的与意义应在600-1000字符之间（任务书约800字）"},
            {"type": "must_include", "keywords": ["研究", "目的", "意义"], "message": "必须包含研究目的和意义的描述"},
        ]
    },
    "conception_content": {
        "type": "content",
        "min_chars": 600,  # 知识库要求800字，允许600-1000范围
        "max_chars": 1000,
        "example": "本研究拟采用...技术路线如下...预期成果包括...",
        "description": "研究构思与内容",
        "validation_rules": [
            {"type": "length", "min": 600, "max": 1000, "message": "构思与内容应在600-1000字符之间（任务书约800字）"},
            {"type": "must_include", "keywords": ["方法", "技术", "实验"], "message": "必须包含研究方法和技术路线"},
        ]
    },
    "conception_and_content": {  # 添加别名，匹配标注器输出
        "type": "content",
        "min_chars": 600,
        "max_chars": 1000,
        "example": "本研究拟采用...技术路线如下...预期成果包括...",
        "description": "研究构思与内容",
        "validation_rules": [
            {"type": "length", "min": 600, "max": 1000, "message": "构思与内容应在600-1000字符之间（任务书约800字）"},
            {"type": "must_include", "keywords": ["方法", "技术", "实验"], "message": "必须包含研究方法和技术路线"},
        ]
    },
    "references": {
        "type": "content",
        "min_chars": 300,
        "max_chars": 1000,
        "min_items": 5,
        "max_items": 10,
        "example": "[1] 作者. 论文标题[J]. 期刊名, 年份, 卷(期): 页码.\n[2] ...",
        "description": "参考文献",
        "validation_rules": [
            {"type": "length", "min": 300, "message": "参考文献总长度应不少于300字符"},
            {"type": "item_count", "min": 5, "message": "至少包含5条参考文献"},
            {"type": "format", "pattern": r"\[\d+\].*?[.\n]", "message": "参考文献应按[1] [2]等格式编号"},
        ]
    },

    "schedule_plan": {
        "type": "content",
        "min_chars": 300,
        "max_chars": 500,
        "example": "第1-2周：文献调研与综述撰写\n第3-4周：开题报告准备与答辩\n第5-8周：实验设计与数据采集\n第9-12周：论文撰写与修改\n第13-14周：论文定稿与答辩准备",
        "description": "论文进度计划",
        "validation_rules": [
            {"type": "length", "min": 300, "max": 500, "message": "进度计划应在300-500字符之间"},
            {"type": "must_include", "keywords": ["周", "月"], "message": "必须包含明确的时间节点"},
        ]
    },

    # 时间信息字段
    "supervisor_signature_date": {
        "type": "time_info",
        "min_chars": 8,
        "max_chars": 20,
        "example": "2025年10月28日",
        "description": "指导教师签名日期",
        "validation_rules": [
            {"type": "length", "max": 20, "message": "日期不应超过20字符"},
        ]
    },
    "director_signature_date": {
        "type": "time_info",
        "min_chars": 8,
        "max_chars": 20,
        "example": "2025年10月28日",
        "description": "系主任签名日期",
        "validation_rules": [
            {"type": "length", "max": 20, "message": "日期不应超过20字符"},
        ]
    },
}


# 教案字段约束定义
LESSON_PLAN_CONSTRAINTS = {
    # 基础信息字段 - 应该简短
    "teacher_name": {
        "type": "basic_info",
        "min_chars": 2,
        "max_chars": 10,
        "example": "李明",
        "description": "教师姓名",
        "validation_rules": [
            {"type": "length", "max": 10, "message": "教师姓名不应超过10字符"},
            {"type": "no_description", "message": "只填写姓名，不要添加职称、单位等描述"},
        ]
    },
    "grade": {
        "type": "basic_info",
        "min_chars": 3,
        "max_chars": 15,
        "example": "2024级",
        "description": "年级",
        "validation_rules": [
            {"type": "length", "max": 15, "message": "年级不应超过15字符"},
        ]
    },
    "grade_level": {  # 别名
        "type": "basic_info",
        "min_chars": 3,
        "max_chars": 15,
        "example": "2024级",
        "description": "年级",
        "validation_rules": [
            {"type": "length", "max": 15, "message": "年级不应超过15字符"},
        ]
    },
    "city_county": {
        "type": "basic_info",
        "min_chars": 2,
        "max_chars": 20,
        "example": "海淀区",
        "description": "地市区县",
        "validation_rules": [
            {"type": "length", "max": 20, "message": "地市区县不应超过20字符"},
        ]
    },
    "district_county": {  # 别名
        "type": "basic_info",
        "min_chars": 2,
        "max_chars": 20,
        "example": "海淀区",
        "description": "地市区县",
        "validation_rules": [
            {"type": "length", "max": 20, "message": "地市区县不应超过20字符"},
        ]
    },
    "work_unit": {
        "type": "basic_info",
        "min_chars": 3,
        "max_chars": 30,
        "example": "北京市第一中学",
        "description": "工作单位",
        "validation_rules": [
            {"type": "length", "max": 30, "message": "工作单位不应超过30字符"},
        ]
    },
    "subject": {
        "type": "basic_info",
        "min_chars": 2,
        "max_chars": 20,
        "example": "人工智能导论",
        "description": "学科/科目",
        "validation_rules": [
            {"type": "length", "max": 20, "message": "学科名称不应超过20字符"},
        ]
    },
    "textbook_version": {
        "type": "basic_info",
        "min_chars": 5,
        "max_chars": 40,
        "example": "人民教育出版社《Python程序设计》",
        "description": "教材版本",
        "validation_rules": [
            {"type": "length", "max": 40, "message": "教材版本不应超过40字符"},
        ]
    },

    # 标题类字段 - 应该简短精炼
    "lesson_title": {
        "type": "title",
        "min_chars": 5,
        "max_chars": 30,
        "example": "Python基础：变量与数据类型",
        "description": "课题名称/课程标题",
        "validation_rules": [
            {"type": "length", "max": 30, "message": "课题名称必须控制在30字符以内"},
            {"type": "no_filler_words", "message": "课题名称应简洁明了，只写核心主题，不添加背景说明"},
        ]
    },
    "course_name": {  # 别名
        "type": "title",
        "min_chars": 2,
        "max_chars": 30,
        "example": "Python程序设计",
        "description": "课程名称",
        "validation_rules": [
            {"type": "length", "max": 30, "message": "课程名称不应超过30字符"},
        ]
    },

    # 教学环节类字段 - 应该简短
    "teaching_step_1": {
        "type": "step",
        "min_chars": 2,
        "max_chars": 50,
        "example": "导入新课",
        "description": "教学环节1",
        "validation_rules": [
            {"type": "length", "max": 50, "message": "教学环节名称不应超过50字符，只写环节名称，不写详细步骤"},
        ]
    },
    "teaching_step_2": {
        "type": "step",
        "min_chars": 2,
        "max_chars": 50,
        "example": "知识讲解",
        "description": "教学环节2",
        "validation_rules": [
            {"type": "length", "max": 50, "message": "教学环节名称不应超过50字符，只写环节名称，不写详细步骤"},
        ]
    },
    "teaching_step_3": {
        "type": "step",
        "min_chars": 2,
        "max_chars": 50,
        "example": "实践操作",
        "description": "教学环节3",
        "validation_rules": [
            {"type": "length", "max": 50, "message": "教学环节名称不应超过50字符，只写环节名称，不写详细步骤"},
        ]
    },
    "teaching_step_4": {
        "type": "step",
        "min_chars": 2,
        "max_chars": 50,
        "example": "互动练习",
        "description": "教学环节4",
        "validation_rules": [
            {"type": "length", "max": 50, "message": "教学环节名称不应超过50字符，只写环节名称，不写详细步骤"},
        ]
    },
    "teaching_step_5": {
        "type": "step",
        "min_chars": 2,
        "max_chars": 50,
        "example": "总结提升",
        "description": "教学环节5",
        "validation_rules": [
            {"type": "length", "max": 50, "message": "教学环节名称不应超过50字符，只写环节名称，不写详细步骤"},
        ]
    },

    # 内容类字段 - 应该详细
    "content_analysis": {
        "type": "content",
        "min_chars": 100,
        "max_chars": 600,
        "example": "本课是Python编程基础的第一节课...",
        "description": "教学内容分析",
        "validation_rules": [
            {"type": "length", "min": 100, "max": 600, "message": "教学内容分析应在100-600字符之间"},
        ]
    },
    "student_analysis": {
        "type": "content",
        "min_chars": 80,
        "max_chars": 300,
        "example": "学生已具备基本计算机操作能力...",
        "description": "学情分析",
        "validation_rules": [
            {"type": "length", "min": 80, "max": 300, "message": "学情分析应在80-300字符之间"},
        ]
    },
    "teaching_objectives": {
        "type": "content",
        "min_chars": 100,
        "max_chars": 400,
        "example": "1.知识目标：掌握Python变量的概念...\n2.能力目标：能够...\n3.情感目标：培养...",
        "description": "教学目标",
        "validation_rules": [
            {"type": "length", "min": 100, "max": 400, "message": "教学目标应在100-400字符之间"},
        ]
    },
    "key_difficult_points": {
        "type": "content",
        "min_chars": 50,
        "max_chars": 300,
        "example": "教学重点：变量的赋值与使用\n教学难点：数据类型的理解与转换",
        "description": "教学重点难点",
        "validation_rules": [
            {"type": "length", "min": 50, "max": 300, "message": "教学重点难点应在50-300字符之间"},
        ]
    },
    "teaching_strategy": {
        "type": "content",
        "min_chars": 100,
        "max_chars": 400,
        "example": "本课采用任务驱动法，结合实际案例...",
        "description": "教学策略",
        "validation_rules": [
            {"type": "length", "min": 100, "max": 400, "message": "教学策略应在100-400字符之间"},
        ]
    },
    "blackboard_design": {
        "type": "content",
        "min_chars": 50,
        "max_chars": 300,
        "example": "一、变量的概念\n   1. 变量名\n   2. 赋值\n二、数据类型\n   1. 整型\n   2. 浮点型\n   3. 字符串",
        "description": "板书设计",
        "validation_rules": [
            {"type": "length", "min": 50, "max": 300, "message": "板书设计应在50-300字符之间"},
        ]
    },
    "post_lesson_reflection": {
        "type": "content",
        "min_chars": 100,
        "max_chars": 400,
        "example": "本节课通过实际案例，学生能够较好地理解变量概念...",
        "description": "课后反思",
        "validation_rules": [
            {"type": "length", "min": 100, "max": 400, "message": "课后反思应在100-400字符之间"},
        ]
    },
    "after_class_reflection": {  # 别名
        "type": "content",
        "min_chars": 100,
        "max_chars": 400,
        "example": "本节课通过实际案例，学生能够较好地理解变量概念...",
        "description": "课后反思",
        "validation_rules": [
            {"type": "length", "min": 100, "max": 400, "message": "课后反思应在100-400字符之间"},
        ]
    },
    "teaching_evaluation": {
        "type": "content",
        "min_chars": 100,
        "max_chars": 600,
        "example": "本节课采用形成性评价与终结性评价相结合...",
        "description": "教学评价设计",
        "validation_rules": [
            {"type": "length", "min": 100, "max": 600, "message": "教学评价设计应在100-600字符之间"},
        ]
    },

    # 活动类字段 - 中等长度
    "teacher_activity_1": {
        "type": "activity",
        "min_chars": 30,
        "max_chars": 200,
        "example": "教师展示PPT，引导学生思考变量的作用...",
        "description": "教师活动1",
        "validation_rules": [
            {"type": "length", "min": 30, "max": 200, "message": "教师活动应在30-200字符之间"},
        ]
    },
    "teacher_activity_2": {
        "type": "activity",
        "min_chars": 30,
        "max_chars": 200,
        "example": "教师演示代码，讲解变量赋值过程...",
        "description": "教师活动2",
        "validation_rules": [
            {"type": "length", "min": 30, "max": 200, "message": "教师活动应在30-200字符之间"},
        ]
    },
    "teacher_activity_3": {
        "type": "activity",
        "min_chars": 30,
        "max_chars": 200,
        "example": "教师巡视指导，解答学生疑问...",
        "description": "教师活动3",
        "validation_rules": [
            {"type": "length", "min": 30, "max": 200, "message": "教师活动应在30-200字符之间"},
        ]
    },
    "teacher_activity_4": {
        "type": "activity",
        "min_chars": 30,
        "max_chars": 200,
        "example": "教师组织讨论，总结知识点...",
        "description": "教师活动4",
        "validation_rules": [
            {"type": "length", "min": 30, "max": 200, "message": "教师活动应在30-200字符之间"},
        ]
    },
    "teacher_activity_5": {
        "type": "activity",
        "min_chars": 30,
        "max_chars": 200,
        "example": "教师布置作业，提出要求...",
        "description": "教师活动5",
        "validation_rules": [
            {"type": "length", "min": 30, "max": 200, "message": "教师活动应在30-200字符之间"},
        ]
    },
    "student_activity_1": {
        "type": "activity",
        "min_chars": 30,
        "max_chars": 250,
        "example": "学生观看演示，记录要点，尝试编写简单的变量赋值代码...",
        "description": "学生活动1",
        "validation_rules": [
            {"type": "length", "min": 30, "max": 250, "message": "学生活动应在30-250字符之间"},
        ]
    },
    "student_activity_2": {
        "type": "activity",
        "min_chars": 30,
        "max_chars": 250,
        "example": "学生分组讨论，完成练习任务...",
        "description": "学生活动2",
        "validation_rules": [
            {"type": "length", "min": 30, "max": 250, "message": "学生活动应在30-250字符之间"},
        ]
    },
    "student_activity_3": {
        "type": "activity",
        "min_chars": 30,
        "max_chars": 250,
        "example": "学生独立完成编程练习，互相检查代码...",
        "description": "学生活动3",
        "validation_rules": [
            {"type": "length", "min": 30, "max": 250, "message": "学生活动应在30-250字符之间"},
        ]
    },
    "student_activity_4": {
        "type": "activity",
        "min_chars": 30,
        "max_chars": 250,
        "example": "学生展示作品，分享学习心得...",
        "description": "学生活动4",
        "validation_rules": [
            {"type": "length", "min": 30, "max": 250, "message": "学生活动应在30-250字符之间"},
        ]
    },
    "student_activity_5": {
        "type": "activity",
        "min_chars": 30,
        "max_chars": 250,
        "example": "学生总结本节课所学，完成课堂测验...",
        "description": "学生活动5",
        "validation_rules": [
            {"type": "length", "min": 30, "max": 250, "message": "学生活动应在30-250字符之间"},
        ]
    },

    # 设计意图类字段 - 简短
    "design_intent_1": {
        "type": "design",
        "min_chars": 20,
        "max_chars": 150,
        "example": "通过实际案例导入，激发学生学习兴趣",
        "description": "设计意图1",
        "validation_rules": [
            {"type": "length", "min": 20, "max": 150, "message": "设计意图应在20-150字符之间"},
        ]
    },
    "design_intent_2": {
        "type": "design",
        "min_chars": 20,
        "max_chars": 150,
        "example": "通过演示帮助学生理解抽象概念",
        "description": "设计意图2",
        "validation_rules": [
            {"type": "length", "min": 20, "max": 150, "message": "设计意图应在20-150字符之间"},
        ]
    },
    "design_intent_3": {
        "type": "design",
        "min_chars": 20,
        "max_chars": 150,
        "example": "通过分组合作培养协作能力",
        "description": "设计意图3",
        "validation_rules": [
            {"type": "length", "min": 20, "max": 150, "message": "设计意图应在20-150字符之间"},
        ]
    },
    "design_intent_4": {
        "type": "design",
        "min_chars": 20,
        "max_chars": 150,
        "example": "通过实践巩固所学知识",
        "description": "设计意图4",
        "validation_rules": [
            {"type": "length", "min": 20, "max": 150, "message": "设计意图应在20-150字符之间"},
        ]
    },
    "design_intent_5": {
        "type": "design",
        "min_chars": 20,
        "max_chars": 150,
        "example": "通过总结帮助学生形成知识体系",
        "description": "设计意图5",
        "validation_rules": [
            {"type": "length", "min": 20, "max": 150, "message": "设计意图应在20-150字符之间"},
        ]
    },
}


# 文档类型到约束映射
DOCUMENT_TYPE_CONSTRAINTS = {
    "task_proposal": TASK_PROPOSAL_CONSTRAINTS,
    "lesson_plan": LESSON_PLAN_CONSTRAINTS,
}


class FieldConstraintValidator:
    """字段约束验证器"""

    def __init__(self, doc_type: str = "task_proposal"):
        self.doc_type = doc_type
        self.constraints = DOCUMENT_TYPE_CONSTRAINTS.get(doc_type, {})

    def get_constraint(self, placeholder: str) -> Optional[Dict[str, Any]]:
        """
        获取字段约束（支持智能匹配）

        匹配策略：
        1. 直接匹配：placeholder完全相同
        2. 别名匹配：导入standard_fields的别名表
        3. 模糊匹配：去掉下划线后包含关系

        Args:
            placeholder: 字段占位符名称

        Returns:
            字段约束字典，如果未找到返回None
        """
        # 1. 直接匹配
        if placeholder in self.constraints:
            return self.constraints[placeholder]

        # 2. 尝试导入别名表进行匹配
        try:
            from ..standard_fields import FIELD_ALIASES, get_standard_field_name

            # 2.1 使用归一化函数
            standard_name = get_standard_field_name(placeholder, self.doc_type)
            if standard_name != placeholder and standard_name in self.constraints:
                print(f"   🔄 字段归一化: {placeholder} → {standard_name}")
                return self.constraints[standard_name]

            # 2.2 使用别名映射
            for std_name, aliases in FIELD_ALIASES.items():
                if placeholder in aliases and std_name in self.constraints:
                    print(f"   🔄 别名匹配: {placeholder} → {std_name}")
                    return self.constraints[std_name]
        except ImportError:
            pass  # standard_fields不存在，跳过

        # 3. 模糊匹配（去掉下划线后比较）
        placeholder_clean = placeholder.replace("_", "").lower()
        for constraint_name in self.constraints:
            constraint_clean = constraint_name.replace("_", "").lower()

            # 包含关系匹配
            if (placeholder_clean in constraint_clean or
                constraint_clean in placeholder_clean):
                print(f"   🔄 模糊匹配: {placeholder} → {constraint_name}")
                return self.constraints[constraint_name]

        # 4. 未找到匹配
        return None

    def validate(self, placeholder: str, content: str) -> Dict[str, Any]:
        """
        验证字段内容是否符合约束

        Returns:
            {
                "passed": bool,
                "issues": List[str],
                "score": float  # 0.0-1.0
            }
        """
        constraint = self.get_constraint(placeholder)
        if not constraint:
            # 未定义约束，通过
            return {"passed": True, "issues": [], "score": 1.0}

        issues = []

        # 执行验证规则
        for rule in constraint.get("validation_rules", []):
            rule_type = rule.get("type")

            if rule_type == "length":
                min_len = rule.get("min", 0)
                max_len = rule.get("max", float('inf'))
                content_len = len(content)

                if content_len < min_len:
                    issues.append(f"{rule.get('message', '长度不足')}: 当前{content_len}字符，要求至少{min_len}字符")
                elif content_len > max_len:
                    issues.append(f"{rule.get('message', '长度超限')}: 当前{content_len}字符，要求最多{max_len}字符")

            elif rule_type == "item_count":
                # 统计列表项数量（如参考文献条数）
                items = re.findall(r'\[\d+\]', content)
                item_count = len(items)
                min_count = rule.get("min", 0)

                if item_count < min_count:
                    issues.append(f"{rule.get('message', '数量不足')}: 当前{item_count}条，要求至少{min_count}条")

            elif rule_type == "must_include":
                keywords = rule.get("keywords", [])
                missing_keywords = [kw for kw in keywords if kw not in content]

                if missing_keywords:
                    issues.append(f"{rule.get('message', '缺少关键词')}: 缺少 {', '.join(missing_keywords)}")

            elif rule_type == "format":
                pattern = rule.get("pattern")
                if pattern and not re.search(pattern, content):
                    issues.append(rule.get('message', '格式不符合要求'))

            elif rule_type == "no_description":
                # 检查是否包含描述性词汇（如"依托"、"聚焦"等）
                descriptive_words = ["依托", "聚焦", "拥有", "提供", "建设点", "前沿研究", "超算中心"]
                if any(word in content for word in descriptive_words):
                    issues.append(rule.get('message', '不应包含描述性内容'))

            elif rule_type == "no_filler_words":
                # 检查是否包含冗余词汇
                filler_phrases = ["以", "为核心", "协同优化", "并在", "上验证"]
                filler_count = sum(1 for phrase in filler_phrases if phrase in content)
                if filler_count >= 3:
                    issues.append(rule.get('message', '题目过于冗长'))

        # 计算得分
        if not issues:
            score = 1.0
        else:
            score = max(0.0, 1.0 - 0.2 * len(issues))

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "score": score
        }

    def format_constraint_for_prompt(self, placeholder: str) -> str:
        """将约束格式化为提示词片段"""
        constraint = self.get_constraint(placeholder)
        if not constraint:
            return ""

        parts = []
        parts.append(f"**{placeholder}** ({constraint.get('description', '')})")
        parts.append(f"  - 类型: {constraint.get('type', 'content')}")
        parts.append(f"  - 长度: {constraint.get('min_chars', 0)}-{constraint.get('max_chars', 500)}字符")

        if constraint.get('min_items'):
            parts.append(f"  - 数量: 至少{constraint.get('min_items')}条")

        if constraint.get('example'):
            parts.append(f"  - 示例: {constraint.get('example')}")

        # 添加验证规则作为强制要求
        rules = constraint.get('validation_rules', [])
        if rules:
            parts.append("  - 强制要求:")
            for rule in rules:
                msg = rule.get('message', '')
                if msg:
                    parts.append(f"    ✓ {msg}")

        return "\n".join(parts)


def _extract_position_from_marker(marker: str) -> Optional[Dict]:
    """
    从marker字符串提取位置信息

    Args:
        marker: DOCX-CELL标记，如 "[[DOCX-CELL table=T0000 row=2 grid_col=0 ...]]"

    Returns:
        位置信息字典，包含col_index, row_index, table_id, is_first_column
    """
    if not marker or "DOCX-CELL" not in marker:
        return None

    col_match = re.search(r'grid_col=(\d+)', marker)
    row_match = re.search(r'row=(\d+)', marker)
    table_match = re.search(r'table=([A-Z0-9]+)', marker)

    if col_match and row_match and table_match:
        col_index = int(col_match.group(1))
        return {
            "col_index": col_index,
            "row_index": int(row_match.group(1)),
            "table_id": table_match.group(1),
            "is_first_column": (col_index == 0),
        }

    return None


def _build_position_hint_simple(field_analysis: Dict) -> str:
    """
    构建简化的位置提示文本（只显示位置信息和关键提示）

    Args:
        field_analysis: 字段分析结果（包含annotation）

    Returns:
        位置提示字符串
    """
    annotation = field_analysis.get("annotation", {})
    # 🔥 修复：优先使用 cell_marker，如果不存在再使用 marker
    marker = annotation.get("cell_marker", "") or annotation.get("marker", "")

    pos_info = _extract_position_from_marker(marker)
    if not pos_info:
        return ""

    table_id = pos_info["table_id"]
    row_idx = pos_info["row_index"]
    col_idx = pos_info["col_index"]
    is_first_col = pos_info["is_first_column"]

    # 基本位置信息
    hint = f"位置: 表格 {table_id} 第{row_idx+1}行 第{col_idx+1}列"

    # 如果是第一列，只标记位置，具体限制由知识库引导
    if is_first_col:
        hint += " | ⚠️ **第一列（标签列）**"

    return hint


def get_enhanced_field_constraints(
    field_analyses: list,
    doc_type: str = "task_proposal"
) -> str:
    """
    为字段列表生成增强的约束说明

    Args:
        field_analyses: 字段分析列表
        doc_type: 文档类型

    Returns:
        格式化的约束文本，可直接插入提示词
    """
    validator = FieldConstraintValidator(doc_type)

    lines = ["## 字段生成约束（必须严格遵守）", ""]

    for analysis in field_analyses:
        placeholder = analysis.get("placeholder") if isinstance(analysis, dict) else analysis.placeholder
        constraint_text = validator.format_constraint_for_prompt(placeholder)

        if constraint_text:
            lines.append(constraint_text)
            
            # 🔥 添加位置信息
            position_hint = _build_position_hint_simple(analysis if isinstance(analysis, dict) else analysis.__dict__)
            if position_hint:
                lines.append(f"  - {position_hint}")
            
            lines.append("")

    # 🔥 移除硬编码的业务规则，这些应该由知识库引导
    # lines.append("**⚠️  重要提示**:")
    # lines.append("- 基础信息字段应简短明确")
    # lines.append("- 内容字段必须详细充分")
    # lines.append("- 参考文献必须至少5条")
    lines.append("")

    return "\n".join(lines)
