"""
Generate feature-oriented Markdown descriptions from DOCX templates for docuagent v4.

This module builds on the reversible Markdown manifest produced by
`docx_markdown_converter`, adds heuristic annotations (label detection, empty
cells, time fields, etc.), and emits an MD file that is easier for LLMs to read.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from .docx_markdown_converter import DocxMarkdownExporter, export_docx_to_markdown


LABEL_PATTERN = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9（）()、·…《》“”\"'\\s]+[：:]$")
TIME_KEYWORDS = ["年", "月", "日", "周", "星期", "节", "分钟", "小时"]
EXAMPLE_KEYWORDS = ["如：", "示例", "例如", "样例", "举例", "参考"]
EXAMPLE_BULLET_RE = re.compile(r"(^|<br>)\s*(?:\d{1,2}|[一二三四五六七八九十]+)[\.|、]")
ELLIPSIS_RE = re.compile(r"(…{2,}|\.{3,})")
BULLET_CHAR_RE = re.compile(r"•")
GENERIC_X_RE = re.compile(r"\bXX\b")


def generate_feature_markdown(
    docx_path: Union[str, Path],
    output_dir: Union[str, Path],
    *,
    reuse_existing: bool = True,
) -> Tuple[Path, Path, Path]:
    """
    Convert DOCX template into feature-oriented Markdown plus manifest & raw MD.

    Args:
        docx_path: Source DOCX file.
        output_dir: Directory for outputs (raw markdown, manifest, feature markdown).
        reuse_existing: If True, reuse existing raw markdown/manifest when present.

    Returns:
        Tuple of (raw_markdown_path, manifest_path, feature_markdown_path)
    """
    docx_path = Path(docx_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_md_path = output_dir / f"{docx_path.stem}_v4.md"
    manifest_path = output_dir / f"{docx_path.stem}_v4_manifest.json"

    if not reuse_existing or not (raw_md_path.exists() and manifest_path.exists()):
        raw_md_path, manifest_path = export_docx_to_markdown(docx_path, output_dir)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    feature_lines: List[str] = []
    feature_lines.append("# 教案模板特征摘要 (v4)")
    feature_lines.append("")
    feature_lines.append(f"- 来源文件：{docx_path.name}")
    feature_lines.append(f"- 生成时间：{datetime.now().isoformat()}")
    feature_lines.append(f"- 原始标记 Markdown：`{raw_md_path.name}`")
    feature_lines.append(f"- Manifest：`{manifest_path.name}`")
    feature_lines.append("")

    # Paragraphs
    feature_lines.append("## 段落特征")
    paragraphs: List[Dict] = manifest.get("paragraphs", [])
    if not paragraphs:
        feature_lines.append("- （无段落内容）")
    else:
        for para in paragraphs:
            text = para.get("text", "")
            display_text = text if text else "(空)"
            para_features = _describe_paragraph(text)
            feature_lines.append(
                f"- **{para['block_id']}** （索引 {para.get('index', '-')}, 样式 {para.get('style', '未知')}）"
            )
            feature_lines.append(f"  - 原文：{display_text}")
            font_meta = para.get("font") or {}
            if font_meta:
                feature_lines.append(f"  - 字体：{_format_font(font_meta)}")
            drawing_count = para.get("drawing_count", 0)
            if drawing_count:
                feature_lines.append(f"  - 媒体：包含 {drawing_count} 个图片/形状资源，保持位置不变")
            if para_features:
                feature_lines.append("  - 特征：")
                for feat in para_features:
                    feature_lines.append(f"    - {feat}")

    # Tables
    feature_lines.append("")
    feature_lines.append("## 表格特征")
    tables: List[Dict] = manifest.get("tables", [])
    if not tables:
        feature_lines.append("- （无表格内容）")
    else:
        for table_idx, table in enumerate(tables, start=1):
            block_id = table.get("block_id", f"T{table_idx:04d}")
            rows: List[List[Dict]] = table.get("rows", [])
            feature_lines.append(f"### 表 {table_idx} （{block_id}）")
            feature_lines.append(f"- 行数：{len(rows)}，最大列数：{table.get('max_columns', len(rows[0]) if rows else 0)}")
            feature_lines.append("")

            column_contexts = _build_column_contexts(rows)

            for row_idx, row in enumerate(rows):
                feature_lines.append(f"- **行 {row_idx}**")
                if not row:
                    feature_lines.append("  - （该行包含纵向合并延续的单元格）")
                    continue

                row_texts = [cell.get("text", "") for cell in row if cell.get("text")]
                if row_texts:
                    feature_lines.append("  - 行内其他文本：" + "；".join(row_texts[:6]))

                for cell in row:
                    marker = cell.get("marker", "")
                    logical_idx = cell.get("logical_col_index")
                    grid_idx = cell.get("grid_col_index")
                    text = cell.get("text", "")
                    col_span = cell.get("col_span", 1)
                    vmerge = cell.get("vmerge", "none")

                    display_text = text if text else "(空)"
                    feature_lines.append(
                        f"  - 列 {logical_idx} (grid {grid_idx}) → `{marker}`"
                    )
                    feature_lines.append(
                        f"    - 内容：{display_text}；列跨度：{col_span}；纵向合并：{vmerge}"
                    )
                    font_meta = cell.get("font") or {}
                    if font_meta:
                        feature_lines.append(f"    - 字体：{_format_font(font_meta)}")
                    drawing_count = cell.get("drawing_count", 0)
                    if drawing_count:
                        feature_lines.append(f"    - 媒体：包含 {drawing_count} 个图片/形状资源，保持位置不变")

                    cell_features = _describe_cell(text)
                    if cell_features:
                        feature_lines.append("    - 特征：")
                        for feat in cell_features:
                            feature_lines.append(f"      - {feat}")

                    col_context = column_contexts.get(grid_idx, [])
                    col_related = [t for t in col_context if t != text and t]
                    if col_related:
                        feature_lines.append(
                            "    - 同列常见文本：" + "；".join(col_related[:4])
                        )

    feature_lines.append("")
    feature_lines.append("---")
    feature_lines.append("（以上内容由 v4 特征生成器自动输出）")

    feature_md_path = output_dir / f"{docx_path.stem}_v4_features.md"
    feature_md_path.write_text("\n".join(feature_lines), encoding="utf-8")
    return raw_md_path, manifest_path, feature_md_path


# --------------------------------------------------------------------------- #
# Heuristic helpers


def _describe_paragraph(text: str) -> List[str]:
    paragraphs_features: List[str] = []
    stripped = text.strip()
    if not stripped:
        paragraphs_features.append("空段落，可插入占位符或保留为空行")
    if LABEL_PATTERN.match(stripped + "："):
        paragraphs_features.append("可能是标签字段（末尾带冒号）")
    if any(keyword in stripped for keyword in TIME_KEYWORDS):
        paragraphs_features.append("包含时间相关字段")
    if "____" in stripped or stripped.count("_") >= 3:
        paragraphs_features.append("包含连续下划线，可能用于手写填写")
    return paragraphs_features


def _describe_cell(text: str) -> List[str]:
    cell_features: List[str] = []
    stripped = text.strip()

    if not stripped:
        cell_features.append("单元格为空，可能需要插入占位符")
    else:
        if any(keyword in stripped for keyword in TIME_KEYWORDS):
            cell_features.append("包含时间字段，建议细分占位符")
        if any(keyword in stripped for keyword in EXAMPLE_KEYWORDS) or _has_example_markers(stripped):
            cell_features.append("包含示例/提示语，需替换为占位内容")
        if _looks_like_label(stripped):
            cell_features.append("疑似字段标签")
        if "<br>" in stripped:
            line_count = stripped.count("<br>") + 1
            if line_count >= 3:
                cell_features.append(f"多行文本，共 {line_count} 行")

    return cell_features


def _has_example_markers(text: str) -> bool:
    s = text.replace(" ", "")
    if "<br>" in s:
        lines = s.split("<br>")
    else:
        lines = [s]
    if ELLIPSIS_RE.search(s):
        return True
    if BULLET_CHAR_RE.search(s):
        return True
    if GENERIC_X_RE.search(s):
        return True
    for ln in lines:
        if EXAMPLE_BULLET_RE.match(ln):
            return True
        if ln.startswith("-") or ln.startswith("•"):
            return True
    return False


def _looks_like_label(text: str) -> bool:
    formatted = text.replace("<br>", "")
    return bool(
        LABEL_PATTERN.match(formatted + "：")
        or formatted.endswith("：")
        or len(formatted) <= 12 and all(ch not in formatted for ch in ["，", "。"])
    )


def _build_column_contexts(rows: List[List[Dict]]) -> Dict[int, List[str]]:
    contexts: Dict[int, List[str]] = {}
    for row in rows:
        for cell in row:
            grid_start = cell.get("grid_col_index")
            text = cell.get("text", "")
            try:
                span = int(cell.get("col_span", 1) or 1)
            except (TypeError, ValueError):
                span = 1
            if grid_start is None:
                continue
            # 将文本传播到被该单元格覆盖的所有 grid 列中
            if isinstance(grid_start, int):
                grid_indices = range(grid_start, grid_start + span)
            else:
                # 尝试将字符串数字转换为 int
                try:
                    start_int = int(grid_start)
                    grid_indices = range(start_int, start_int + span)
                except (TypeError, ValueError):
                    grid_indices = [grid_start]
            for g in grid_indices:
                contexts.setdefault(g, [])
                if text:
                    contexts[g].append(text)
    return contexts


def _format_font(meta: Dict[str, Any]) -> str:
    if not meta:
        return "沿用段落样式"

    primary_parts: List[str] = []
    name = meta.get("name")
    if isinstance(name, str) and name:
        primary_parts.append(name)

    size = meta.get("size_pt")
    if isinstance(size, (int, float)):
        primary_parts.append(f"{size:g}pt")

    style_flags: List[str] = []
    if meta.get("bold"):
        style_flags.append("加粗")
    if meta.get("italic"):
        style_flags.append("斜体")
    underline = meta.get("underline")
    if underline:
        style_flags.append("下划线")

    color = meta.get("color")
    color_part = None
    if isinstance(color, str) and color:
        color_part = f"颜色 {color.upper()}"

    segments: List[str] = []
    if primary_parts:
        segments.append(" ".join(primary_parts))
    if style_flags:
        segments.append("样式：" + "、".join(style_flags))
    if color_part:
        segments.append(color_part)

    return "；".join(segments) if segments else "沿用段落样式"


__all__ = ["generate_feature_markdown"]

