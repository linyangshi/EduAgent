"""
内容生成的 LLM Prompts（简化版，利用 Kimi 推理能力）
"""

import re
from typing import Dict, List, Optional
from .field_constraints import get_enhanced_field_constraints, FieldConstraintValidator


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
    span_match = re.search(r'span=(\d+)', marker)  # 🔥 新增：提取span（跨列数）

    if col_match and row_match and table_match:
        col_index = int(col_match.group(1))
        span = int(span_match.group(1)) if span_match else 1

        # 🔥 修复：只有当grid_col=0且span=1时才是"第一列"
        # 如果span>1，说明是跨列合并单元格（整行内容），不应被视为"第一列"
        is_first_column = (col_index == 0 and span == 1)

        return {
            "col_index": col_index,
            "row_index": int(row_match.group(1)),
            "table_id": table_match.group(1),
            "is_first_column": is_first_column,
            "span": span,  # 返回span信息供调试
        }

    return None


def _build_position_hint(field_analysis: Dict) -> str:
    """
    构建位置提示文本（从annotation的marker解析）

    Args:
        field_analysis: 字段分析结果（包含annotation）

    Returns:
        位置提示字符串，如果是表格第一列会特别强调
    """
    print(f"🔍 [DEBUG] _build_position_hint 被调用")
    print(f"   field_analysis keys: {field_analysis.keys() if isinstance(field_analysis, dict) else 'NOT A DICT'}")

    # 🔥 修复：annotation可能是None，需要提供默认值
    annotation = field_analysis.get("annotation") or {}
    print(f"   annotation keys: {annotation.keys() if isinstance(annotation, dict) else 'NOT A DICT'}")
    
    # 🔥 修复：优先使用 cell_marker，如果不存在再使用 marker
    marker = annotation.get("cell_marker", "") or annotation.get("marker", "")
    print(f"   marker (from cell_marker or marker): {marker[:100] if marker else 'EMPTY'}")

    pos_info = _extract_position_from_marker(marker)
    print(f"   pos_info: {pos_info}")
    
    if not pos_info:
        print(f"   ❌ 没有位置信息，返回空字符串")
        return ""

    hints = []
    table_id = pos_info["table_id"]
    row_idx = pos_info["row_index"]
    col_idx = pos_info["col_index"]
    is_first_col = pos_info["is_first_column"]

    # 基本位置信息
    hints.append(f"- 位置: 表格 {table_id} 第{row_idx+1}行 第{col_idx+1}列")

    # 🔥 关键：如果是第一列，只标记位置，具体限制由知识库引导
    if is_first_col:
        hints.append("- ⚠️ **这是表格第一列（索引列/分类列）**")

    result = "\n".join(hints)
    print(f"   ✅ 返回位置提示: {len(result)} 字符")
    return result


def create_content_generation_prompt(
    field_analysis: Dict,
    user_input: Dict,
    generated_content: Dict[str, str],
    kb_insights: str = "",  # ✅ 新增: 知识库洞察
) -> str:
    """创建内容生成 prompt（简化版）"""
    print(f"\n🔍 [DEBUG] create_content_generation_prompt 被调用")
    print(f"   placeholder: {field_analysis.get('placeholder', 'N/A')}")
    print(f"   kb_insights长度: {len(kb_insights)} 字符")
    
    placeholder = field_analysis["placeholder"]
    content_type = field_analysis["content_type"]
    length_req = field_analysis["length_requirement"]
    style = field_analysis["style"]

    # 构建上下文信息
    context_lines = []

    # 用户输入
    if "prompt" in user_input and user_input["prompt"]:
        context_lines.append(f"**用户需求**: {user_input['prompt']}")

    basic_info = user_input.get("basic_info", {})
    if basic_info:
        context_lines.append("\n**课程信息**:")
        for key, value in basic_info.items():
            context_lines.append(f"- {key}: {value}")

    # 🔥 新增：字段描述（从annotation的reason获取）
    annotation = field_analysis.get("annotation") or {}
    reason = annotation.get("reason", "")
    if reason and reason.strip():
        context_lines.append(f"\n**字段说明**: {reason}")

    # 已生成内容（仅关键字段）
    if generated_content:
        context_lines.append("\n**已生成内容**:")
        for dep in field_analysis.get("dependencies", [])[:3]:  # 只显示前3个依赖
            if dep in generated_content:
                content = generated_content[dep][:100] + "..." if len(generated_content[dep]) > 100 else generated_content[dep]
                context_lines.append(f"- {dep}: {content}")

    context_text = "\n".join(context_lines) if context_lines else "无上下文"

    # 长度描述
    min_chars = length_req.get("min_chars", 50)
    max_chars = length_req.get("max_chars", 200)
    target_items = length_req.get("target_items", 1)

    if style == "structured_list":
        length_desc = f"{target_items} 条结构化条目"
    elif max_chars <= 50:
        length_desc = f"简短（{min_chars}-{max_chars}字）"
    elif max_chars <= 200:
        length_desc = f"中等（{min_chars}-{max_chars}字）"
    else:
        length_desc = f"详细（{min_chars}-{max_chars}字）"

    # 构建知识库约束部分
    kb_constraints = ""
    if kb_insights and kb_insights.strip():
        kb_constraints = f"\n{kb_insights.strip()}\n"
        print(f"   ✅ 添加知识库约束: {len(kb_constraints)} 字符")
    else:
        print(f"   ❌ 没有知识库约束")

    # 🔥 新增：构建位置提示
    print(f"   🔍 准备调用 _build_position_hint...")
    position_hint = _build_position_hint(field_analysis)
    field_type = field_analysis.get("field_type", "unknown")

    # 🔥 新增：构建字段信息部分
    field_info_lines = [
        f"- 字段名: {placeholder}",
        f"- 字段类型: {field_type}",
    ]
    if position_hint:
        field_info_lines.append(position_hint)
        print(f"   ✅ 添加位置信息到prompt")
    else:
        print(f"   ❌ 没有位置信息")

    field_info_section = "## 字段信息\n" + "\n".join(field_info_lines)

    # 根据文档类型确定文档名称
    doc_type_names = {
        "lesson_plan": "教案",
        "task_proposal": "任务书",
        "thesis": "论文",
        "report": "报告"
    }
    doc_type = user_input.get("doc_type", "lesson_plan")
    doc_name = doc_type_names.get(doc_type, "文档")

    prompt = f"""请生成{doc_name}字段"{content_type}"的内容。

{field_info_section}

## 上下文
{context_text}
{kb_constraints}
## 要求
- 长度: {length_desc}
- 风格: {style}

**重要**: 直接输出内容文本，不要包含标签名、花括号或占位符。

内容："""

    return prompt


def create_batch_generation_prompt(
    field_analyses: List[Dict],
    user_input: Dict,
    generated_content: Dict[str, str],
    kb_insights: str = "",
    doc_type: str = "task_proposal",  # 新增：文档类型
    use_enhanced_constraints: bool = True,  # 新增：是否使用增强约束
) -> str:
    """创建批量生成 prompt（简化版，支持强约束）"""
    # 提取核心信息
    prompt_text = user_input.get("prompt", "")
    basic_info = user_input.get("basic_info", {})

    # 构建基础信息文本
    info_lines = []
    if prompt_text:
        info_lines.append(f"用户需求: {prompt_text}")
    if basic_info.get("course_name"):
        info_lines.append(f"课程: {basic_info['course_name']}")
    if basic_info.get("teacher_name"):
        info_lines.append(f"教师: {basic_info['teacher_name']}")

    info_text = "\n".join(info_lines) if info_lines else "无特定要求"

    # 示例字段键（用于 JSON 格式说明）
    example_keys = [f["placeholder"] for f in field_analyses[:min(2, len(field_analyses))]]

    # 构建知识库部分
    kb_section = ""
    if kb_insights and kb_insights.strip():
        kb_section = f"\n{kb_insights.strip()}\n"

    # 🔥 新增：使用增强约束（字段类型、长度、验证规则）
    if use_enhanced_constraints:
        constraints_text = get_enhanced_field_constraints(field_analyses, doc_type)
        fields_section = constraints_text
    else:
        # 旧版：简单的字段列表（但添加位置信息）
        fields_list = []
        for i, analysis in enumerate(field_analyses, 1):
            placeholder = analysis["placeholder"]
            content_type = analysis["content_type"]
            field_type = analysis.get("field_type", "unknown")
            length_req = analysis["length_requirement"]

            min_chars = length_req.get("min_chars", 50)
            max_chars = length_req.get("max_chars", 200)

            # 🔥 添加位置信息
            position_hint = _build_position_hint(analysis)
            
            field_desc = f"{i}. **{placeholder}** ({content_type}, {field_type}): {min_chars}-{max_chars}字"
            if position_hint:
                # 提取简化的位置信息（只保留关键部分）
                position_lines = position_hint.split('\n')
                if position_lines:
                    # 只保留第一行位置信息
                    field_desc += f"\n   {position_lines[0]}"
            
            fields_list.append(field_desc)

        fields_section = "## 需要生成的字段\n" + "\n".join(fields_list)

    # 🔥 新增：添加文档类型名称
    doc_type_names = {
        "lesson_plan": "教案",
        "task_proposal": "任务书",
        "thesis": "论文",
        "report": "报告"
    }
    doc_name = doc_type_names.get(doc_type, "文档")

    prompt = f"""请一次性生成以下{doc_name}的 {len(field_analyses)} 个字段的内容，确保严格遵守每个字段的约束要求。

## 背景信息
{info_text}

{fields_section}
{kb_section}
## ❗ 输出要求

1. **严格遵守字段约束**：
   - 每个字段的字符数必须在约束范围内
   - 内容必须符合字段类型的语义要求

2. **字符数计算**：
   - 直接统计文本长度，不包括JSON格式字符
   - 生成前先估算字数，确保符合要求

## 输出格式
以 JSON 格式输出（不要添加 Markdown 代码块标记）：

{{
  "{example_keys[0]}": "生成的内容...",
  "{example_keys[1] if len(example_keys) > 1 else 'field2'}": "生成的内容...",
  ...
}}

**重要**: 字段值不要包含花括号或占位符，直接写内容文本。

请输出 JSON："""

    return prompt


def create_quality_check_prompt(content: str, field_analysis: Dict) -> str:
    """创建质量检查 prompt（简化版）"""
    content_type = field_analysis["content_type"]
    min_chars = field_analysis["length_requirement"].get("min_chars", 50)
    max_chars = field_analysis["length_requirement"].get("max_chars", 200)

    prompt = f"""请检查以下"{content_type}"内容的质量：

{content}

要求: {min_chars}-{max_chars}字

返回 JSON:
{{
  "passed": true/false,
  "score": 0.0-1.0,
  "issues": ["问题列表"]
}}
"""

    return prompt
