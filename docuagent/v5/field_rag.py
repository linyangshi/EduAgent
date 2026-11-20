"""
字段级RAG知识库检索 - 根据字段名称检索相关经验
"""
from typing import List, Dict, Optional
from pathlib import Path
import json
import re
from collections import defaultdict


class FieldRAG:
    """字段级RAG检索器"""

    def __init__(self, doc_type: str = "lesson_plan"):
        """
        初始化字段RAG检索器

        Args:
            doc_type: 文档类型 (lesson_plan, task_proposal等)
        """
        self.doc_type = doc_type
        self.kb_path = Path(f"knowledge/{doc_type}/experiences.jsonl")

        # 字段关键词映射(用于匹配)
        self.field_keywords = {
            "教学内容分析": ["教学内容", "内容分析", "知识分析", "能力要素"],
            "教学目标": ["教学目标", "知识目标", "能力目标", "情感目标"],
            "教学重点": ["教学重点", "重点", "重难点", "难点"],
            "教学难点": ["教学难点", "难点", "重难点"],
            "教学过程": ["教学过程", "教学环节", "教师活动", "学生活动", "设计意图"],
            "教学反思": ["教学反思", "反思", "总结"],
            "课后拓展": ["课后", "拓展", "作业"],

            # 任务书字段（🔥 增加更多变体以提高匹配率）
            "目的与意义": ["目的", "意义", "研究背景", "研究现状", "purpose", "significance", "目的意义"],
            "构思与内容": ["构思", "内容", "研究目标", "研究内容", "技术路线", "conception", "concept", "构思内容"],
            "参考文献": ["参考文献", "文献", "references", "参考资料"],
            "进度计划": ["进度", "计划", "阶段", "schedule", "时间安排"],

            # 通用字段
            "表格第一列": ["grid_col=0", "第一列", "表格", "环节名称"],
            "字段长度": ["字数", "长度", "≤", "≥", "约", "800", "600", "1000"],  # 🔥 新增具体数字
        }

    def load_experiences(self) -> List[Dict]:
        """加载知识库所有经验"""
        if not self.kb_path.exists():
            return []

        experiences = []
        with open(self.kb_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        experiences.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return experiences

    def extract_field_name(self, content_type: str, placeholder: str) -> str:
        """
        从content_type或placeholder中提取字段名称

        🔥 使用与field_constraints相同的智能匹配逻辑

        Args:
            content_type: 字段类型描述
            placeholder: 占位符名称

        Returns:
            规范化的字段名称
        """
        # 🔥 新增：使用field_constraints的智能匹配来归一化placeholder
        try:
            import sys
            from pathlib import Path

            # 添加v4路径
            v4_path = Path(__file__).parent.parent / "v4" / "content_generation"
            if str(v4_path) not in sys.path:
                sys.path.insert(0, str(v4_path))

            from field_constraints import FieldConstraintValidator

            validator = FieldConstraintValidator(self.doc_type)
            constraint = validator.get_constraint(placeholder)

            if constraint:
                # 找到匹配的约束，使用约束中的描述作为字段名
                # 例如: "purpose_significance" -> "研究目的与意义" -> "目的与意义"
                description = constraint.get("description", "")
                if description:
                    # 尝试匹配到field_keywords中的标准字段名
                    for field_name in self.field_keywords.keys():
                        if field_name in description or description in field_name:
                            return field_name
        except Exception as e:
            # 如果智能匹配失败，降级到原逻辑
            pass

        # 优先从content_type提取
        for field_name in self.field_keywords.keys():
            if field_name in content_type:
                return field_name

        # 从placeholder提取
        for field_name in self.field_keywords.keys():
            field_name_normalized = field_name.replace("与", "").replace("及", "")
            if field_name_normalized in placeholder:
                return field_name

        # 🔥 新增：尝试直接匹配placeholder到field_keywords的关键词
        for field_name, keywords in self.field_keywords.items():
            for keyword in keywords:
                # 去除特殊字符进行模糊匹配
                keyword_clean = keyword.replace("与", "").replace("及", "").lower()
                placeholder_clean = placeholder.replace("_", "").lower()
                if keyword_clean in placeholder_clean or placeholder_clean in keyword_clean:
                    return field_name

        # 返回原始content_type
        return content_type

    def search_field_experiences(
        self,
        field_name: str,
        top_k: int = 3,
        min_relevance: float = 0.3
    ) -> List[str]:
        """
        检索与特定字段相关的经验

        Args:
            field_name: 字段名称
            top_k: 返回top-k条最相关经验
            min_relevance: 最小相关度阈值

        Returns:
            相关经验提示列表
        """
        experiences = self.load_experiences()
        if not experiences:
            return []

        # 获取字段关键词
        keywords = self.field_keywords.get(field_name, [field_name])

        # 计算每条经验的相关度并收集prompts
        scored_prompts = []

        for exp in experiences:
            # 收集所有generator_prompts
            for prompt_item in exp.get("generator_prompts", []):
                prompt_text = prompt_item.get("prompt", "")

                # 计算相关度得分
                score = self._calculate_relevance(prompt_text, keywords)

                if score >= min_relevance:
                    scored_prompts.append({
                        "prompt": prompt_text,
                        "score": score,
                        "severity": exp.get("severity", "low")
                    })

        # 按相关度和严重程度排序
        severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        scored_prompts.sort(
            key=lambda x: (x["score"], severity_weight.get(x["severity"], 0)),
            reverse=True
        )

        # 返回top-k
        return [item["prompt"] for item in scored_prompts[:top_k]]

    def _calculate_relevance(self, prompt: str, keywords: List[str]) -> float:
        """
        计算prompt与关键词的相关度

        Args:
            prompt: 提示文本
            keywords: 关键词列表

        Returns:
            相关度得分 (0-1)
        """
        if not prompt or not keywords:
            return 0.0

        # 计算匹配的关键词数量
        matches = 0
        total_keywords = len(keywords)

        for keyword in keywords:
            if keyword in prompt:
                matches += 1

        # 基础得分: 匹配关键词比例
        base_score = matches / total_keywords

        # 如果prompt中包含字段的完整名称,额外加分
        field_name = keywords[0] if keywords else ""
        if field_name in prompt and len(field_name) > 2:
            base_score += 0.3

        # 归一化到0-1
        return min(base_score, 1.0)

    def format_field_knowledge(
        self,
        field_name: str,
        top_k: int = 3
    ) -> str:
        """
        格式化字段相关知识为prompt片段

        Args:
            field_name: 字段名称
            top_k: 检索top-k条经验

        Returns:
            格式化的知识提示
        """
        prompts = self.search_field_experiences(field_name, top_k=top_k)

        if not prompts:
            return ""

        lines = [
            f"\n### 📚 {field_name}相关的历史经验",
            ""
        ]

        for idx, prompt in enumerate(prompts, 1):
            lines.append(f"{idx}. {prompt}")

        lines.append("")
        return "\n".join(lines)


def get_field_knowledge(
    field_name: str,
    placeholder: str,
    doc_type: str = "lesson_plan",
    top_k: int = 3
) -> str:
    """
    便捷函数: 获取字段相关知识

    Args:
        field_name: 字段名称(content_type)
        placeholder: 占位符名称
        doc_type: 文档类型
        top_k: 检索top-k条经验

    Returns:
        格式化的字段知识
    """
    rag = FieldRAG(doc_type=doc_type)

    # 提取规范化字段名
    normalized_field = rag.extract_field_name(field_name, placeholder)

    # 检索并格式化知识
    return rag.format_field_knowledge(normalized_field, top_k=top_k)


if __name__ == "__main__":
    # 测试
    rag = FieldRAG(doc_type="lesson_plan")

    print("=" * 60)
    print("字段级RAG测试")
    print("=" * 60)

    test_fields = ["教学内容分析", "教学重点", "教学过程", "表格第一列"]

    for field in test_fields:
        print(f"\n🔍 检索字段: {field}")
        print("-" * 60)
        knowledge = rag.format_field_knowledge(field, top_k=3)
        if knowledge:
            print(knowledge)
        else:
            print("  未找到相关经验")
