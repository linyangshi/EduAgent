"""
LLM annotation pipeline for v4 Markdown templates.

Uses LangGraph to orchestrate a multi-attempt loop:
1. “标注器”节点调用 Fireworks DeepSeek-V3P1-Terminus 模型生成 JSON 标注；
2. “检查器”节点解析输出并判断是否完整（默认共用 Terminus，可通过环境变量覆盖）；
3. 如果不完整，向 LLM 发送补充指令继续生成，直到解析成功或达到最大尝试次数；
4. 若依旧失败，再调用 Fireworks JSON 修复模型（Qwen3-Coder-480B-A35B-Instruct）。

Outputs aggregated annotations and raw responses for审查。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langgraph.graph import END, StateGraph

from .llm_annotator import (
    GITCODE_MODEL,
    DEFAULT_MAX_TOKENS,
    stream_gitcode_chat,
    call_gitcode_llm,
    create_annotation_prompt,
    call_checker_llm,
    call_json_repair_llm,
    TemplateTooComplexError,
)

DEFAULT_MD_PATH = Path("results/v4_markdown/未标注模板2_v4.md")
DEFAULT_OUTPUT_DIR = Path("results/v4_llm_annotation_fireworks")
DEFAULT_FEATURES_SUFFIX = "_features.md"
MAX_SEGMENT_CHARS = 9000
MAX_ATTEMPTS = 8  # 增加到8次，为长文档提供更多重试机会
MAX_INLINE_FEATURE_CHARS = 6000
COMPACT_HINT_LIMIT = 12

HEADER_KEYWORDS = {
    "教学内容", "教师活动", "学生活动", "设计意图",
    "思政目标", "知识目标", "能力目标", "素养目标",
    "教学目标", "教学重点", "教学难点", "教学方法",
    "教学过程", "教学环节", "时间分配", "板书设计",
    "课后反思", "教学反思", "课程思政",
}
TIME_HINT_KEYWORDS = ("年", "月", "日", "周", "星期", "节", "分钟", "学时")

SYSTEM_MESSAGE = {
    "role": "system",
    "content": "你是一个教案模板标注专家。你的任务是分析未标注的教案模板 Markdown，输出合法 JSON 标注方案。",
}
CONTINUE_PROMPT = (
    "你的上一条回答未能提供完整 JSON。请继续补全剩余部分，保持相同结构，直接延续输出，"
    "不要重新开始，不要添加解释或额外文本，只输出剩余的 JSON 内容。"
)

# 清理 JSON 文本中的控制字符、制表符与多余代码围栏
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Example-like content detectors (promote to MUST-REPLACE hints)
EX_ELLIPSIS_RE = re.compile(r"(…{2,}|\.{3,})")  # 多个省略号
EX_BULLET_RE = re.compile(r"(^|<br>)\s*(?:\d{1,2}|[一二三四五六七八九十]+)[\.|、]")  # 编号列表
EX_DOTCHAR_RE = re.compile(r"•")  # 项目符号
EX_GENERIC_X_RE = re.compile(r"(?:^|[\s，。])XX(?:$|[\s，。课程名称])")  # XX 占位符（支持中文）

# 新增：更多示例内容模式（保持泛化性）
EX_PLACEHOLDER_WORDS = re.compile(r"(待填写|待完善|待补充|TBD|TODO|填写说明)")  # 明确的占位词
EX_VAGUE_CONTENT = re.compile(r"(相关知识点|具体内容|教学活动|实际情况|生活实际)(?!\S)")  # 模糊描述
EX_TRAILING_ELLIPSIS = re.compile(r"[。，、]?…+$")  # 以省略号结尾
EX_REPEATED_PATTERN = re.compile(r"(活动|内容|知识点|案例)[一二三四五1-5][:：]\s*[。…]{1,3}")  # 重复模式
EX_GENERIC_PHRASE = re.compile(r"^(通过|结合|引导|激发|培养).*?…+")  # 通用引导短语 + 省略号


def _clean_json_candidate(text: str) -> str:
    if not text:
        return ""
    cleaned = text.replace("\u0000", "")
    cleaned = cleaned.replace("\r", "")
    cleaned = cleaned.replace("\t", " ")
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = CONTROL_CHAR_PATTERN.sub("", cleaned)
    return cleaned.strip()


@dataclass
class AnnotationState:
    messages: List[Dict[str, str]]
    attempt: int = 0
    raw_responses: List[str] = field(default_factory=list)
    parsed: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    checker_decision: Optional[str] = None
    checker_reason: Optional[str] = None


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def segment_markdown(md_text: str, max_chars: int = MAX_SEGMENT_CHARS) -> List[str]:
    segments: List[str] = []
    current: List[str] = []
    length = 0

    for line in md_text.splitlines(keepends=True):
        if length + len(line) > max_chars and current:
            segments.append("".join(current).strip())
            current = []
            length = 0
        current.append(line)
        length += len(line)

    if current:
        segments.append("".join(current).strip())

    return segments or [md_text]


def _extract_table_cells_from_line(line: str) -> List[Tuple[str, str]]:
    cells: List[Tuple[str, str]] = []
    if "[[DOCX-CELL" not in line or "|" not in line:
        return cells
    parts = line.split("|")
    for seg in parts:
        seg = seg.strip()
        if not seg:
            continue
        if seg.startswith("[[DOCX-CELL") and "]]" in seg:
            end = seg.find("]]") + 2
            marker = seg[:end].strip()
            content = seg[end:].strip()
            cells.append((marker, content))
    return cells


def _looks_like_example(text: str) -> bool:
    """
    判断文本是否像示例内容（需要替换）

    检测模式（保持泛化性）：
    1. 明确占位符：XX、……、待填写
    2. 编号列表但内容空洞
    3. 以省略号结尾的句子
    4. 通用引导短语 + 省略号
    5. 模糊描述词
    6. 重复模式（活动一：…… 活动二：……）
    """
    s = text.replace(" ", "").strip()

    # 1. 明确的占位符
    if EX_ELLIPSIS_RE.search(s):  # 多个省略号
        return True
    if EX_DOTCHAR_RE.search(s):  # • 符号
        return True
    if EX_GENERIC_X_RE.search(s):  # XX
        return True
    if EX_PLACEHOLDER_WORDS.search(text):  # 待填写、TBD 等
        return True

    # 2. 以省略号结尾（如"通过真实案例激发学习兴趣……"）
    if EX_TRAILING_ELLIPSIS.search(text):
        return True

    # 3. 通用引导短语 + 省略号（如"通过……"、"结合……"）
    if EX_GENERIC_PHRASE.search(text):
        return True

    # 4. 重复模式（如"活动一：…… 活动二：……"）
    if EX_REPEATED_PATTERN.search(text):
        return True

    # 5. 模糊描述词（如"相关知识点"、"具体内容"）
    # 但要避免误伤，只有当它单独出现或很短时才认为是示例
    if len(text.strip()) < 15 and EX_VAGUE_CONTENT.search(text):
        return True

    # 6. 编号列表检测（改进：只检测空洞的列表）
    lines = s.split("<br>") if "<br>" in s else [s]
    numbered_lines = 0
    short_lines = 0

    for ln in lines:
        ln_stripped = ln.strip()
        if not ln_stripped:
            continue

        # 检测是否是编号行
        if EX_BULLET_RE.match(ln) or ln_stripped.startswith(("-", "•")):
            numbered_lines += 1
            # 提取编号后的内容
            # 例如 "1. XXX" -> "XXX"
            content_after_number = re.sub(r"^[\d一二三四五六七八九十]+[\.|、]\s*", "", ln_stripped)
            content_after_number = re.sub(r"^[-•]\s*", "", content_after_number)

            # 如果内容很短（<= 5字）或只有省略号/占位符，认为是示例
            if len(content_after_number) <= 5 or content_after_number in ["……", "…", "XX", "XXX"]:
                short_lines += 1

    # 只有当编号列表中大部分行都很短时，才认为是示例
    # 这样 "1. 理解深度学习概念 2. 掌握基本原理" 就不会被误判
    if numbered_lines >= 2 and short_lines >= numbered_lines * 0.7:  # 70% 的行都很短
        return True

    return False


def _detect_example_cells(markdown_segment: str) -> List[Tuple[str, str]]:
    """检测示例单元格，但跳过表头单元格"""
    hints: List[Tuple[str, str]] = []
    for line in markdown_segment.splitlines():
        if "[[DOCX-CELL" not in line:
            continue
        for marker, content in _extract_table_cells_from_line(line):
            if not content:
                continue

            # ⚠️ 跳过表头单元格
            content_stripped = content.strip()
            if any(keyword in content_stripped for keyword in HEADER_KEYWORDS):
                continue  # 不标注表头

            # 检查是否在第一行（通常是表头）
            if "row=0" in marker or "row=1" in marker:
                # 如果内容很短且不像示例，可能是表头
                if len(content_stripped) < 10 and not any(c in content_stripped for c in ["…", "XX", "___"]):
                    continue

            if _looks_like_example(content):
                reason_parts: List[str] = []

                # 收集所有匹配的模式
                if EX_ELLIPSIS_RE.search(content):
                    reason_parts.append("省略号")
                if EX_BULLET_RE.search(content) or content.strip().startswith(("-", "•")):
                    reason_parts.append("编号/项目符号")
                if EX_DOTCHAR_RE.search(content):
                    reason_parts.append("• 符号")
                if EX_GENERIC_X_RE.search(content):
                    reason_parts.append("XX 占位词")
                if EX_PLACEHOLDER_WORDS.search(content):
                    reason_parts.append("占位词（待填写/TBD）")
                if EX_TRAILING_ELLIPSIS.search(content):
                    reason_parts.append("省略号结尾")
                if EX_GENERIC_PHRASE.search(content):
                    reason_parts.append("通用引导短语")
                if EX_REPEATED_PATTERN.search(content):
                    reason_parts.append("重复模式")
                if len(content.strip()) < 15 and EX_VAGUE_CONTENT.search(content):
                    reason_parts.append("模糊描述")

                reason = "/".join(reason_parts) if reason_parts else "示例痕迹"
                hints.append((marker, reason))
    return hints


def _shorten_hint_text(text: str, max_len: int = 24) -> str:
    compact = " ".join(text.replace("<br>", " / ").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3] + "..."


def _build_compact_feature_hints(markdown_segment: str) -> str:
    paragraph_ids = re.findall(r"\[\[DOCX-BLOCK[^\]]*id=(P\d+)", markdown_segment)
    table_ids = sorted(set(re.findall(r"\[\[DOCX-CELL table=([^ ]+)", markdown_segment)))
    example_map = dict(_detect_example_cells(markdown_segment))

    empty_cells: List[str] = []
    example_cells: List[str] = []
    label_cells: List[str] = []
    time_cells: List[str] = []
    wide_title_cells: List[str] = []
    total_cells = 0

    for line in markdown_segment.splitlines():
        if "[[DOCX-CELL" not in line:
            continue
        for marker, content in _extract_table_cells_from_line(line):
            total_cells += 1
            stripped = content.strip()

            row_match = re.search(r"row=(\d+)", marker)
            row_index = int(row_match.group(1)) if row_match else None
            span_match = re.search(r"span=(\d+)", marker)
            span = int(span_match.group(1)) if span_match else 1

            if not stripped:
                if len(empty_cells) < COMPACT_HINT_LIMIT:
                    empty_cells.append(marker)
                continue

            if marker in example_map and len(example_cells) < COMPACT_HINT_LIMIT:
                example_cells.append(f"{marker} => {_shorten_hint_text(stripped)}")

            is_header_like = stripped in HEADER_KEYWORDS or (
                len(stripped) <= 12 and any(keyword in stripped for keyword in HEADER_KEYWORDS)
            )
            if is_header_like and len(label_cells) < COMPACT_HINT_LIMIT:
                label_cells.append(f"{marker} => {_shorten_hint_text(stripped)}")

            if any(keyword in stripped for keyword in TIME_HINT_KEYWORDS) and len(time_cells) < COMPACT_HINT_LIMIT:
                time_cells.append(f"{marker} => {_shorten_hint_text(stripped)}")

            if row_index is not None and row_index > 0 and span >= 6 and len(stripped) <= 20 and len(wide_title_cells) < COMPACT_HINT_LIMIT:
                wide_title_cells.append(f"{marker} => {_shorten_hint_text(stripped)}")

    hint_lines = [
        f"- 本段包含 {len(paragraph_ids)} 个段落块、{total_cells} 个表格单元格，涉及表格：{', '.join(table_ids) if table_ids else '无'}。",
    ]
    if empty_cells:
        hint_lines.append("- 空白单元格优先考虑 `replace`：" + "；".join(empty_cells))
    if example_cells:
        hint_lines.append("- 明显示例/占位痕迹优先 `replace`：" + "；".join(example_cells))
    if label_cells:
        hint_lines.append("- 下列短文本更像标签/表头，本身不要标注：" + "；".join(label_cells))
    if time_cells:
        hint_lines.append("- 含时间/节次信息的单元格通常要拆成更具体字段：" + "；".join(time_cells))
    if wide_title_cells:
        hint_lines.append("- 跨列标题/章节行通常保留原样，不直接追加内容：" + "；".join(wide_title_cells))
    return "\n".join(hint_lines)


def build_prompt_input(
    markdown_segment: str,
    *,
    features_text: Optional[str],
    segment_label: str,
) -> str:
    parts = [
        f"### Markdown 片段（{segment_label}）",
        markdown_segment.strip(),
    ]
    # Auto-detect example-like cells in this segment
    example_hints = _detect_example_cells(markdown_segment)
    if example_hints:
        parts.extend([
            "",
            "### 强制替换候选（检测到示例/占位痕迹，务必在 annotations 中以 action=\"replace\" 标注）",
        ])
        for marker, reason in example_hints[:80]:
            parts.append(f"- {marker}  // 原因：{reason}")
    compact_hints = _build_compact_feature_hints(markdown_segment)
    if compact_hints:
        parts.extend(
            [
                "",
                "### 紧凑结构提示",
                compact_hints,
            ]
        )
    if features_text and len(features_text) <= MAX_INLINE_FEATURE_CHARS:
        parts.extend(
            [
                "",
                "### 模板特征摘要",
                features_text.strip(),
            ]
        )
    elif features_text:
        parts.extend(
            [
                "",
                "### 模板特征摘要",
                f"原始特征摘要较长（{len(features_text)} 字符），为提速已省略，以上“紧凑结构提示”已保留关键线索。",
            ]
        )
    return "\n\n".join(parts)


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    cleaned = _clean_json_candidate(text)
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    brace_start = cleaned.find("{")
    brace_end = cleaned.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        candidate = cleaned[brace_start : brace_end + 1]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, list):
                return {"annotations": obj}
            return obj
        except json.JSONDecodeError:
            pass

    bracket_start = cleaned.find("[")
    bracket_end = cleaned.rfind("]")
    if bracket_start != -1 and bracket_end != -1 and bracket_end > bracket_start:
        candidate = cleaned[bracket_start : bracket_end + 1]
        try:
            array = json.loads(candidate)
            if isinstance(array, list):
                return {"annotations": array}
        except json.JSONDecodeError:
            return None
    return None


def save_json(data: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def annotator_node(state: AnnotationState) -> Dict[str, Any]:
    response = stream_gitcode_chat(
        state.messages,
        model=GITCODE_MODEL,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=0.3,
    )
    return {
        "attempt": state.attempt + 1,
        "messages": state.messages + [{"role": "assistant", "content": response}],
        "raw_responses": state.raw_responses + [response],
    }


def checker_node(state: AnnotationState) -> Dict[str, Any]:
    latest = state.raw_responses[-1] if state.raw_responses else ""
    decision = call_checker_llm(latest) if latest else {"status": "continue"}
    return {
        "checker_decision": str(decision.get("status", "continue")).lower(),
        "checker_reason": decision.get("reason") if isinstance(decision.get("reason"), str) else None,
    }


def parser_node(state: AnnotationState) -> Dict[str, Any]:
    latest = state.raw_responses[-1] if state.raw_responses else ""
    combined = "\n".join(filter(None, state.raw_responses))
    candidate_text = combined or latest
    parsed = extract_json(candidate_text)
    return {
        "parsed": parsed,
        "error": None if parsed is not None else "JSON 解析失败",
    }


def continuation_node(state: AnnotationState) -> Dict[str, Any]:
    # 获取最后一次尝试的最后几个字符，作为继续的起点
    last_response = state.raw_responses[-1] if state.raw_responses else ""
    combined = "\n".join(filter(None, state.raw_responses))

    # 如果最后输出看起来像被截断的JSON，提供更明确的continuation prompt
    if combined and ("{" in combined and not combined.rstrip().endswith("}")):
        # 找到迄今为止的 JSON 片段尾部
        last_part = combined.rstrip()
        if last_part.endswith("..."):
            last_part = last_part[:-3]

        continuation_prompt = (
            "你的上一条 JSON 回答被截断了。请基于目前为止的完整内容继续输出剩余 JSON：\n\n"
            f"```json\n{last_part}\n```\n\n"
            f"请直接从 `{last_part[-80:] if len(last_part) > 80 else last_part}` 开始继续写 JSON，"
            f"保持相同结构，完成剩余的annotations数组，最后用正确的括号关闭JSON。"
            f"不要重新开始，不要添加解释。"
        )
    else:
        continuation_prompt = CONTINUE_PROMPT

    return {
        "messages": state.messages + [{"role": "user", "content": continuation_prompt}],
        "checker_decision": None,
        "checker_reason": None,
    }


def condition_after_checker(state: AnnotationState) -> str:
    # 如果已达到最大尝试次数，直接去解析，不再继续
    if state.attempt >= MAX_ATTEMPTS:
        return "parse"
    decision = (state.checker_decision or "continue").lower()
    if decision == "complete":
        return "parse"
    return "continue"


def condition_after_parser(state: AnnotationState) -> str:
    if state.parsed:
        return "complete"
    if state.attempt >= MAX_ATTEMPTS:
        return "repair"
    return "continue"


def build_annotation_graph() -> StateGraph:
    graph = StateGraph(AnnotationState)
    graph.add_node("annotate", annotator_node)
    graph.add_node("check", checker_node)
    graph.add_node("parse", parser_node)
    graph.add_node("continuation", continuation_node)
    graph.set_entry_point("annotate")
    graph.add_edge("annotate", "check")
    graph.add_conditional_edges(
        "check",
        condition_after_checker,
        {
            "parse": "parse",
            "continue": "continuation",
        },
    )
    graph.add_conditional_edges(
        "parse",
        condition_after_parser,
        {
            "complete": END,
            "continue": "continuation",
            "repair": END,
        },
    )
    graph.add_edge("continuation", "annotate")
    return graph.compile()


def run_annotation_with_graph(prompt: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    initial_state: Dict[str, Any] = {
        "messages": [SYSTEM_MESSAGE, {"role": "user", "content": prompt}],
        "attempt": 0,
        "raw_responses": [],
        "parsed": None,
        "error": None,
        "checker_decision": None,
        "checker_reason": None,
    }
    graph = build_annotation_graph()
    # 增加递归限制到100次，避免过早中止
    config = {"recursion_limit": 100}
    final_state = graph.invoke(initial_state, config=config)
    # final_state 可能是 AnnotationState 或 dict，统一处理
    if isinstance(final_state, dict):
        return final_state.get("parsed"), final_state
    else:
        # 如果是 AnnotationState 对象，转换为字典
        return final_state.parsed, {
            "messages": final_state.messages,
            "attempt": final_state.attempt,
            "raw_responses": final_state.raw_responses,
            "parsed": final_state.parsed,
            "error": final_state.error,
            "checker_decision": final_state.checker_decision,
            "checker_reason": final_state.checker_reason,
        }


def _parse_row_col_from_marker(marker: str) -> Optional[Tuple[int, int]]:
    try:
        row_match = re.search(r"row=(\d+)", marker)
        col_match = re.search(r"grid_col=(\d+)", marker)
        if not row_match or not col_match:
            return None
        return int(row_match.group(1)), int(col_match.group(1))
    except Exception:
        return None


def _derive_placeholder_from_position(row: int, grid_col: int) -> str:
    base_by_col = {
        1: "teaching_content",
        2: "teaching_content",
        3: "teaching_content",
        4: "teacher_activity",
        5: "student_activity",
        6: "student_activity",
        7: "student_activity",
        8: "design_intention",
    }
    base = base_by_col.get(grid_col, "cell_value")
    return f"{base}_r{row:03d}_c{grid_col:02d}"


def annotate_markdown(
    md_path: Path = DEFAULT_MD_PATH,
    *,
    features_path: Optional[Path] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    no_segment: bool = False,
    kb_insights: str = "",
) -> Dict[str, Any]:
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown 文件不存在：{md_path}")

    if features_path is None:
        guess_path = md_path.with_name(md_path.stem + DEFAULT_FEATURES_SUFFIX)
        features_path = guess_path if guess_path.exists() else None

    markdown_text = load_text(md_path)
    features_text = load_text(features_path) if features_path and features_path.exists() else None

    segments = [markdown_text] if no_segment else segment_markdown(markdown_text)
    total_segments = len(segments)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / f"raw_{timestamp}"
    raw_dir.mkdir(parents=True, exist_ok=True)

    combined_annotations: List[Dict[str, Any]] = []
    raw_responses_paths: List[str] = []
    failures: List[str] = []

    try:
        for idx, segment in enumerate(segments, start=1):
            segment_label = f"{idx}/{total_segments}"
            prompt_input = build_prompt_input(
                segment,
                features_text=features_text,
                segment_label=segment_label,
            )
            prompt = create_annotation_prompt(prompt_input, kb_insights=kb_insights)

            parsed, state = run_annotation_with_graph(prompt)

            # 保存每次尝试的原始响应
            raw_responses = state.get("raw_responses", []) if isinstance(state, dict) else state.raw_responses
            for attempt_index, raw_text in enumerate(raw_responses, start=1):
                raw_path = raw_dir / f"segment_{idx:02d}_attempt_{attempt_index}.txt"
                raw_path.write_text(raw_text, encoding="utf-8")
                raw_responses_paths.append(str(raw_path))

            combined_text = _clean_json_candidate("\n\n".join(raw_responses))
            had_continuation = len(raw_responses) > 1

            if parsed is None:
                # 使用 JSON 修复模型做最后尝试
                repair_response = call_json_repair_llm(combined_text)
                repair_path = raw_dir / f"segment_{idx:02d}_repair.txt"
                repair_path.write_text(repair_response, encoding="utf-8")
                raw_responses_paths.append(str(repair_path))
                parsed = extract_json(repair_response)
            elif had_continuation:
                # 如果发生续写，仍交给修复器做最终整理
                # 但只有在修复后的标注数量≥原始标注数量时才采纳修复结果
                repair_response = call_json_repair_llm(combined_text)
                repair_path = raw_dir / f"segment_{idx:02d}_repair.txt"
                repair_path.write_text(repair_response, encoding="utf-8")
                raw_responses_paths.append(str(repair_path))
                repaired = extract_json(repair_response)

                # 比较标注数量，防止修复器错误简化
                if repaired and parsed:
                    original_count = len(parsed.get("annotations", []))
                    repaired_count = len(repaired.get("annotations", []))
                    if repaired_count >= original_count:
                        print(f"✅ 修复器保持了标注完整性 (原:{original_count}, 修复后:{repaired_count})")
                        parsed = repaired
                    else:
                        print(f"⚠️  修复器删减了标注，保留原始版本 (原:{original_count}, 修复后:{repaired_count})")
                elif repaired:
                    parsed = repaired

            if parsed is None:
                failures.append(f"Segment {idx} 无法解析为合法 JSON")
                continue

            annotations = parsed.get("annotations", [])
            if not isinstance(annotations, list):
                failures.append(f"Segment {idx} 的 JSON 缺少 annotations 列表")
                continue

            combined_annotations.extend(annotations)

            # 在处理多个段落时，在段落之间添加延迟以避免触发 API 限流
            if total_segments > 1 and idx < total_segments:
                delay = 3.0  # 3秒延迟
                print(f"⏸️  等待 {delay} 秒后处理下一段落（避免 API 限流）...")
                time.sleep(delay)

    except TemplateTooComplexError as e:
        # 模板过于复杂，超出模型max_tokens限制
        print(f"\n{str(e)}")
        # 返回失败信息，让上层调用者知道失败原因
        raise

    # 强制补标：对"示例痕迹"单元格（如 1./2./•/……/XX）进行自动 replace，占位符按行列生成唯一名
    must_replace = _detect_example_cells(markdown_text)
    existing_cells = {
        a.get("cell_marker")
        for a in combined_annotations
        if isinstance(a, dict) and a.get("location_type") == "table_cell"
    }
    auto_added = 0
    for marker, reason in must_replace:
        if marker in existing_cells:
            continue
        pos = _parse_row_col_from_marker(marker)
        if not pos:
            placeholder = "cell_value_auto"
        else:
            placeholder = _derive_placeholder_from_position(*pos)
        combined_annotations.append(
            {
                "location_type": "table_cell",
                "cell_marker": marker,
                "action": "replace",
                "placeholder": placeholder,
                "result": f"{{{{{placeholder}}}}}",
                "reason": f"强制替换候选：{reason}",
            }
        )
        auto_added += 1

    result: Dict[str, Any] = {"annotations": combined_annotations}

    final_json_path = output_dir / f"annotation_{timestamp}.json"
    save_json(result, final_json_path)

    summary_payload = {
        "markdown": str(md_path),
        "features": str(features_path) if features_path else None,
        "outputs": {
            "raw_dir": str(raw_dir),
            "annotation_json": str(final_json_path),
            "raw_responses": raw_responses_paths,
        },
        "failures": failures,
        "generated_at": timestamp,
    }
    summary_path = output_dir / f"annotation_summary_{timestamp}.json"
    save_json(summary_payload, summary_path)

    return summary_payload


def main() -> None:
    summary = annotate_markdown()
    print("LLM 标注流程完成（已保存结果，未验证内容）：")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
