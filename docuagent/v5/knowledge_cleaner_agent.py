"""
知识库清理Agent - 让LLM主动调用工具清理知识库

支持工具:
1. read_kb() - 读取知识库内容
2. list_prompts() - 列出所有建议
3. delete_prompts(indices) - 删除指定建议
4. rewrite_prompt(index, new_text) - 重写指定建议
5. merge_prompts(indices, merged_text) - 合并多条建议
6. add_prompt(text, reason) - 添加新建议
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from http import HTTPStatus
import dashscope

from config.settings import DASHSCOPE_API_KEY


class KnowledgeBaseTools:
    """知识库操作工具集"""

    def __init__(self, kb_path: Path):
        self.kb_path = kb_path
        self.entries = []
        self.all_prompts = []  # [{prompt, source, timestamp, entry_idx, prompt_idx}]
        self._load()

    def _load(self):
        """加载知识库"""
        if not self.kb_path.exists():
            raise FileNotFoundError(f"知识库文件不存在: {self.kb_path}")

        self.entries = []
        with open(self.kb_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # 提取所有建议
        self.all_prompts = []
        for entry_idx, entry in enumerate(self.entries):
            source = entry.get("source", "vlm")
            timestamp = entry.get("timestamp", "")

            for prompt_idx, prompt_item in enumerate(entry.get("generator_prompts", [])):
                self.all_prompts.append({
                    "prompt": prompt_item.get("prompt", ""),
                    "source": source,
                    "timestamp": timestamp,
                    "reason": prompt_item.get("reason", ""),
                    "entry_idx": entry_idx,
                    "prompt_idx": prompt_idx,
                })

    def read_kb(self) -> Dict[str, Any]:
        """读取知识库内容"""
        return {
            "total_entries": len(self.entries),
            "total_prompts": len(self.all_prompts),
            "entries": [
                {
                    "source": e.get("source", "vlm"),
                    "timestamp": e.get("timestamp", ""),
                    "prompts_count": len(e.get("generator_prompts", []))
                }
                for e in self.entries
            ]
        }

    def list_prompts(self, source_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出所有建议

        Args:
            source_filter: 过滤来源 (manual/vlm/None=全部)
        """
        prompts = []
        for idx, p in enumerate(self.all_prompts, start=1):
            if source_filter and p["source"] != source_filter:
                continue

            prompts.append({
                "index": idx,
                "prompt": p["prompt"],
                "source": p["source"],
                "reason": p["reason"],
                "length": len(p["prompt"])
            })

        return prompts

    def delete_prompts(self, indices: List[int]) -> Dict[str, Any]:
        """
        删除指定建议

        Args:
            indices: 建议编号列表（从1开始）

        Returns:
            删除结果
        """
        if not indices:
            return {"status": "error", "message": "未指定删除的建议"}

        # 标记要删除的建议
        deleted = []
        for idx in sorted(set(indices), reverse=True):  # 从后往前删除
            if 0 < idx <= len(self.all_prompts):
                prompt_info = self.all_prompts[idx - 1]

                # 不允许删除manual来源的建议
                if prompt_info["source"] == "manual":
                    continue

                deleted.append({
                    "index": idx,
                    "prompt": prompt_info["prompt"][:100] + "..."
                })

                # 从对应的entry中删除
                entry = self.entries[prompt_info["entry_idx"]]
                if "generator_prompts" in entry and prompt_info["prompt_idx"] < len(entry["generator_prompts"]):
                    entry["generator_prompts"].pop(prompt_info["prompt_idx"])

        # 重新加载（更新索引）
        self._reload_from_entries()

        return {
            "status": "success",
            "deleted_count": len(deleted),
            "deleted_prompts": deleted[:5]  # 只显示前5条
        }

    def rewrite_prompt(self, index: int, new_text: str) -> Dict[str, Any]:
        """
        重写指定建议

        Args:
            index: 建议编号（从1开始）
            new_text: 新的建议文本
        """
        if not (0 < index <= len(self.all_prompts)):
            return {"status": "error", "message": f"无效的索引: {index}"}

        prompt_info = self.all_prompts[index - 1]

        # 不允许重写manual来源的建议
        if prompt_info["source"] == "manual":
            return {"status": "error", "message": "不允许重写人工添加的建议"}

        # 更新entry中的建议
        entry = self.entries[prompt_info["entry_idx"]]
        if "generator_prompts" in entry and prompt_info["prompt_idx"] < len(entry["generator_prompts"]):
            old_text = entry["generator_prompts"][prompt_info["prompt_idx"]]["prompt"]
            entry["generator_prompts"][prompt_info["prompt_idx"]]["prompt"] = new_text
            entry["generator_prompts"][prompt_info["prompt_idx"]]["reason"] = "LLM重写优化"

        # 重新加载
        self._reload_from_entries()

        return {
            "status": "success",
            "index": index,
            "old_text": old_text[:100] + "...",
            "new_text": new_text[:100] + "..."
        }

    def merge_prompts(self, indices: List[int], merged_text: str) -> Dict[str, Any]:
        """
        合并多条建议为一条

        Args:
            indices: 要合并的建议编号列表
            merged_text: 合并后的文本
        """
        if len(indices) < 2:
            return {"status": "error", "message": "至少需要2条建议才能合并"}

        # 检查所有建议都不是manual来源
        for idx in indices:
            if 0 < idx <= len(self.all_prompts):
                if self.all_prompts[idx - 1]["source"] == "manual":
                    return {"status": "error", "message": f"不能合并人工建议 (索引 {idx})"}

        # 保留第一条，删除其他
        first_idx = min(indices)
        other_indices = [i for i in indices if i != first_idx]

        # 重写第一条
        rewrite_result = self.rewrite_prompt(first_idx, merged_text)
        if rewrite_result["status"] != "success":
            return rewrite_result

        # 删除其他
        delete_result = self.delete_prompts(other_indices)

        return {
            "status": "success",
            "merged_index": first_idx,
            "deleted_indices": other_indices,
            "merged_text": merged_text[:100] + "..."
        }

    def add_prompt(self, text: str, reason: str = "LLM新增建议") -> Dict[str, Any]:
        """
        添加新建议

        Args:
            text: 建议文本
            reason: 添加理由
        """
        # 找到第一个VLM来源的entry，或创建新的
        vlm_entry = None
        for entry in self.entries:
            if entry.get("source") != "manual":
                vlm_entry = entry
                break

        if not vlm_entry:
            # 创建新的VLM条目
            vlm_entry = {
                "timestamp": datetime.now().isoformat(),
                "doc_type": "lesson_plan",
                "source": "llm_agent",
                "severity": "high",
                "generator_prompts": []
            }
            self.entries.append(vlm_entry)

        # 添加建议
        vlm_entry["generator_prompts"].append({
            "prompt": text,
            "reason": reason,
            "root_cause": "generator"
        })

        # 重新加载
        self._reload_from_entries()

        return {
            "status": "success",
            "message": f"已添加新建议 (总计 {len(self.all_prompts)} 条)",
            "prompt": text[:100] + "..."
        }

    def _reload_from_entries(self):
        """从entries重新加载all_prompts"""
        self.all_prompts = []
        for entry_idx, entry in enumerate(self.entries):
            source = entry.get("source", "vlm")
            timestamp = entry.get("timestamp", "")

            for prompt_idx, prompt_item in enumerate(entry.get("generator_prompts", [])):
                self.all_prompts.append({
                    "prompt": prompt_item.get("prompt", ""),
                    "source": source,
                    "timestamp": timestamp,
                    "reason": prompt_item.get("reason", ""),
                    "entry_idx": entry_idx,
                    "prompt_idx": prompt_idx,
                })

    def save(self, backup: bool = True) -> Path:
        """
        保存知识库

        Args:
            backup: 是否备份原文件

        Returns:
            备份文件路径（如果进行了备份）
        """
        backup_path = None
        if backup and self.kb_path.exists():
            backup_path = self.kb_path.with_suffix(
                f".jsonl.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            shutil.copy(self.kb_path, backup_path)

        # 写入新文件
        with open(self.kb_path, "w", encoding="utf-8") as f:
            for entry in self.entries:
                # 移除空的generator_prompts
                if "generator_prompts" in entry and not entry["generator_prompts"]:
                    continue
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return backup_path


def cleanup_by_agent(kb_path: Path, doc_type: str = "lesson_plan") -> Dict[str, Any]:
    """
    使用LLM Agent清理知识库（支持工具调用）

    Args:
        kb_path: 知识库路径
        doc_type: 文档类型

    Returns:
        清理结果
    """
    print(f"\n🤖 启动LLM Agent清理知识库: {kb_path.name}")

    # 初始化工具
    tools = KnowledgeBaseTools(kb_path)

    # 读取知识库
    kb_info = tools.read_kb()
    prompts = tools.list_prompts()

    print(f"   知识库条目: {kb_info['total_entries']}")
    print(f"   总建议数: {kb_info['total_prompts']}")

    # 构建工具描述
    tool_descriptions = """
你有以下工具可以使用:

1. read_kb() - 读取知识库总体信息
2. list_prompts(source_filter="vlm"|"manual"|None) - 列出所有建议
3. delete_prompts([1,2,3]) - 删除指定编号的建议（支持批量）
4. rewrite_prompt(index=1, new_text="...") - 重写指定建议
5. merge_prompts([1,2,3], merged_text="...") - 合并多条建议
6. add_prompt(text="...", reason="...") - 添加新建议

⚠️ 注意:
- 人工添加(manual)的建议不能删除/修改
- 只能操作VLM生成的建议
- 索引从1开始
"""

    # 构建建议列表
    prompts_text = "\n".join([
        f"【{i}】({p['source']}, {p['length']}字) {p['prompt'][:150]}{'...' if p['length'] > 150 else ''}"
        for i, p in enumerate(prompts, start=1)
    ])

    # 构建清理提示
    cleanup_prompt = f"""你是知识库清理专家。当前知识库有 {len(prompts)} 条建议。

{tool_descriptions}

**清理目标**:
❌ 删除: 技术实现、排版布局、系统机制、重复、过于抽象的建议
✅ 保留: 字段长度限制、内容要求、类型识别规则、具体可操作的建议

**当前所有建议**:
{prompts_text}

**执行步骤**:
1. 先调用 list_prompts() 查看所有建议
2. 分析哪些建议应该删除/合并/重写
3. 依次调用工具执行操作
4. 最后总结清理结果

请开始清理！一步步执行工具调用。

⚠️ 重要：你必须使用JSON格式输出工具调用，格式如下：
```json
{{
  "tool": "delete_prompts",
  "args": {{
    "indices": [2, 5, 7]
  }},
  "reason": "删除技术实现建议"
}}
```

每次只调用一个工具，我会返回结果后你再继续。"""

    # 调用LLM
    dashscope.api_key = DASHSCOPE_API_KEY

    messages = [{"role": "user", "content": cleanup_prompt}]
    max_iterations = 20  # 最多20轮对话
    operations = []

    for iteration in range(max_iterations):
        print(f"\n🔄 迭代 {iteration + 1}/{max_iterations}")

        try:
            response = dashscope.Generation.call(
                model="qwen-plus",
                messages=messages,
                result_format="message",
            )

            if response.status_code != HTTPStatus.OK:
                return {
                    "status": "error",
                    "message": f"LLM调用失败: {response.message}"
                }

            # 获取LLM响应
            content = response.output.choices[0].message.content
            print(f"🤖 LLM响应: {content[:200]}...")

            # 添加到对话历史
            messages.append({"role": "assistant", "content": content})

            # 检查是否完成
            if "清理完成" in content or "总结" in content or "完成清理" in content:
                print("✅ LLM表示清理完成")
                break

            # 提取JSON工具调用
            json_match = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', content)
            if not json_match:
                json_match = re.search(r'\{[\s\S]*?"tool"[\s\S]*?\}', content)

            if not json_match:
                # LLM可能在思考或总结，继续
                user_msg = "请继续使用工具执行清理操作，或者说明清理完成。"
                messages.append({"role": "user", "content": user_msg})
                continue

            # 解析工具调用
            try:
                tool_call = json.loads(json_match.group(1) if json_match.lastindex else json_match.group(0))
            except json.JSONDecodeError:
                user_msg = "JSON格式错误，请重新输出工具调用。"
                messages.append({"role": "user", "content": user_msg})
                continue

            tool_name = tool_call.get("tool", "")
            tool_args = tool_call.get("args", {})
            tool_reason = tool_call.get("reason", "")

            print(f"🔧 工具调用: {tool_name}({tool_args}) - {tool_reason}")

            # 执行工具
            result = None
            if tool_name == "list_prompts":
                result = tools.list_prompts(tool_args.get("source_filter"))
            elif tool_name == "delete_prompts":
                result = tools.delete_prompts(tool_args.get("indices", []))
                operations.append({
                    "operation": "delete",
                    "count": result.get("deleted_count", 0)
                })
            elif tool_name == "rewrite_prompt":
                result = tools.rewrite_prompt(
                    tool_args.get("index", 0),
                    tool_args.get("new_text", "")
                )
                operations.append({
                    "operation": "rewrite",
                    "index": tool_args.get("index")
                })
            elif tool_name == "merge_prompts":
                result = tools.merge_prompts(
                    tool_args.get("indices", []),
                    tool_args.get("merged_text", "")
                )
                operations.append({
                    "operation": "merge",
                    "count": len(tool_args.get("indices", []))
                })
            elif tool_name == "add_prompt":
                result = tools.add_prompt(
                    tool_args.get("text", ""),
                    tool_args.get("reason", "LLM新增")
                )
                operations.append({
                    "operation": "add",
                    "text": tool_args.get("text", "")[:50]
                })
            else:
                result = {"status": "error", "message": f"未知工具: {tool_name}"}

            print(f"✅ 工具结果: {result}")

            # 返回结果给LLM
            user_msg = f"工具执行结果: {json.dumps(result, ensure_ascii=False)}\n\n请继续清理或总结。"
            messages.append({"role": "user", "content": user_msg})

        except Exception as e:
            import traceback
            print(f"❌ 迭代失败: {e}")
            traceback.print_exc()
            break

    # 保存知识库
    backup_path = tools.save(backup=True)

    print(f"\n📊 清理统计:")
    print(f"   原始建议数: {kb_info['total_prompts']}")
    print(f"   当前建议数: {len(tools.all_prompts)}")
    print(f"   执行操作数: {len(operations)}")
    print(f"   备份文件: {backup_path}")

    return {
        "status": "success",
        "method": "agent_based",
        "original_count": kb_info['total_prompts'],
        "new_count": len(tools.all_prompts),
        "operations": operations,
        "backup_path": str(backup_path) if backup_path else None
    }


if __name__ == "__main__":
    import sys

    kb_path = Path("knowledge/lesson_plan/experiences.jsonl")

    if len(sys.argv) > 1:
        kb_path = Path(sys.argv[1])

    result = cleanup_by_agent(kb_path)

    print(f"\n📊 最终结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
