"""
知识库管理系统

功能：
1. 存储经验教训（JSONL 格式）
2. 加载和查询历史经验
3. 聚合洞察（按标注器/生成器分类）
4. 格式化为提示词注入格式
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple


# 文档类型定义
DocumentType = Literal["lesson_plan", "task_proposal", "thesis", "report", "other"]

# 文档类型中文名称映射
DOC_TYPE_NAMES = {
    "lesson_plan": "教案",
    "task_proposal": "任务书",
    "thesis": "论文",
    "report": "报告",
    "other": "其他"
}


class KnowledgeBase:
    """知识库管理器（支持按文档类型分类存储）"""

    def __init__(
        self,
        kb_path: Optional[Path] = None,
        doc_type: Optional[DocumentType] = None,
        base_dir: Path = Path("knowledge")
    ):
        """
        初始化知识库

        Args:
            kb_path: 知识库文件路径（JSONL 格式）
                    如果指定了kb_path，则直接使用；
                    如果未指定，则根据doc_type自动生成路径
            doc_type: 文档类型（lesson_plan/task_proposal/thesis/report/other）
            base_dir: 知识库根目录，默认为 knowledge/
        """
        self.doc_type = doc_type
        self.base_dir = base_dir

        # 如果指定了kb_path，直接使用
        if kb_path is not None:
            self.kb_path = kb_path
        # 否则根据doc_type自动生成路径
        elif doc_type is not None:
            self.kb_path = base_dir / doc_type / "experiences.jsonl"
        # 兼容旧版本：默认路径
        else:
            self.kb_path = Path("results/v5_kb/experiences.jsonl")

        # 确保目录和文件存在
        self.kb_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.kb_path.exists():
            self.kb_path.touch()

        # 记录当前使用的类型
        type_name = DOC_TYPE_NAMES.get(doc_type, "未分类") if doc_type else "通用"
        print(f"📚 知识库初始化: {type_name} ({self.kb_path})")

    @classmethod
    def for_doc_type(
        cls,
        doc_type: DocumentType,
        base_dir: Path = Path("knowledge")
    ) -> "KnowledgeBase":
        """
        便捷方法：创建指定文档类型的知识库

        Args:
            doc_type: 文档类型
            base_dir: 知识库根目录

        Returns:
            知识库实例
        """
        return cls(doc_type=doc_type, base_dir=base_dir)

    def add_experience(
        self,
        vlm_result: Dict[str, Any],
        analysis: Dict[str, Any],
        context: Dict[str, Any],
    ) -> None:
        """
        添加一条经验到知识库（只存储可操作的改进建议）

        Args:
            vlm_result: VLM 检查结果（用于提取严重程度）
            analysis: 错误分析结果（核心：包含改进建议）
            context: 上下文信息（用户需求、模板名称、文档类型等）
        """
        # 获取文档类型（优先从context，其次从self.doc_type）
        doc_type = context.get("doc_type", self.doc_type)
        doc_type_name = DOC_TYPE_NAMES.get(doc_type, "未知") if doc_type else "未分类"

        annotator_prompts = []
        generator_prompts = []

        for item in analysis.get("analysis", []):
            root_cause = item.get("root_cause", "unknown")
            recommendation = item.get("recommendation", {})

            # 提取标注器改进建议
            if root_cause in ["annotator", "both"] and recommendation.get("for_annotator"):
                annotator_prompts.append({
                    "prompt": recommendation["for_annotator"],
                    "reason": item.get("reason", ""),
                    "root_cause": root_cause
                })

            # 提取生成器改进建议
            if root_cause in ["generator", "both"] and recommendation.get("for_generator"):
                generator_prompts.append({
                    "prompt": recommendation["for_generator"],
                    "reason": item.get("reason", ""),
                    "root_cause": root_cause
                })

        # 提取整体建议
        overall_rec = analysis.get("overall_recommendation", {})
        key_insights = overall_rec.get("key_insights", [])
        next_steps = overall_rec.get("next_steps", [])

        recs = vlm_result.get("recommendations", {})
        by_issue = recs.get("by_issue", [])
        overall = recs.get("overall", [])
        issues = vlm_result.get("issues", [])

        idx_to_kind = {}
        i = 1
        for it in issues:
            idx_to_kind[i] = it.get("kind", "")
            i += 1

        def _cat(kind: str, text: str) -> str:
            k = (kind or "").strip()
            t = (text or "")
            if k in ("format_error", "header_overwritten"):
                return "annotator"
            if k in ("placeholder_not_filled", "empty_section", "content_mismatch"):
                return "generator"
            tl = t.lower()
            if ("格式" in t) or ("排版" in t) or ("布局" in t) or ("模板" in t):
                return "annotator"
            if ("填充" in t) or ("日期" in t) or ("文献" in t) or ("一致" in t) or ("数据集" in t) or ("替换" in t):
                return "generator"
            return "generator"

        for bi in by_issue:
            ii = bi.get("issue_index")
            sg = bi.get("suggestion", "")
            kd = idx_to_kind.get(ii, "")
            c = _cat(kd, sg)
            if c == "annotator":
                annotator_prompts.append({"prompt": sg, "reason": "", "root_cause": "vlm"})
            else:
                generator_prompts.append({"prompt": sg, "reason": "", "root_cause": "vlm"})

        for sg in overall:
            c = _cat("", sg)
            if c == "annotator":
                annotator_prompts.append({"prompt": sg, "reason": "", "root_cause": "vlm"})
            else:
                generator_prompts.append({"prompt": sg, "reason": "", "root_cause": "vlm"})

        # 只存储有价值的改进建议
        entry = {
            "timestamp": datetime.now().isoformat(),
            "doc_type": doc_type,
            "doc_type_name": doc_type_name,
            "template_name": context.get("template_name", "unknown"),
            "severity": vlm_result.get("summary", {}).get("severity", "unknown"),
            # 核心：可操作的改进建议
            "annotator_prompts": annotator_prompts,
            "generator_prompts": generator_prompts,
            "key_insights": key_insights,
            "next_steps": next_steps,
            # 最小化元数据
            "metadata": {
                "pipeline_version": "v5",
                "doc_classification": context.get("doc_classification", {}),
            }
        }

        # 追加到 JSONL 文件
        with open(self.kb_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        print(f"   💾 已添加 {len(annotator_prompts)} 条标注建议 + {len(generator_prompts)} 条生成建议到知识库")

    def load_all(self, max_entries: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        加载所有知识库条目

        Args:
            max_entries: 最多加载多少条（从最新开始），None 表示全部加载

        Returns:
            知识库条目列表
        """
        if not self.kb_path.exists():
            return []

        entries = []
        with open(self.kb_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # 按时间戳降序排列（最新的在前）
        entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        if max_entries:
            entries = entries[:max_entries]

        return entries

    def aggregate_insights(
        self,
        max_entries: int = 50,
        min_severity: str = "low",
    ) -> Dict[str, Any]:
        """
        聚合历史经验，提取关键洞察（基于存储的改进建议）

        Args:
            max_entries: 最多使用多少条最近的经验
            min_severity: 最低严重程度（low/medium/high）

        Returns:
            聚合的洞察结果:
            {
                "annotator_prompts": ["建议1", "建议2", ...],
                "generator_prompts": ["建议1", "建议2", ...],
                "key_insights": ["洞察1", "洞察2", ...],
                "next_steps": ["步骤1", "步骤2", ...]
            }
        """
        entries = self.load_all(max_entries=max_entries)

        if not entries:
            return {
                "annotator_prompts": [],
                "generator_prompts": [],
                "key_insights": [],
                "next_steps": []
            }

        # 严重程度过滤
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        min_level = severity_order.get(min_severity, 0)

        # 聚合所有改进建议
        all_annotator_prompts = []
        all_generator_prompts = []
        all_key_insights = []
        all_next_steps = []

        for entry in entries:
            # 过滤严重程度
            severity = entry.get("severity", "low")
            if severity_order.get(severity, 0) < min_level:
                continue

            # 收集标注器建议
            annotator_prompts = entry.get("annotator_prompts", [])
            for item in annotator_prompts:
                all_annotator_prompts.append(item.get("prompt", ""))

            # 收集生成器建议
            generator_prompts = entry.get("generator_prompts", [])
            for item in generator_prompts:
                all_generator_prompts.append(item.get("prompt", ""))

            # 收集关键洞察
            all_key_insights.extend(entry.get("key_insights", []))

            # 收集改进步骤
            all_next_steps.extend(entry.get("next_steps", []))

        # 去重并按频率排序
        def _deduplicate_and_sort(items: List[str], max_count: int = 10) -> List[str]:
            """去重并保留最常见的条目"""
            counts = defaultdict(int)
            for item in items:
                if item.strip():
                    counts[item.strip()] += 1
            # 按频率降序排序
            sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            return [item for item, _ in sorted_items[:max_count]]

        return {
            "annotator_prompts": _deduplicate_and_sort(all_annotator_prompts, 15),
            "generator_prompts": _deduplicate_and_sort(all_generator_prompts, 15),
            "key_insights": _deduplicate_and_sort(all_key_insights, 10),
            "next_steps": _deduplicate_and_sort(all_next_steps, 8)
        }

    def format_for_annotator_prompt(
        self,
        max_entries: int = 30,
        min_severity: str = "medium",
    ) -> str:
        """
        格式化知识库内容，用于注入到标注器提示词（只包含可操作的建议）

        Args:
            max_entries: 使用最近多少条经验
            min_severity: 最低严重程度

        Returns:
            格式化的提示词片段
        """
        insights = self.aggregate_insights(max_entries, min_severity)
        annotator_prompts = insights.get("annotator_prompts", [])
        key_insights = insights.get("key_insights", [])

        if not annotator_prompts and not key_insights:
            return ""

        lines = [
            "## 📚 知识库提示（基于历史经验的改进建议）",
            "",
        ]

        if annotator_prompts:
            lines.append("### ⚠️  标注器改进建议")
            lines.append("")
            for idx, prompt in enumerate(annotator_prompts[:10], start=1):
                lines.append(f"{idx}. {prompt}")
            lines.append("")

        if key_insights:
            lines.append("### 💡 关键洞察")
            lines.append("")
            for insight in key_insights[:5]:
                lines.append(f"- {insight}")
            lines.append("")

        return "\n".join(lines)

    def format_for_generator_prompt(
        self,
        max_entries: int = 30,
        min_severity: str = "medium",
    ) -> str:
        """
        格式化知识库内容，用于注入到生成器提示词（只包含可操作的建议）

        Args:
            max_entries: 使用最近多少条经验
            min_severity: 最低严重程度

        Returns:
            格式化的提示词片段
        """
        insights = self.aggregate_insights(max_entries, min_severity)
        generator_prompts = insights.get("generator_prompts", [])
        key_insights = insights.get("key_insights", [])
        next_steps = insights.get("next_steps", [])

        if not generator_prompts and not key_insights and not next_steps:
            return ""

        lines = [
            "## 📚 知识库提示（基于历史经验的改进建议）",
            "",
        ]

        if generator_prompts:
            lines.append("### ⚠️  生成器改进建议")
            lines.append("")
            for idx, prompt in enumerate(generator_prompts[:10], start=1):
                lines.append(f"{idx}. {prompt}")
            lines.append("")

        if key_insights:
            lines.append("### 💡 关键洞察")
            lines.append("")
            for insight in key_insights[:5]:
                lines.append(f"- {insight}")
            lines.append("")

        if next_steps:
            lines.append("### 📋 改进步骤")
            lines.append("")
            for step in next_steps[:5]:
                lines.append(f"- {step}")
            lines.append("")

        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """
        获取知识库统计信息

        Returns:
            统计数据
        """
        entries = self.load_all()

        if not entries:
            return {
                "total_entries": 0,
                "date_range": None,
                "severity_distribution": {},
                "total_annotator_prompts": 0,
                "total_generator_prompts": 0,
                "total_insights": 0
            }

        timestamps = [e.get("timestamp", "") for e in entries if e.get("timestamp")]
        severities = [e.get("severity", "unknown") for e in entries]

        # 统计改进建议数量
        total_annotator = sum(len(e.get("annotator_prompts", [])) for e in entries)
        total_generator = sum(len(e.get("generator_prompts", [])) for e in entries)
        total_insights = sum(len(e.get("key_insights", [])) for e in entries)

        severity_dist = defaultdict(int)
        for s in severities:
            severity_dist[s] += 1

        return {
            "total_entries": len(entries),
            "date_range": {
                "earliest": min(timestamps) if timestamps else None,
                "latest": max(timestamps) if timestamps else None
            },
            "severity_distribution": dict(severity_dist),
            "total_annotator_prompts": total_annotator,
            "total_generator_prompts": total_generator,
            "total_insights": total_insights,
            "avg_prompts_per_entry": (total_annotator + total_generator) / len(entries) if entries else 0.0
        }

    def prune_old_entries(self, keep_latest: int = 100) -> int:
        """
        清理旧条目，只保留最新的 N 条

        Args:
            keep_latest: 保留最新多少条

        Returns:
            删除的条目数
        """
        entries = self.load_all()

        if len(entries) <= keep_latest:
            return 0

        # 保留最新的 keep_latest 条
        entries_to_keep = entries[:keep_latest]

        # 重写文件
        with open(self.kb_path, "w", encoding="utf-8") as f:
            for entry in entries_to_keep:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        deleted_count = len(entries) - keep_latest
        print(f"   🗑️  已删除 {deleted_count} 条旧经验，保留最新 {keep_latest} 条")

        return deleted_count


# 全局单例
_global_kb: Optional[KnowledgeBase] = None


def get_knowledge_base(kb_path: Optional[Path] = None) -> KnowledgeBase:
    """
    获取全局知识库单例

    Args:
        kb_path: 知识库路径（仅首次调用时生效）

    Returns:
        KnowledgeBase 实例
    """
    global _global_kb

    if _global_kb is None:
        _global_kb = KnowledgeBase(kb_path)

    return _global_kb


if __name__ == "__main__":
    # 测试示例
    kb = KnowledgeBase(Path("results/v5_kb_test.jsonl"))

    # 测试添加经验（新格式：只存储改进建议）
    test_vlm_result = {
        "summary": {
            "severity": "high",
            "notes": "存在未替换的占位符"
        }
    }

    test_analysis = {
        "analysis": [
            {
                "issue_index": 1,
                "root_cause": "generator",
                "reason": "生成器未能识别表格中的占位符",
                "recommendation": {
                    "for_annotator": "",
                    "for_generator": "增强占位符识别逻辑，特别注意表格单元格中的占位符"
                }
            },
            {
                "issue_index": 2,
                "root_cause": "annotator",
                "reason": "标注器遗漏了表头后的空白单元格",
                "recommendation": {
                    "for_annotator": "系统性检查表格每个单元格，不要遗漏空白区域",
                    "for_generator": ""
                }
            }
        ],
        "overall_recommendation": {
            "priority": "high",
            "key_insights": [
                "表格单元格的占位符识别准确率较低",
                "空白单元格容易被标注器遗漏"
            ],
            "next_steps": [
                "优化表格处理逻辑",
                "增加空白检测机制"
            ]
        }
    }

    test_context = {
        "template_name": "test_template.docx",
        "user_requirement": "生成测试教案",
        "doc_type": "lesson_plan"
    }

    print("=" * 60)
    print("测试 1: 添加经验到知识库")
    print("=" * 60)
    kb.add_experience(test_vlm_result, test_analysis, test_context)

    # 测试聚合
    print("\n" + "=" * 60)
    print("测试 2: 聚合改进建议")
    print("=" * 60)
    insights = kb.aggregate_insights()
    print(json.dumps(insights, ensure_ascii=False, indent=2))

    # 测试格式化
    print("\n" + "=" * 60)
    print("测试 3: 格式化为标注器提示词")
    print("=" * 60)
    print(kb.format_for_annotator_prompt())

    print("=" * 60)
    print("测试 4: 格式化为生成器提示词")
    print("=" * 60)
    print(kb.format_for_generator_prompt())

    # 测试统计
    print("=" * 60)
    print("测试 5: 知识库统计")
    print("=" * 60)
    print(json.dumps(kb.get_stats(), ensure_ascii=False, indent=2))
