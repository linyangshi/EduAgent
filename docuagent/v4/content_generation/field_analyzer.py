"""
字段分析器 - 分析占位符需要什么样的内容
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any

from .state import FieldAnalysis


# 字段类型识别规则
FIELD_TYPE_PATTERNS = {
    "title": [
        "phase", "title", "topic", "heading", "section", "step", "stage",
        "环节", "标题", "主题", "阶段", "步骤", "章节"
    ],
    "basic_info": [
        "name", "teacher", "teacher_name", "instructor", "lecturer", "mentor", "tutor",
        "unit", "department", "school",
        "class", "grade", "semester", "year", "course_category", "category", "课程类别",
        "credit", "credits", "学分", "teaching_unit", "教学单位", "授课单位", "授课教师", "班级", "年级"
    ],
    "time_info": [
        "time", "date", "hour", "period", "week", "day", "month", "学时", "hours", "class_hours"
    ],
    "objective": [
        "objective", "goal", "target", "目标", "要求"
    ],
    "content": [
        "content", "teaching_content", "learning_content",
        "内容", "知识点", "要点"
    ],
    "method": [
        "method", "approach", "strategy", "technique",
        "方法", "策略", "手段"
    ],
    "activity": [
        "activity", "practice", "exercise", "task",
        "活动", "实践", "练习"
    ],
    "assessment": [
        "assessment", "evaluation", "test", "exam", "homework",
        "评价", "考核", "作业", "测试"
    ],
    "resource": [
        "resource", "material", "tool", "equipment", "textbook", "教材", "参考书",
        "资源", "材料", "工具"
    ],
}

# 不同字段类型的默认长度要求
DEFAULT_LENGTH_REQUIREMENTS = {
    "title": {"min_chars": 5, "max_chars": 30, "target_items": 1},
    "basic_info": {"min_chars": 2, "max_chars": 50, "target_items": 1},
    "time_info": {"min_chars": 5, "max_chars": 30, "target_items": 1},
    "objective": {"min_chars": 50, "max_chars": 300, "target_items": 3},
    "content": {"min_chars": 100, "max_chars": 500, "target_items": 1},
    "method": {"min_chars": 50, "max_chars": 200, "target_items": 1},
    "activity": {"min_chars": 100, "max_chars": 400, "target_items": 1},
    "assessment": {"min_chars": 50, "max_chars": 300, "target_items": 1},
    "resource": {"min_chars": 20, "max_chars": 100, "target_items": 1},
}

# 不同字段类型的默认生成策略
DEFAULT_GENERATION_STRATEGIES = {
    "title": "direct_mapping",
    "basic_info": "direct_mapping",
    "time_info": "format_conversion",
    "objective": "structured_list",
    "content": "paragraph_generation",
    "method": "method_suggestion",
    "activity": "activity_design",
    "assessment": "assessment_design",
    "resource": "resource_list",
}

# 字段依赖规则
DEPENDENCY_RULES = {
    "objective": ["course_name", "course_category"],
    "content": ["objective", "course_name"],
    "method": ["content", "objective"],
    "activity": ["content", "method"],
    "assessment": ["objective", "content"],
}


def _infer_length_from_kb(placeholder: str, field_type: str, doc_type: str = "lesson_plan") -> Optional[Dict[str, int]]:
    """
    方案3：从知识库学习字段长度约束
    
    Args:
        placeholder: 字段占位符
        field_type: 字段类型
        doc_type: 文档类型
    
    Returns:
        推断的长度约束，如果无法推断则返回None
    """
    try:
        # 知识库路径
        kb_dir = Path(__file__).parent.parent.parent.parent / "knowledge" / "lesson_plan"
        kb_file = kb_dir / "experiences.jsonl"
        
        if not kb_file.exists():
            return None
        
        # 收集相似字段的长度数据
        lengths = []
        placeholder_lower = placeholder.lower()
        
        with open(kb_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    
                    # 检查是否有相关字段
                    for key, value in entry.items():
                        key_lower = key.lower()
                        
                        # 语义匹配：字段名相似或类型相同
                        if (placeholder_lower in key_lower or 
                            key_lower in placeholder_lower or
                            any(kw in key_lower for kw in ["topic", "title", "课题", "标题"]) and field_type == "title"):
                            
                            if isinstance(value, str) and value.strip():
                                lengths.append(len(value.strip()))
                
                except (json.JSONDecodeError, Exception):
                    continue
        
        # 如果收集到足够的样本，计算统计量
        if len(lengths) >= 3:
            lengths.sort()
            p10 = lengths[int(len(lengths) * 0.1)]
            p90 = lengths[int(len(lengths) * 0.9)]
            median = lengths[len(lengths) // 2]
            
            print(f"   📊 从知识库学习: {placeholder} → 样本数={len(lengths)}, 中位数={median}, 范围=[{p10}, {p90}]")
            
            return {
                "min_chars": max(p10, 2),  # 至少2字符
                "max_chars": min(p90, 1000),  # 最多1000字符
                "target_items": 1,
            }
        
        return None
        
    except Exception as e:
        print(f"   ⚠️ 知识库推断失败: {e}")
        return None


class FieldAnalyzer:
    """字段分析器"""
    
    def __init__(self):
        self.field_type_patterns = FIELD_TYPE_PATTERNS
        self.length_requirements = DEFAULT_LENGTH_REQUIREMENTS
        self.generation_strategies = DEFAULT_GENERATION_STRATEGIES
        self.dependency_rules = DEPENDENCY_RULES
    
    def analyze_field(self, annotation: Dict, context: Optional[str] = None, user_input: Optional[Dict[str, Any]] = None) -> FieldAnalysis:
        """
        分析单个字段

        Args:
            annotation: 标注信息
            context: 上下文信息

        Returns:
            FieldAnalysis: 字段分析结果
        """
        # 获取占位符（现在 insert_multiple 已经在 analyze_all_fields 中拆分了）
        placeholder = annotation.get("placeholder", "unknown")

        reason = annotation.get("reason", "")
        location_type = annotation.get("location_type", "")
        action = annotation.get("action", "")
        
        # 1. 识别字段类型
        field_type = self._identify_field_type(placeholder, reason)
        
        # 2. 确定内容类型描述
        content_type = self._get_content_type_description(placeholder, reason, field_type)
        
        # 3. 确定长度要求
        length_req = self._determine_length_requirement(
            field_type, location_type, annotation, action, user_input or {}
        )
        
        # 4. 确定生成风格
        style = self._determine_style(field_type, action, location_type)
        
        # 5. 确定生成策略
        strategy = self.generation_strategies.get(field_type, "paragraph_generation")
        
        # 6. 识别依赖关系
        dependencies = self._identify_dependencies(placeholder, field_type)
        
        # 7. 确定优先级
        priority = self._calculate_priority(field_type, dependencies)
        
        return FieldAnalysis(
            placeholder=placeholder,
            field_type=field_type,
            content_type=content_type,
            length_requirement=length_req,
            style=style,
            generation_strategy=strategy,
            dependencies=dependencies,
            priority=priority,
            location_context=context,
            annotation=annotation,
        )
    
    def _identify_field_type(self, placeholder: str, reason: str) -> str:
        """识别字段类型（方案1：基于语义的智能识别）"""
        text = f"{placeholder} {reason}".lower()
        
        # 🔥 最高优先级：标题类字段（课题、课程、主题等）
        title_keywords = ["topic", "title", "lesson", "course", "subject", 
                         "课题", "标题", "主题", "课程", "学科", "heading"]
        
        # 排除词：如果包含这些词，说明是内容描述而非标题
        exclude_keywords = ["分析", "说明", "描述内容", "详细说明", "具体内容"]
        
        if any(kw in text for kw in title_keywords):
            # 检查是否是真正的标题字段
            if not any(exclude in reason for exclude in exclude_keywords):
                # 进一步确认：包含"名称"或在placeholder中
                if "名称" in reason or any(kw in placeholder.lower() for kw in ["topic", "title", "lesson", "course"]):
                    return "title"
        
        # 🔥 第二优先级：教学环节类（phase、step、stage）
        if any(keyword in text for keyword in ["phase", "环节", "step", "stage", "阶段"]):
            if any(indicator in reason for indicator in ["环节名称", "环节", "阶段名", "步骤"]):
                return "title"

        # 特殊规则：表格单元格中的活动、内容相关字段
        if any(keyword in text for keyword in ["活动", "activity"]):
            if "activity" in text or "活动" in text:
                return "activity"
        
        # 内容类字段需要明确包含"内容"且不是标题
        if "content" in text or "内容" in text:
            if "teaching" in text or "教学" in text:
                return "content"

        # 遍历所有类型的模式
        type_scores = {}
        for field_type, patterns in self.field_type_patterns.items():
            score = sum(1 for pattern in patterns if pattern.lower() in text)
            if score > 0:
                type_scores[field_type] = score

        # 返回得分最高的类型
        if type_scores:
            return max(type_scores.items(), key=lambda x: x[1])[0]

        return "content"  # 默认为内容类
    
    def _get_content_type_description(
        self, placeholder: str, reason: str, field_type: str
    ) -> str:
        """生成内容类型描述"""
        # 从 reason 中提取描述
        if "对应" in reason:
            match = re.search(r"对应(.+?)(?:填写|区域)", reason)
            if match:
                return match.group(1).strip()
        
        # 从 placeholder 转换
        words = placeholder.split("_")
        chinese_map = {
            "course": "课程",
            "name": "名称",
            "objective": "目标",
            "content": "内容",
            "method": "方法",
            "activity": "活动",
            "teacher": "教师",
            "student": "学生",
            "teaching": "教学",
            "learning": "学习",
        }
        
        return "".join(chinese_map.get(w, w) for w in words)
    
    def _determine_length_requirement(
        self,
        field_type: str,
        location_type: str,
        annotation: Dict,
        action: str,
        user_input: Dict[str, Any],
    ) -> Dict[str, int]:
        """确定长度要求（整合方案1和方案3）"""
        placeholder = annotation.get("placeholder", "")
        doc_type = user_input.get("doc_type", "lesson_plan")

        # 🔥 优先级1: 从 field_constraints.py 读取约束
        try:
            from .field_constraints import FieldConstraintValidator
            validator = FieldConstraintValidator(doc_type)
            constraint = validator.get_constraint(placeholder)

            if constraint:
                base_req = {
                    "min_chars": constraint.get("min_chars", 50),
                    "max_chars": constraint.get("max_chars", 200),
                    "target_items": constraint.get("min_items", 1),
                }
                print(f"   ✅ 使用约束长度: {placeholder} → min={base_req['min_chars']}, max={base_req['max_chars']}")
            else:
                # 🔥 优先级2: 从知识库学习（方案3）
                kb_constraint = _infer_length_from_kb(placeholder, field_type, doc_type)
                
                if kb_constraint:
                    base_req = kb_constraint
                    print(f"   ✅ 使用知识库学习: {placeholder} → min={base_req['min_chars']}, max={base_req['max_chars']}")
                else:
                    # 🔥 优先级3: 使用字段类型默认值
                    base_req = self.length_requirements.get(
                        field_type,
                        {"min_chars": 50, "max_chars": 200, "target_items": 1}
                    ).copy()
                    print(f"   ⚠️ 使用默认长度: {placeholder} (type={field_type}) → min={base_req['min_chars']}, max={base_req['max_chars']}")
        except Exception as e:
            print(f"   ⚠️ 约束导入失败，使用默认长度: {e}")
            base_req = self.length_requirements.get(
                field_type,
                {"min_chars": 50, "max_chars": 200, "target_items": 1}
            ).copy()

        # 🔥 特殊字段模式识别与长度调整
        placeholder_lower = placeholder.lower()
        reason = (annotation.get("reason") or "").lower()
        combined_text = f"{placeholder_lower} {reason}"

        # ========================================
        # 🔥 结构性约束（位置、布局、数量相关）
        # 💡 这些约束覆盖知识库约束，因为是布局硬性要求
        # ========================================

        # 1️⃣ 最高优先级：表格第一列（位置相关）
        # 🔥 修复：任务书的表格第一列是内容列，不应该被限制为简短
        cell_marker = annotation.get("cell_marker", "") or annotation.get("marker", "")

        # 🔥 修复：检查 span，只有 span=1 的第一列才是分类列
        if "grid_col=0" in cell_marker and doc_type == "lesson_plan":
            # 提取 span 信息
            span_match = re.search(r"span=(\d+)", cell_marker)
            span = int(span_match.group(1)) if span_match else 1

            # 只有 span=1 的第一列才是真正的分类列（如"教学环节"）
            # span>1 表示跨列合并单元格（如"教学目标"），应该是内容字段
            if span == 1:
                # 这是布局硬性要求，覆盖知识库约束
                base_req["min_chars"] = 2
                base_req["max_chars"] = 30
                base_req["target_items"] = 1
                print(f"   🔧 覆盖约束：表格第一列（教案分类列，span={span}） → max=30")
                return base_req  # 直接返回，不再进行其他调整
            else:
                print(f"   ℹ️ 跳过覆盖：grid_col=0 但 span={span}>1，保留知识库约束")

        # 2️⃣ 表格单元格 span 调整（布局相关）
        # 🔥 修复：标题类字段不应该因为跨列而放大长度限制
        if location_type == "table_cell" and field_type not in ["title", "basic_info"]:
            span_match = re.search(r"span=(\d+)", cell_marker)
            if span_match:
                span = int(span_match.group(1))
                if span > 1:
                    multiplier = min(span / 3.0, 2.0)
                    base_req["min_chars"] = int(base_req["min_chars"] * multiplier)
                    base_req["max_chars"] = int(base_req["max_chars"] * multiplier)
                    print(f"   🔧 调整约束：span={span} → multiplier={multiplier}")
        elif field_type in ["title", "basic_info"]:
            print(f"   ℹ️ 标题/基础信息字段，不因跨列放大长度限制")

        # 3️⃣ insert_multiple 调整（数量相关）
        if action == "insert_multiple":
            placeholders = annotation.get("placeholders", [])
            base_req["target_items"] = len(placeholders)
            base_req["max_chars"] = base_req["max_chars"] * len(placeholders)
            print(f"   🔧 调整约束：insert_multiple → items={len(placeholders)}")

        # ========================================
        # ❌ 所有业务规则已移除，交给知识库管理：
        #   - 日期字段格式
        #   - 签名字段长度
        #   - 学院名称长度
        #   - 单节课调整
        #   - 教材资源长度
        # ========================================

        # 合理边界
        if base_req.get("min_chars", 0) > base_req.get("max_chars", 0):
            base_req["min_chars"], base_req["max_chars"] = base_req.get("max_chars", 0), base_req.get("min_chars", 0)
        
        return base_req
    
    def _determine_style(self, field_type: str, action: str, location_type: str) -> str:
        """确定生成风格"""
        # 目标类字段通常用结构化列表
        if field_type == "objective":
            return "structured_list"

        # 如果是 insert_multiple，用列表
        if action == "insert_multiple":
            return "comma_separated"

        # 标题和基础信息用简短形式
        if field_type in ["title", "basic_info", "time_info"]:
            return "brief"

        # 内容类字段用段落
        if field_type in ["content", "method", "activity"]:
            return "paragraph"

        return "formal"
    
    def _identify_dependencies(self, placeholder: str, field_type: str) -> List[str]:
        """识别字段依赖关系"""
        dependencies = []
        
        # 基于字段类型的依赖规则
        if field_type in self.dependency_rules:
            dependencies.extend(self.dependency_rules[field_type])
        
        # 特殊规则：如果字段名包含 "teacher"，依赖 "course_name"
        if "teacher" in placeholder and "course_name" not in dependencies:
            dependencies.append("course_name")
        
        # 特殊规则：如果字段名包含 "student"，依赖 "teaching_content"
        if "student" in placeholder and field_type == "activity":
            if "teaching_content" not in dependencies:
                dependencies.append("teaching_content")
        
        return dependencies
    
    def _calculate_priority(self, field_type: str, dependencies: List[str]) -> int:
        """计算生成优先级（1-10，越小越优先）"""
        # 基础信息最优先
        if field_type == "basic_info":
            return 1
        
        # 时间信息次之
        if field_type == "time_info":
            return 2
        
        # 目标类
        if field_type == "objective":
            return 3
        
        # 内容类
        if field_type == "content":
            return 4
        
        # 方法类
        if field_type == "method":
            return 5
        
        # 活动类
        if field_type == "activity":
            return 6
        
        # 评价类最后
        if field_type == "assessment":
            return 7
        
        # 基于依赖数量调整
        return 5 + len(dependencies)
    
    def analyze_all_fields(
        self,
        annotations: List[Dict],
        context_map: Optional[Dict[str, str]] = None,
        user_input: Optional[Dict[str, Any]] = None,
    ) -> List[FieldAnalysis]:
        """
        分析所有字段
        
        Args:
            annotations: 所有标注
            context_map: 上下文映射 {placeholder: context}
            
        Returns:
            List[FieldAnalysis]: 所有字段的分析结果
        """
        context_map = context_map or {}

        results = []
        for annotation in annotations:
            # 处理 insert_multiple 类型：为每个占位符创建独立的 FieldAnalysis
            if "placeholders" in annotation and annotation.get("action") == "insert_multiple":
                placeholders = annotation.get("placeholders", [])
                for ph in placeholders:
                    # 为每个占位符创建单独的标注副本
                    ann_copy = annotation.copy()
                    ann_copy["placeholder"] = ph
                    # 移除 placeholders 字段，避免重复处理
                    ann_copy.pop("placeholders", None)

                    context = context_map.get(ph)
                    analysis = self.analyze_field(ann_copy, context, user_input=user_input)
                    results.append(analysis)
            else:
                # 普通标注
                placeholder = annotation.get("placeholder", "")
                context = context_map.get(placeholder)

                analysis = self.analyze_field(annotation, context, user_input=user_input)
                results.append(analysis)

        # 按优先级排序
        results.sort(key=lambda x: (x.priority, x.placeholder))

        return results
