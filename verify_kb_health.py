#!/usr/bin/env python3
"""
知识库健康检查工具 - 检测跨类型污染和数据质量
"""
from pathlib import Path
from docuagent.v5.knowledge_base import KnowledgeBase
import json

# 文档类型专属关键词
DOC_TYPE_KEYWORDS = {
    "task_proposal": {
        "exclusive": ["目的与意义", "构思与内容", "任务书", "开题报告", "参考文献"],
        "forbidden": ["教学", "授课", "课堂", "教案", "教学设计", "教学目标"]
    },
    "lesson_plan": {
        "exclusive": ["教学目标", "教学重点", "教学难点", "教学过程", "教案"],
        "forbidden": ["目的与意义", "构思与内容", "任务书", "论文"]
    },
    "thesis": {
        "exclusive": ["论文", "摘要", "关键词", "研究方法", "结论"],
        "forbidden": ["教学", "授课", "课堂"]
    }
}

def check_kb_health(doc_type: str) -> dict:
    """
    检查指定文档类型的知识库健康状态

    Returns:
        {
            "doc_type": str,
            "entry_count": int,
            "is_healthy": bool,
            "contamination": List[str],  # 检测到的污染关键词
            "warnings": List[str]
        }
    """
    kb = KnowledgeBase(doc_type=doc_type)
    entries = kb.load_all()

    result = {
        "doc_type": doc_type,
        "entry_count": len(entries),
        "is_healthy": True,
        "contamination": [],
        "warnings": []
    }

    if not entries:
        result["warnings"].append(f"知识库为空")
        return result

    # 获取格式化的知识库内容
    formatted = kb.format_for_generator_prompt(max_entries=50)

    # 检查forbidden关键词
    if doc_type in DOC_TYPE_KEYWORDS:
        forbidden = DOC_TYPE_KEYWORDS[doc_type]["forbidden"]
        for keyword in forbidden:
            if keyword in formatted:
                result["contamination"].append(keyword)
                result["is_healthy"] = False

    # 检查条目质量
    for entry in entries:
        severity = entry.get("severity", "unknown")
        if severity not in ["low", "medium", "high", "critical"]:
            result["warnings"].append(f"未知的severity级别: {severity}")

        gen_count = len(entry.get("generator_prompts", []))
        ann_count = len(entry.get("annotator_prompts", []))

        if gen_count == 0 and ann_count == 0:
            result["warnings"].append(f"条目无任何改进建议: {entry.get('timestamp', 'N/A')}")

    return result

def main():
    print("=" * 70)
    print("🏥 知识库健康检查工具")
    print("=" * 70)
    print()

    # 检查所有文档类型
    doc_types = ["task_proposal", "lesson_plan", "thesis", "report"]

    all_healthy = True
    results = []

    for doc_type in doc_types:
        kb_path = Path(f"knowledge/{doc_type}/experiences.jsonl")

        if not kb_path.exists():
            print(f"⚪ {doc_type:20s} - 知识库不存在")
            continue

        result = check_kb_health(doc_type)
        results.append(result)

        # 显示结果
        icon = "✅" if result["is_healthy"] else "❌"
        print(f"{icon} {doc_type:20s} - {result['entry_count']}条记录", end="")

        if result["contamination"]:
            print(f" - ⚠️  污染: {', '.join(result['contamination'][:3])}")
            all_healthy = False
        elif result["warnings"]:
            print(f" - ⚠️  {len(result['warnings'])}个警告")
        else:
            print(" - 健康")

    print()
    print("=" * 70)

    # 详细报告
    for result in results:
        if result["contamination"] or result["warnings"]:
            print(f"\n📋 {result['doc_type']} 详细信息:")

            if result["contamination"]:
                print(f"  ❌ 污染关键词 ({len(result['contamination'])}个):")
                for keyword in result["contamination"]:
                    print(f"     - {keyword}")

            if result["warnings"]:
                print(f"  ⚠️  警告 ({len(result['warnings'])}个):")
                for warning in result["warnings"][:5]:
                    print(f"     - {warning}")

    print()
    print("=" * 70)

    if all_healthy:
        print("🎉 所有知识库健康检查通过!")
    else:
        print("⚠️  发现问题,建议运行清理脚本")
        print("   python3 clean_task_proposal_kb.py")

    print("=" * 70)

    return 0 if all_healthy else 1

if __name__ == "__main__":
    exit(main())
