"""
知识库智能精简模块
使用LLM分析知识库条目，识别冗余、过时或低价值的条目并删除
"""

import json
from pathlib import Path
from typing import List, Dict, Any

try:
    import dashscope
    from dashscope import Generation
    from config.settings import DASHSCOPE_API_KEY
    dashscope.api_key = DASHSCOPE_API_KEY
    HAS_DASHSCOPE = True
except ImportError:
    HAS_DASHSCOPE = False


def _call_pruner_llm(prompt: str) -> str:
    """调用LLM进行知识库精简分析"""
    if not HAS_DASHSCOPE:
        raise RuntimeError("需要dashscope库进行知识库精简")
    
    response = Generation.call(
        model="qwen-plus",
        prompt=prompt,
        temperature=0.3,
        result_format='message',
        max_tokens=2000,
    )
    
    if response.status_code == 200:
        return response.output.choices[0].message.content or ""
    else:
        raise RuntimeError(f"LLM调用失败: {response.message}")


def _build_pruning_prompt(entries: List[Dict[str, Any]], target_size: int) -> str:
    """构建知识库精简prompt"""
    
    # 提取关键信息
    summary_lines = []
    for i, entry in enumerate(entries, 1):
        timestamp = entry.get("timestamp", "")[:10]  # 只取日期
        severity = entry.get("severity", "unknown")
        ann_count = len(entry.get("annotator_prompts", []))
        gen_count = len(entry.get("generator_prompts", []))
        
        # 提取前2条建议作为示例
        ann_samples = [p.get("prompt", "")[:50] for p in entry.get("annotator_prompts", [])[:2]]
        gen_samples = [p.get("prompt", "")[:50] for p in entry.get("generator_prompts", [])[:2]]
        
        summary_lines.append(
            f"{i}. [{timestamp}] 严重度:{severity} | 标注建议:{ann_count}条 | 生成建议:{gen_count}条\n"
            f"   标注示例: {', '.join(ann_samples) if ann_samples else '无'}\n"
            f"   生成示例: {', '.join(gen_samples) if gen_samples else '无'}"
        )
    
    summary_text = "\n".join(summary_lines)
    
    prompt = f"""# 知识库精简任务

你是一个知识库管理专家。当前知识库有 {len(entries)} 条经验记录，需要精简到 {target_size} 条左右。

## 精简原则

1. **保留高价值条目**：
   - 严重度高的问题（critical/high）
   - 建议具体、可操作的条目
   - 最近的经验（更符合当前系统状态）

2. **删除低价值条目**：
   - 重复或相似的建议
   - 过于通用、不具体的建议
   - 已经被后续经验覆盖的旧问题
   - 严重度低且建议数量少的条目

3. **保持多样性**：
   - 保留不同类型的问题（标注问题、生成问题）
   - 保留不同严重度级别的代表性案例

## 知识库条目摘要

{summary_text}

## 输出格式

请输出一个JSON对象，包含要**删除**的条目编号列表：

```json
{{
  "to_delete": [1, 5, 8, 12, ...],
  "reason": "删除理由的简要说明"
}}
```

请立即输出精简方案："""
    
    return prompt


def prune_knowledge_base_with_llm(kb_path: Path, target_size: int = 30) -> int:
    """
    使用LLM智能精简知识库
    
    Args:
        kb_path: 知识库文件路径
        target_size: 目标保留条目数
    
    Returns:
        删除的条目数
    """
    # 加载所有条目
    entries = []
    with open(kb_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    
    # 最新的在前
    entries = list(reversed(entries))
    
    if len(entries) <= target_size:
        return 0
    
    # 调用LLM分析
    prompt = _build_pruning_prompt(entries, target_size)
    response = _call_pruner_llm(prompt)
    
    # 解析响应
    import re
    response = response.strip()
    if response.startswith("```json"):
        response = response[7:]
    elif response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    response = response.strip()
    
    try:
        result = json.loads(response)
    except json.JSONDecodeError:
        match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
        else:
            raise ValueError("无法解析LLM响应")
    
    to_delete = set(result.get("to_delete", []))
    reason = result.get("reason", "")
    
    print(f"   📋 LLM建议删除 {len(to_delete)} 条: {reason}")
    
    # 保留未被删除的条目
    entries_to_keep = [entry for i, entry in enumerate(entries, 1) if i not in to_delete]
    
    # 重写文件
    with open(kb_path, "w", encoding="utf-8") as f:
        for entry in reversed(entries_to_keep):  # 恢复时间顺序（旧的在前）
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    return len(to_delete)

