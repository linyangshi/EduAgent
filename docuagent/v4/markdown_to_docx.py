"""
Markdown → DOCX rebuilder for docuagent v4 pipeline.

Consumes the annotated Markdown (with DOCX-BLOCK / DOCX-CELL markers) together
with the manifest JSON produced by `docx_markdown_converter` and writes an
updated DOCX file by applying the Markdown edits back to the original template.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Union

from docx import Document
from docx.document import Document as _Document
from docx.shared import Pt, RGBColor
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING

BLOCK_PATTERN = re.compile(r"\[\[DOCX-BLOCK\s+([^\]]+)\]\]")
CELL_PATTERN = re.compile(r"\[\[DOCX-CELL\s+([^\]]+)\]\]")
DRAWING_TOKEN_PATTERN = re.compile(r"\s*\[\[DRAWING[^\]]*\]\]\s*")


def rebuild_docx_from_markdown(
    markdown_path: Union[str, Path],
    manifest_path: Union[str, Path],
    output_docx_path: Union[str, Path],
    *,
    base_docx_path: Union[str, Path, None] = None,
) -> Path:
    """
    Rebuild a DOCX document from Markdown + manifest.

    Args:
        markdown_path: Path to the annotated Markdown file.
        manifest_path: Path to the manifest JSON generated during export.
        output_docx_path: Where to write the rebuilt DOCX file.
        base_docx_path: Optional DOCX to serve as the base. Defaults to the
            manifest's `source_path`.

    Returns:
        Path to the rebuilt DOCX.
    """
    markdown_path = Path(markdown_path)
    manifest_path = Path(manifest_path)
    output_docx_path = Path(output_docx_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    base_source = Path(base_docx_path) if base_docx_path else Path(manifest["source_path"])
    if not base_source.exists():
        raise FileNotFoundError(f"Base DOCX not found: {base_source}")

    doc = Document(str(base_source))

    md_info = _parse_markdown(markdown_path.read_text(encoding="utf-8"))
    paragraph_map = {item["block_id"]: item for item in manifest["paragraphs"]}
    table_map = {item["block_id"]: item for item in manifest["tables"]}

    block_sequence = manifest.get("block_sequence")
    if not block_sequence:
        raise ValueError("Manifest missing 'block_sequence'; please regenerate v4 export.")

    block_iter = iter(block_sequence)
    for block in _iter_block_items(doc):
        try:
            block_meta = next(block_iter)
        except StopIteration:
            break

        block_id = block_meta["block_id"]
        block_type = block_meta["type"]

        if isinstance(block, Paragraph) and block_type == "paragraph":
            para_meta = paragraph_map.get(block_id, {})
            content = md_info["paragraphs"].get(block_id)
            if content is None:
                continue
            _apply_paragraph_text(
                block,
                content,
                original_text=para_meta.get("text", ""),
                drawing_count=para_meta.get("drawing_count", 0),
                font_meta=para_meta.get("font") or {},
                indent=para_meta.get("indent", False),
            )
        elif isinstance(block, Table) and block_type == "table":
            table_manifest = table_map.get(block_id)
            table_updates = md_info["tables"].get(block_id, {})
            if not table_manifest:
                continue
            _apply_table_updates(block, table_manifest, table_updates)
        else:
            # Type mismatch – skip but warn?
            continue

    output_docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_docx_path))
    return output_docx_path


# --------------------------------------------------------------------------- #
# internal helpers


def _iter_block_items(parent: Union[_Document, Table]) -> Iterable[Union[Paragraph, Table]]:
    parent_elm = parent.element.body if isinstance(parent, _Document) else parent._tbl
    for child in parent_elm.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, parent)
        elif child.tag.endswith("}tbl"):
            yield Table(child, parent)


def _parse_markdown(markdown_text: str) -> Dict[str, Dict]:
    lines = markdown_text.splitlines()
    idx = 0
    paragraph_updates: Dict[str, str] = {}
    table_updates: Dict[str, Dict[str, str]] = {}

    while idx < len(lines):
        line = lines[idx]
        block_match = BLOCK_PATTERN.match(line.strip())
        if not block_match:
            idx += 1
            continue

        attrs = _parse_attrs(block_match.group(1))
        block_type = attrs.get("type")
        block_id = attrs.get("id")
        idx += 1

        if block_type == "paragraph":
            content_lines: List[str] = []
            while idx < len(lines):
                peek = lines[idx]
                if BLOCK_PATTERN.match(peek.strip()):
                    break
                if peek.strip() == "" and (idx + 1 < len(lines) and BLOCK_PATTERN.match(lines[idx + 1].strip())):
                    idx += 1
                    break
                content_lines.append(peek)
                idx += 1

            paragraph_updates[block_id] = "\n".join(content_lines).strip()

        elif block_type == "table":
            # Skip leading blank lines
            while idx < len(lines) and lines[idx].strip() == "":
                idx += 1

            cell_map: Dict[str, str] = {}
            while idx < len(lines):
                table_line = lines[idx].strip()
                if BLOCK_PATTERN.match(table_line):
                    break

                if not table_line:
                    idx += 1
                    continue

                if not table_line.startswith("|"):
                    break

                # Some DOCX-exported table rows contain literal newlines inside a
                # merged cell, so a single logical Markdown table row may span
                # multiple physical lines. Keep collecting until we reach the
                # closing pipe of that logical row.
                logical_row = lines[idx].rstrip("\n")
                idx += 1
                while not logical_row.strip().endswith("|") and idx < len(lines):
                    continuation = lines[idx]
                    continuation_stripped = continuation.strip()
                    if BLOCK_PATTERN.match(continuation_stripped):
                        break
                    logical_row += "\n" + continuation.rstrip("\n")
                    idx += 1

                parts = [part.strip() for part in logical_row.strip().split("|")[1:-1]]
                for part in parts:
                    cell_match = CELL_PATTERN.match(part)
                    if not cell_match:
                        continue
                    marker = CELL_PATTERN.match(part).group(0)
                    text_content = part[cell_match.end():].strip()
                    text_content = DRAWING_TOKEN_PATTERN.sub("", text_content)
                    text_content = text_content.replace("<br>", "\n")
                    cell_map[marker] = text_content
            table_updates[block_id] = cell_map
        else:
            # Unsupported block type
            continue

    return {"paragraphs": paragraph_updates, "tables": table_updates}


def _parse_attrs(attr_string: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for token in shlex.split(attr_string):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        result[key] = value
    return result


def _apply_paragraph_text(
    paragraph: Paragraph,
    text: str,
    *,
    original_text: str = "",
    drawing_count: int = 0,
    font_meta: Dict[str, Union[str, float, bool]] | None = None,
    indent: bool = False,
) -> None:
    font_meta = font_meta or {}
    if drawing_count or _safe_equal(text, original_text):
        # 保留原始段落（包含图片/形状或内容相同）
        return
    _clear_paragraph(paragraph)
    if text:
        # 🔥 检测文本开头是否有全角空格缩进（'　　' 或 '  '）
        # 如果有，则设置首行缩进并移除这些空格
        has_fullwidth_indent = text.startswith('　　') or text.startswith('  ')
        if has_fullwidth_indent:
            indent = True
            # 移除开头的缩进空格
            text = text.lstrip('　 ')
        
        # 🔥 去掉首尾空格
        text = text.strip()

        run = paragraph.add_run(text)

        # 🔥 设置生成内容的格式，优先使用用户设置的字号
        # 只对生成的新内容应用，原始内容保持不变
        if not _safe_equal(text, original_text):
            # 设置段落格式：左对齐、单倍行距
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            
            # 设置首行缩进
            if indent:
                # 默认字体12pt，2字符 = 24pt
                # 如果有自定义字体大小，使用自定义大小
                size = 12
                if font_meta and font_meta.get("size_pt"):
                    try:
                        size = float(font_meta["size_pt"])
                    except (ValueError, TypeError):
                        pass
                paragraph.paragraph_format.first_line_indent = Pt(size * 2)
            else:
                paragraph.paragraph_format.first_line_indent = Pt(0)

            # 合并默认格式和用户设置，用户设置优先
            default_font = {
                "name": "宋体",
                "size_pt": 12,  # 小四 = 12磅（默认值）
                "bold": False,
                "italic": False,
            }
            # 用户设置的值覆盖默认值
            font_meta = {**default_font, **font_meta}

        _apply_run_style(run, font_meta)


def _apply_table_updates(table: Table, table_manifest: Dict, table_updates: Dict[str, str]) -> None:
    rows_meta = table_manifest.get("rows", [])

    for row_idx, row in enumerate(table.rows):
        row_meta = rows_meta[row_idx] if row_idx < len(rows_meta) else []
        cells = list(row.cells)

        # 🔥 Fix: Filter duplicates in cells to match manifest structure (deduplicated)
        unique_cells = []
        seen_cells = set()
        for cell in cells:
            if cell not in seen_cells:
                unique_cells.append(cell)
                seen_cells.add(cell)

        for logical_idx, cell in enumerate(unique_cells):
            if logical_idx >= len(row_meta):
                continue

            cell_meta = row_meta[logical_idx]
            marker = cell_meta.get("marker")
            original_text = cell_meta.get("text", "")
            new_text = table_updates.get(marker, original_text)
            _set_cell_text(
                cell,
                new_text,
                original_text=original_text,
                drawing_count=cell_meta.get("drawing_count", 0),
                font_meta=cell_meta.get("font") or {},
            )


def _clear_paragraph(paragraph: Paragraph) -> None:
    for run in list(paragraph.runs):
        paragraph._p.remove(run._r)


def _set_cell_text(
    cell,
    text: str,
    *,
    original_text: str = "",
    drawing_count: int = 0,
    font_meta: Dict[str, Union[str, float, bool]] | None = None,
) -> None:
    font_meta = font_meta or {}
    if drawing_count or _safe_equal(text, _cell_original_to_markdown(original_text)):
        return
    paragraphs = list(cell.paragraphs)
    if not paragraphs:
        paragraphs = [cell.add_paragraph("")]

    # 🔥 处理每一行，检测并处理首行缩进
    lines = text.split("\n") if text else [""]
    processed_lines = []
    line_indents = []
    
    for line in lines:
        # 检测是否有全角空格缩进
        has_indent = line.startswith('　　') or line.startswith('  ')
        if has_indent:
            # 移除开头的缩进空格
            line = line.lstrip('　 ')
        line = line.strip()
        processed_lines.append(line)
        line_indents.append(has_indent)
    
    lines = processed_lines

    # 🔥 设置生成内容的格式，优先使用用户设置的字号
    if not _safe_equal(text, _cell_original_to_markdown(original_text)):
        # 合并默认格式和用户设置，用户设置优先
        default_font = {
            "name": "宋体",
            "size_pt": 12,  # 小四 = 12磅（默认值）
            "bold": False,
            "italic": False,
        }
        # 用户设置的值覆盖默认值
        font_meta = {**default_font, **font_meta}

    # 获取字体大小用于计算缩进
    font_size = 12
    if font_meta and font_meta.get("size_pt"):
        try:
            font_size = float(font_meta["size_pt"])
        except (ValueError, TypeError):
            pass

    _clear_paragraph(paragraphs[0])
    if lines:
        if lines[0]:
            run = paragraphs[0].add_run(lines[0])
            # 设置段落格式：左对齐、单倍行距
            paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
            paragraphs[0].paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            # 🔥 根据检测到的缩进设置首行缩进
            if line_indents[0]:
                paragraphs[0].paragraph_format.first_line_indent = Pt(font_size * 2)
            else:
                paragraphs[0].paragraph_format.first_line_indent = Pt(0)
            _apply_run_style(run, font_meta)
        else:
            paragraphs[0].text = ""

    # remove extra paragraphs
    for para in paragraphs[1:]:
        cell._tc.remove(para._p)

    for idx, line in enumerate(lines[1:], start=1):
        new_para = cell.add_paragraph("")
        if line:
            run = new_para.add_run(line)
            # 设置段落格式：左对齐、单倍行距
            new_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            new_para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            # 🔥 根据检测到的缩进设置首行缩进
            if idx < len(line_indents) and line_indents[idx]:
                new_para.paragraph_format.first_line_indent = Pt(font_size * 2)
            else:
                new_para.paragraph_format.first_line_indent = Pt(0)
            _apply_run_style(run, font_meta)


def _apply_run_style(run, font_meta: Dict[str, Union[str, float, bool]]) -> None:
    if not font_meta:
        return

    font = run.font

    name = font_meta.get("name")
    if isinstance(name, str):
        font.name = name
        # 专门处理中文字体
        if name in ["宋体", "SimSun", "黑体", "SimHei", "楷体", "KaiTi", "仿宋", "FangSong"]:
            font.element.rPr.rFonts.set(qn('w:eastAsia'), name)

    size = font_meta.get("size_pt")
    if isinstance(size, str):
        try:
            size = float(size)
        except ValueError:
            size = None
    if isinstance(size, (int, float)):
        font.size = Pt(size)

    if "bold" in font_meta:
        font.bold = font_meta["bold"]

    if "italic" in font_meta:
        font.italic = font_meta["italic"]

    if "underline" in font_meta:
        font.underline = font_meta["underline"]

    color = font_meta.get("color")
    if isinstance(color, str):
        hex_color = color.lstrip("#")
        if len(hex_color) == 6:
            font.color.rgb = RGBColor.from_string(hex_color.upper())


def _safe_equal(a: str, b: str) -> bool:
    return (a or "").strip() == (b or "").strip()


def _cell_original_to_markdown(text: str) -> str:
    return text.replace("<br>", "\n") if text else ""
