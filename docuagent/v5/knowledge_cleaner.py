"""
知识库清理器 - 使用LLM自动清理无用建议
支持两种模式：
1. 基于规则的快速清理（rule-based）
2. 基于LLM的智能清理（llm-based）
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Literal

from config.settings import DASHSCOPE_API_KEY
from http import HTTPStatus
import dashscope


# 无用建议的关键词模式（基于规则判断）
USELESS_PATTERNS = {
    "technical": [
        "生成器", "标注器", "系统", "模块", "逻辑", "机制", "引擎", "校验", "检查模块",
        "优化.*逻辑", "增强.*能力", "强化.*机制", "完善.*功能", "调整.*策略",
        "在.*中", "对.*进行", "为.*添加", "将.*调整", "使.*能够"
    ],
    "layout": [
        "表格列宽", "文字重叠", "边框", "排版", "布局", "换行", "边距", "对齐",
        "字体", "字号", "行距", "段落", "缩进", "溢出", "贴边", "自适应"
    ],
    "vague": [
        "^内容应该详细$", "^应该.*$", "^建议.*$", "^确保.*$", "^避免.*$"
    ]
}


def is_useless_prompt(prompt: str) -> tuple[bool, str]:
    """
    基于规则判断建议是否无用

    Args:
        prompt: 建议文本

    Returns:
        (是否无用, 删除原因)
    """
    prompt_lower = prompt.lower()

    # 检查技术实现建议
    for pattern in USELESS_PATTERNS["technical"]:
        if re.search(pattern, prompt):
            return True, "技术实现建议"

    # 检查排版布局建议
    for pattern in USELESS_PATTERNS["layout"]:
        if pattern in prompt:
            return True, "排版布局建议"

    # 检查过于抽象的建议
    for pattern in USELESS_PATTERNS["vague"]:
        if re.match(pattern, prompt):
            return True, "过于抽象"

    # 检查是否太短（可能是不完整的建议）
    if len(prompt.strip()) < 10:
        return True, "建议太短，可能不完整"

    return False, ""


def has_specific_constraint(prompt: str) -> bool:
    """
    判断建议是否包含具体约束（应该保留）

    Returns:
        是否包含具体约束
    """
    # 检查是否包含具体的字符数限制
    if re.search(r'[≤<=]\s*\d+\s*字', prompt):
        return True

    # 检查是否包含具体的字数范围
    if re.search(r'\d+[-~]\d+\s*字', prompt):
        return True

    # 检查是否包含具体示例
    if '✅' in prompt or '❌' in prompt or '示例' in prompt:
        return True

    # 检查是否是字段类型识别规则
    if '基础信息' in prompt or '内容字段' in prompt or '辅助内容' in prompt:
        return True

    return False


def cleanup_by_rules(kb_path: Path, doc_type: str = "lesson_plan") -> Dict[str, Any]:
    """
    基于规则快速清理知识库

    Args:
        kb_path: 知识库文件路径
        doc_type: 文档类型

    Returns:
        清理结果统计
    """
    if not kb_path.exists():
        return {"status": "not_found", "message": "知识库文件不存在"}

    # 加载所有知识库条目
    entries = []
    with open(kb_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not entries:
        return {"status": "empty", "message": "知识库为空"}

    print(f"\n🧹 基于规则清理知识库: {kb_path.name}")
    print(f"   原始条目数: {len(entries)}")

    # 统计
    total_prompts = 0
    kept_prompts = []
    removed_prompts = []
    removed_reasons = {}

    # 处理每个条目
    for entry in entries:
        source = entry.get("source", "vlm")

        # 人工添加的条目永远保留
        if source == "manual":
            for prompt_item in entry.get("generator_prompts", []):
                kept_prompts.append({
                    "prompt": prompt_item.get("prompt", ""),
                    "source": "manual",
                    "reason": "人工添加"
                })
                total_prompts += 1
            continue

        # VLM条目需要过滤
        for i, prompt_item in enumerate(entry.get("generator_prompts", [])):
            total_prompts += 1
            prompt_text = prompt_item.get("prompt", "")

            # 判断是否无用
            is_useless, reason = is_useless_prompt(prompt_text)

            # 如果被判断为无用，但包含具体约束，仍然保留
            if is_useless and has_specific_constraint(prompt_text):
                is_useless = False
                reason = "包含具体约束，保留"

            if is_useless:
                removed_prompts.append(prompt_text)
                removed_reasons[str(total_prompts)] = reason
            else:
                kept_prompts.append({
                    "prompt": prompt_text,
                    "source": source,
                    "reason": prompt_item.get("reason", "")
                })

    print(f"   总建议数: {total_prompts}")
    print(f"   保留: {len(kept_prompts)} 条")
    print(f"   删除: {len(removed_prompts)} 条")

    # 如果没有需要删除的，直接返回
    if not removed_prompts:
        return {
            "status": "no_change",
            "message": "没有发现需要删除的建议"
        }

    # 重建知识库
    new_entries = []

    # 1. 保留所有manual来源的条目
    manual_count = 0
    for entry in entries:
        if entry.get("source") == "manual":
            new_entries.append(entry)
            manual_count += 1

    if manual_count > 0:
        print(f"   ✅ 保留 {manual_count} 条人工条目")

    # 2. 创建合并后的VLM条目（只包含保留的建议）
    vlm_prompts = [p for p in kept_prompts if p["source"] != "manual"]

    if vlm_prompts:
        merged_entry = {
            "timestamp": datetime.now().isoformat(),
            "doc_type": doc_type,
            "doc_type_name": "教案" if doc_type == "lesson_plan" else doc_type,
            "source": "rule_cleaned",
            "severity": "high",
            "annotator_prompts": [],
            "generator_prompts": [
                {
                    "prompt": p["prompt"],
                    "reason": p.get("reason", "规则筛选保留"),
                    "root_cause": "generator"
                }
                for p in vlm_prompts
            ],
            "key_insights": [
                "知识库已通过规则清理，删除了技术实现、排版布局等无关建议"
            ],
            "next_steps": [],
            "metadata": {
                "pipeline_version": "v5",
                "cleanup_method": "rule_based",
                "cleanup_time": datetime.now().isoformat()
            }
        }
        new_entries.append(merged_entry)
        print(f"   ✅ 创建规则清理后的VLM合并条目: {len(vlm_prompts)} 条建议")

    # 3. 备份原文件
    backup_path = kb_path.with_suffix(f".jsonl.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy(kb_path, backup_path)
    print(f"   💾 备份原文件: {backup_path.name}")

    # 4. 写入新的知识库
    with open(kb_path, "w", encoding="utf-8") as f:
        for entry in new_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"   ✅ 知识库已更新: {len(new_entries)} 条记录")

    # 打印删除的建议示例
    if removed_reasons:
        print(f"\n❌ 删除的建议示例（前5条）:")
        for idx, reason in list(removed_reasons.items())[:5]:
            idx_int = int(idx) - 1
            if 0 <= idx_int < len(removed_prompts):
                prompt_preview = removed_prompts[idx_int][:80]
                print(f"   [{idx}] {reason}")
                print(f"        {prompt_preview}...")

    # 统计删除原因分布
    reason_counts = {}
    for reason in removed_reasons.values():
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    print(f"\n📊 删除原因分布:")
    for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"   {reason}: {count} 条")

    return {
        "status": "success",
        "method": "rule_based",
        "original_count": len(entries),
        "new_count": len(new_entries),
        "prompts_kept": len(kept_prompts),
        "prompts_removed": len(removed_prompts),
        "reason_distribution": reason_counts,
        "backup_path": str(backup_path)
    }


def cleanup_knowledge_base(
    kb_path: Path,
    doc_type: str = "lesson_plan",
    mode: Literal["rule", "llm", "agent", "auto"] = "auto"
) -> Dict[str, Any]:
    """
    清理知识库，删除无用和重复的建议

    支持四种模式：
    - rule: 基于规则快速清理（推荐，速度快，无API调用）
    - llm: 基于LLM分析后一次性清理（需要API，但只调用一次）
    - agent: LLM Agent主动调用工具清理（最智能，多次API调用）
    - auto: 自动选择（默认使用rule模式）

    Args:
        kb_path: 知识库文件路径
        doc_type: 文档类型
        mode: 清理模式

    Returns:
        清理结果统计
    """
    if not kb_path.exists():
        return {"status": "not_found", "message": "知识库文件不存在"}

    # 自动模式：默认使用规则清理（更快，无API成本）
    if mode == "auto":
        mode = "rule"

    # 基于规则清理（推荐）
    if mode == "rule":
        return cleanup_by_rules(kb_path, doc_type)

    # 基于LLM清理（一次性分析）
    if mode == "llm":
        return cleanup_by_llm(kb_path, doc_type)

    # 基于Agent清理（工具调用）
    if mode == "agent":
        from .knowledge_cleaner_agent import cleanup_by_agent
        return cleanup_by_agent(kb_path, doc_type)

    return {"status": "error", "message": f"未知的清理模式: {mode}"}


def cleanup_by_llm(kb_path: Path, doc_type: str = "lesson_plan") -> Dict[str, Any]:
    """
    基于LLM智能清理知识库（原有的LLM清理逻辑）

    Args:
        kb_path: 知识库文件路径
        doc_type: 文档类型

    Returns:
        清理结果统计
    """
    if not kb_path.exists():
        return {"status": "not_found", "message": "知识库文件不存在"}

    # 加载所有知识库条目
    entries = []
    with open(kb_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not entries:
        return {"status": "empty", "message": "知识库为空"}

    print(f"\n📚 开始清理知识库: {kb_path.name}")
    print(f"   原始条目数: {len(entries)}")

    # 提取所有建议
    all_prompts = []
    for entry in entries:
        source = entry.get("source", "vlm")
        timestamp = entry.get("timestamp", "")

        for prompt_item in entry.get("generator_prompts", []):
            all_prompts.append({
                "prompt": prompt_item.get("prompt", ""),
                "source": source,
                "timestamp": timestamp,
                "reason": prompt_item.get("reason", ""),
                "entry": entry  # 保存原始条目引用
            })

    if not all_prompts:
        return {"status": "no_prompts", "message": "没有找到建议"}

    print(f"   总建议数: {len(all_prompts)}")

    # 构建LLM清理提示
    prompts_text = "\n\n".join([
        f"【建议 {i+1}】（来源: {p['source']}）\n{p['prompt'][:200]}..."  # 只显示前200字
        for i, p in enumerate(all_prompts)
    ])

    cleanup_prompt = f"""你是知识库管理专家。请审查以下知识库中的建议，识别并删除：

❌ **必须删除的建议**：
1. **技术实现建议**（如"增强生成器..."、"优化系统逻辑..."、"校准字段长度检查模块..."）
2. **排版布局建议**（如"调整表格列宽..."、"修复文字重叠..."、"引入自动换行..."）
3. **系统机制建议**（如"强化生成器的内容必填校验机制..."、"检查生成逻辑路径..."）
4. **重复的建议**（内容基本相同，只保留一条最精简的）
5. **过于抽象的建议**（如"内容应该详细"，没有具体标准）

✅ **必须保留的建议**：
1. **具体的字段长度限制**（如"姓名≤5字"、"学科≤10字"）
2. **字段内容要求**（如"教学目标应包含知识/能力/情感目标，100-300字"）
3. **字段类型识别规则**（如"基础信息字段应简短（2-20字）"）
4. **具体可操作的建议**（有明确的例子、标准、字数范围）

以下是当前知识库中的所有建议：

{prompts_text}

请返回JSON格式：
{{
  "keep_indices": [保留的建议编号列表，从1开始],
  "remove_reasons": {{
    "2": "技术实现建议",
    "5": "排版布局建议",
    "7": "与建议1重复"
  }},
  "summary": "清理总结（说明保留了什么，删除了什么）"
}}

只输出JSON，不要其他内容。"""

    # 调用LLM
    try:
        dashscope.api_key = DASHSCOPE_API_KEY

        response = dashscope.Generation.call(
            model="qwen-plus",
            messages=[{"role": "user", "content": cleanup_prompt}],
            result_format="message",
        )

        if response.status_code != HTTPStatus.OK:
            return {
                "status": "error",
                "message": f"LLM调用失败: {response.message}"
            }

        # 解析LLM响应
        content = response.output.choices[0].message.content

        # 提取JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            print(f"❌ LLM返回内容:\n{content}")
            return {
                "status": "error",
                "message": "LLM返回格式错误，无法解析JSON"
            }

        result = json.loads(json_match.group(0))
        keep_indices = result.get("keep_indices", [])
        remove_reasons = result.get("remove_reasons", {})
        summary = result.get("summary", "")

        print(f"\n🤖 LLM清理建议:")
        print(f"   保留: {len(keep_indices)}/{len(all_prompts)} 条建议")
        print(f"   删除: {len(all_prompts) - len(keep_indices)} 条建议")
        print(f"   总结: {summary}")

        # 重建知识库（只保留manual来源的完整条目 + 筛选后的VLM建议）
        new_entries = []

        # 1. 保留所有manual来源的条目
        manual_count = 0
        for entry in entries:
            if entry.get("source") == "manual":
                new_entries.append(entry)
                manual_count += 1

        if manual_count > 0:
            print(f"   ✅ 保留 {manual_count} 条人工条目")

        # 2. 如果有保留的VLM建议，创建新的合并条目
        if keep_indices:
            kept_prompts = [all_prompts[i-1] for i in keep_indices if 0 < i <= len(all_prompts)]

            if kept_prompts:
                # 创建合并后的VLM条目
                merged_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "doc_type": doc_type,
                    "doc_type_name": "教案" if doc_type == "lesson_plan" else doc_type,
                    "source": "vlm_cleaned",
                    "severity": "high",
                    "annotator_prompts": [],
                    "generator_prompts": [
                        {
                            "prompt": p["prompt"],
                            "reason": p.get("reason", "LLM筛选保留"),
                            "root_cause": "generator"
                        }
                        for p in kept_prompts
                    ],
                    "key_insights": [
                        "知识库已通过LLM清理，删除了技术实现、排版布局等无关建议"
                    ],
                    "next_steps": [],
                    "metadata": {
                        "pipeline_version": "v5",
                        "cleanup_summary": summary,
                        "cleanup_time": datetime.now().isoformat()
                    }
                }
                new_entries.append(merged_entry)
                print(f"   ✅ 创建清理后的VLM合并条目: {len(kept_prompts)} 条建议")

        # 3. 备份原文件
        backup_path = kb_path.with_suffix(f".jsonl.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy(kb_path, backup_path)
        print(f"   💾 备份原文件: {backup_path.name}")

        # 4. 写入新的知识库
        with open(kb_path, "w", encoding="utf-8") as f:
            for entry in new_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        print(f"   ✅ 知识库已更新: {len(new_entries)} 条记录")

        # 打印删除的建议（前5条）
        if remove_reasons:
            print(f"\n❌ 删除的建议示例（前5条）:")
            for idx, reason in list(remove_reasons.items())[:5]:
                idx_int = int(idx)
                if 0 < idx_int <= len(all_prompts):
                    prompt_preview = all_prompts[idx_int-1]["prompt"][:80]
                    print(f"   [{idx}] {reason}")
                    print(f"        {prompt_preview}...")

        return {
            "status": "success",
            "original_count": len(entries),
            "new_count": len(new_entries),
            "prompts_kept": len(keep_indices),
            "prompts_removed": len(all_prompts) - len(keep_indices),
            "summary": summary,
            "backup_path": str(backup_path)
        }

    except Exception as e:
        import traceback
        print(f"❌ 清理失败: {e}")
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"清理失败: {str(e)}"
        }


if __name__ == "__main__":
    import sys

    # 测试清理功能
    kb_path = Path("knowledge/lesson_plan/experiences.jsonl")

    # 支持命令行参数选择模式
    mode = "rule"  # 默认使用规则清理
    if len(sys.argv) > 1:
        mode = sys.argv[1]

    print(f"🔧 清理模式: {mode}")
    print(f"   rule  - 基于规则快速清理（推荐）")
    print(f"   llm   - LLM一次性分析清理")
    print(f"   agent - LLM Agent工具调用清理（最智能）")
    print(f"   auto  - 自动选择（默认rule）")

    result = cleanup_knowledge_base(kb_path, mode=mode)

    print(f"\n📊 清理结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
