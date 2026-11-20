"""
DOCX → Markdown converter for docuagent v4 pipeline.

This module exports a DOCX template to a Markdown representation that keeps
round-trip metadata so that LLM annotations can be mapped back to the original
XML nodes. Each paragraph/table/cell is tagged with a stable identifier, and a
manifest JSON with structural metadata is generated for later reconstruction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from docx import Document
from docx.document import Document as _Document
from docx.oxml.ns import qn
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph


BLOCK_MARKER_TEMPLATE = "[[DOCX-BLOCK type={block_type} id={block_id} extra=\"{extra}\"]]"
CELL_MARKER_TEMPLATE = (
    "[[DOCX-CELL table={table_id} row={row_idx} grid_col={grid_col_idx} "
    "cell_id={cell_id} span={col_span} vmerge={vmerge}]]"
)


@dataclass
class ParagraphMeta:
    block_id: str
    index: int
    para_id: Optional[str]
    style: Optional[str]
    text: str
    drawing_count: int = 0
    font: Dict[str, Any] = field(default_factory=dict)
    indent: bool = False


@dataclass
class CellMeta:
    block_id: str
    table_index: int
    row_index: int
    logical_col_index: int
    grid_col_index: int
    cell_marker: str
    text: str
    col_span: int
    vmerge: str
    style: Optional[str]
    drawing_count: int = 0
    font: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TableMeta:
    block_id: str
    table_index: int
    rows: List[List[CellMeta]] = field(default_factory=list)
    max_columns: int = 0


class DocxMarkdownExporter:
    """Export DOCX templates into annotated Markdown plus a manifest."""

    def __init__(self, docx_path: Union[str, Path]):
        self.docx_path = Path(docx_path)
        self.document = Document(str(self.docx_path))
        self.paragraph_counter = 0
        self.table_counter = 0

    def export(self, output_dir: Union[str, Path]) -> Tuple[Path, Path]:
        """
        Export DOCX to Markdown and manifest JSON.

        Returns:
            A tuple of (markdown_path, manifest_path).
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        paragraphs: List[ParagraphMeta] = []
        tables: List[TableMeta] = []
        block_sequence: List[Dict[str, Union[str, int]]] = []

        for block in self._iter_block_items(self.document):
            if isinstance(block, Paragraph):
                meta = self._capture_paragraph(block)
                paragraphs.append(meta)
                block_sequence.append({"type": "paragraph", "block_id": meta.block_id})
            elif isinstance(block, Table):
                meta = self._capture_table(block)
                tables.append(meta)
                block_sequence.append({"type": "table", "block_id": meta.block_id})
            else:
                # Ignore unsupported block types (e.g., sections)
                continue

        md_lines: List[str] = []
        manifest = {
            "document": self.docx_path.name,
            "source_path": str(self.docx_path),
            "generated_at": datetime.now().isoformat(),
            "paragraphs": [self._paragraph_to_manifest(p) for p in paragraphs],
            "tables": [self._table_to_manifest(t) for t in tables],
            "block_sequence": block_sequence,
        }

        paragraph_map = {meta.block_id: meta for meta in paragraphs}
        table_map = {meta.block_id: meta for meta in tables}

        for block in block_sequence:
            if block["type"] == "paragraph":
                meta = paragraph_map[block["block_id"]]
                marker = BLOCK_MARKER_TEMPLATE.format(
                    block_type="paragraph",
                    block_id=meta.block_id,
                    extra=f"index={meta.index}",
                )
                md_lines.append(marker)
                md_lines.append(meta.text if meta.text else "")
                if meta.drawing_count:
                    md_lines.append(f"[[DOCX-DRAWING block={meta.block_id} count={meta.drawing_count}]]")
                md_lines.append("")
            elif block["type"] == "table":
                table_meta = table_map[block["block_id"]]
                marker = BLOCK_MARKER_TEMPLATE.format(
                    block_type="table",
                    block_id=table_meta.block_id,
                    extra=f"index={table_meta.table_index}",
                )
                md_lines.append(marker)
                md_lines.append("")
                for row_cells in table_meta.rows:
                    md_row = ["|"]
                    for cell_meta in row_cells:
                        cell_text = cell_meta.text
                        if cell_meta.drawing_count:
                            cell_text = f"{cell_text} [[DRAWING x{cell_meta.drawing_count}]]" if cell_text else f"[[DRAWING x{cell_meta.drawing_count}]]"
                        md_row.append(f" {cell_meta.cell_marker} {cell_text} |")
                    md_lines.append("".join(md_row))
                md_lines.append("")

        markdown_path = output_dir / f"{self.docx_path.stem}_v4.md"
        manifest_path = output_dir / f"{self.docx_path.stem}_v4_manifest.json"

        markdown_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return markdown_path, manifest_path

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _iter_block_items(parent: Union[_Document, _Cell]) -> Iterable[Union[Paragraph, Table]]:
        """Yield paragraphs and tables in document order."""
        parent_elm = parent.element.body if isinstance(parent, _Document) else parent._tc
        for child in parent_elm.iterchildren():
            if child.tag.endswith("}p"):
                yield Paragraph(child, parent)
            elif child.tag.endswith("}tbl"):
                yield Table(child, parent)

    def _capture_paragraph(self, paragraph: Paragraph) -> ParagraphMeta:
        block_id = f"P{self.paragraph_counter:04d}"
        self.paragraph_counter += 1

        para_element = paragraph._p
        para_id = para_element.get(qn("w14:paraId")) or para_element.get(qn("w:rsidR"))
        style_name = paragraph.style.name if paragraph.style else None

        text = paragraph.text.replace("\r", " ").strip()
        drawing_count = self._count_drawings(paragraph)
        font_meta = self._extract_font_from_paragraph(paragraph)
        
        # Check for first line indent
        indent = False
        
        # 方法1：通过 python-docx API 检测
        try:
            pf = paragraph.paragraph_format
            if pf and pf.first_line_indent is not None:
                # first_line_indent 是 Length 对象 (EMU单位)
                # 1 pt = 12700 EMU, 所以 10pt = 127000 EMU
                indent_val = pf.first_line_indent
                # 直接将 Length 对象转换为 int (EMU值)
                emu_val = int(indent_val) if indent_val else 0
                if emu_val >= 127000:  # 约 10pt
                    indent = True
        except Exception:
            pass
        
        # 方法2：检测段落格式属性中的首行缩进 (XML层面)
        if not indent:
            p_pr = paragraph._p.pPr
            if p_pr is not None:
                ind = getattr(p_pr, "ind", None)
                if ind is not None:
                    # Some python-docx builds omit helper properties like firstLineChars.
                    # Fall back to raw XML attributes when those helpers do not exist.
                    first_line_chars = getattr(ind, "firstLineChars", None)
                    if first_line_chars is None and hasattr(ind, "_element"):
                        first_line_chars = ind._element.get(qn("w:firstLineChars"))

                    if first_line_chars is not None:
                        try:
                            if int(first_line_chars) >= 150:  # Approx 1.5+ chars
                                indent = True
                        except (ValueError, TypeError):
                            pass
                    
                    if not indent:
                        first_line = getattr(ind, "firstLine", None)
                        if first_line is None and hasattr(ind, "_element"):
                            first_line = ind._element.get(qn("w:firstLine"))
                        if first_line is not None:
                            try:
                                # 1 twip = 1/20 pt, 24pt = 480 twips
                                # 降低阈值以捕获更多缩进情况
                                if int(first_line) >= 200:  # Approx 10pt+
                                    indent = True
                            except (ValueError, TypeError):
                                pass
        
        # 方法3：检测文本内容是否以全角空格开头
        if not indent and text:
            if text.startswith('　　') or text.startswith('  '):
                indent = True

        return ParagraphMeta(
            block_id=block_id,
            index=paragraph._p.getparent().index(paragraph._p) if paragraph._p.getparent() is not None else -1,
            para_id=para_id,
            style=style_name,
            text=text,
            drawing_count=drawing_count,
            font=font_meta,
            indent=indent,
        )

    def _capture_table(self, table: Table) -> TableMeta:
        table_id = f"T{self.table_counter:04d}"
        self.table_counter += 1

        meta = TableMeta(block_id=table_id, table_index=self.table_counter - 1)

        for row_idx, row in enumerate(table.rows):
            logical_cells: List[CellMeta] = []
            logical_col_idx = 0
            seen_cells = set()

            for grid_col_idx, cell in enumerate(row.cells):
                # 🔥 Fix: Skip duplicate cells (merged cells appear multiple times in row.cells)
                if cell in seen_cells:
                    continue
                seen_cells.add(cell)

                # 🔥 提取单元格文本，并保留每个段落的首行缩进
                cell_text = self._extract_cell_text_with_indent(cell)
                col_span = self._extract_col_span(cell)
                vmerge_state = self._extract_vmerge(cell)
                cell_marker = CELL_MARKER_TEMPLATE.format(
                    table_id=table_id,
                    row_idx=row_idx,
                    grid_col_idx=grid_col_idx,
                    cell_id=f"{table_id}-R{row_idx:03d}-C{grid_col_idx:03d}",
                    col_span=col_span,
                    vmerge=vmerge_state,
                )

                cell_meta = CellMeta(
                    block_id=table_id,
                    table_index=meta.table_index,
                    row_index=row_idx,
                    logical_col_index=logical_col_idx,
                    grid_col_index=grid_col_idx,
                    cell_marker=cell_marker,
                    text=cell_text,
                    col_span=col_span,
                    vmerge=vmerge_state,
                    style=cell.paragraphs[0].style.name if cell.paragraphs and cell.paragraphs[0].style else None,
                    drawing_count=self._count_drawings_in_cell(cell),
                    font=self._extract_font_from_cell(cell),
                )

                logical_cells.append(cell_meta)
                logical_col_idx += 1

            meta.rows.append(logical_cells)
            meta.max_columns = max(meta.max_columns, len(logical_cells))

        return meta

    def _paragraph_to_manifest(self, meta: ParagraphMeta) -> Dict:
        return {
            "block_id": meta.block_id,
            "index": meta.index,
            "para_id": meta.para_id,
            "style": meta.style,
            "text": meta.text,
            "drawing_count": meta.drawing_count,
            "font": meta.font,
            "indent": meta.indent,
        }

    def _table_to_manifest(self, meta: TableMeta) -> Dict:
        manifest_rows = []
        for row_cells in meta.rows:
            manifest_row = []
            for cell in row_cells:
                manifest_row.append(
                    {
                        "grid_col_index": cell.grid_col_index,
                        "logical_col_index": cell.logical_col_index,
                        "text": cell.text,
                        "col_span": cell.col_span,
                        "vmerge": cell.vmerge,
                        "style": cell.style,
                        "marker": cell.cell_marker,
                        "drawing_count": cell.drawing_count,
                        "font": cell.font,
                    }
                )
            manifest_rows.append(manifest_row)

        return {
            "block_id": meta.block_id,
            "table_index": meta.table_index,
            "max_columns": meta.max_columns,
            "rows": manifest_rows,
        }

    @staticmethod
    def _normalise_cell_text(text: str) -> str:
        return text.replace("\r", " ").replace("\n", "<br>").strip()

    def _extract_cell_text_with_indent(self, cell: _Cell) -> str:
        """
        提取单元格文本，保留每个段落的首行缩进。
        如果段落有首行缩进，在该段落文本前添加全角空格。
        """
        paragraphs_text = []
        indent_marker = '　　'  # 两个全角空格
        
        for paragraph in cell.paragraphs:
            text = paragraph.text.replace("\r", " ").strip()
            
            # 检测该段落是否有首行缩进
            has_indent = self._check_paragraph_indent(paragraph)
            
            # 如果文本已经以全角空格开头，不重复添加
            if has_indent and text and not text.startswith('　') and not text.startswith('  '):
                text = indent_marker + text
            
            paragraphs_text.append(text)
        
        # 用 <br> 连接各段落
        return "<br>".join(paragraphs_text).strip()

    def _check_paragraph_indent(self, paragraph: Paragraph) -> bool:
        """检测段落是否有首行缩进"""
        # 方法1：通过 python-docx API 检测
        try:
            pf = paragraph.paragraph_format
            if pf and pf.first_line_indent is not None:
                emu_val = int(pf.first_line_indent) if pf.first_line_indent else 0
                if emu_val >= 127000:  # 约 10pt
                    return True
        except Exception:
            pass
        
        # 方法2：检测段落格式属性中的首行缩进 (XML层面)
        try:
            p_pr = paragraph._p.pPr
            if p_pr is not None:
                ind = getattr(p_pr, "ind", None)
                if ind is not None:
                    first_line_chars = getattr(ind, "firstLineChars", None)
                    if first_line_chars is None and hasattr(ind, "_element"):
                        first_line_chars = ind._element.get(qn("w:firstLineChars"))

                    if first_line_chars is not None:
                        try:
                            if int(first_line_chars) >= 150:
                                return True
                        except (ValueError, TypeError):
                            pass
                    
                    first_line = getattr(ind, "firstLine", None)
                    if first_line is None and hasattr(ind, "_element"):
                        first_line = ind._element.get(qn("w:firstLine"))
                    if first_line is not None:
                        try:
                            if int(first_line) >= 200:
                                return True
                        except (ValueError, TypeError):
                            pass
        except Exception:
            pass
        
        return False

    @staticmethod
    def _extract_col_span(cell: _Cell) -> int:
        tc_pr = cell._tc.tcPr
        if tc_pr is not None and tc_pr.gridSpan is not None and tc_pr.gridSpan.val:
            try:
                return int(tc_pr.gridSpan.val)
            except (TypeError, ValueError):
                return 1
        return 1

    @staticmethod
    def _extract_vmerge(cell: _Cell) -> str:
        tc_pr = cell._tc.tcPr
        if tc_pr is None or tc_pr.vMerge is None:
            return "none"
        val = tc_pr.vMerge.val
        if val is None:
            return "continue"
        return str(val)

    def _extract_font_from_paragraph(self, paragraph: Paragraph) -> Dict[str, Any]:
        for run in paragraph.runs:
            meta = self._extract_font_from_run(run)
            if meta:
                return meta
        return {}

    def _extract_font_from_cell(self, cell: _Cell) -> Dict[str, Any]:
        for paragraph in cell.paragraphs:
            meta = self._extract_font_from_paragraph(paragraph)
            if meta:
                return meta
        return {}

    def _extract_font_from_run(self, run) -> Dict[str, Any]:
        font = run.font
        r_pr = run._element.rPr if run._element is not None else None

        name = font.name
        if not name and r_pr is not None and r_pr.rFonts is not None:
            # 安全访问 eastAsia 属性，某些文档可能缺少该属性
            east_asia = getattr(r_pr.rFonts, 'eastAsia', None)
            name = r_pr.rFonts.ascii or east_asia or r_pr.rFonts.hAnsi

        size_pt = None
        if font.size is not None:
            size_pt = float(font.size.pt)
        elif r_pr is not None and r_pr.sz is not None and r_pr.sz.val is not None:
            size_pt = float(r_pr.sz.val) / 2.0

        bold = font.bold
        if bold is None and r_pr is not None and r_pr.b is not None:
            val = r_pr.b.val
            bold = True if val is None else bool(val)

        italic = font.italic
        if italic is None and r_pr is not None and r_pr.i is not None:
            val = r_pr.i.val
            italic = True if val is None else bool(val)

        underline = font.underline
        if underline is None and r_pr is not None and r_pr.u is not None:
            underline = r_pr.u.val if r_pr.u.val is not None else True

        color = None
        if font.color is not None and font.color.rgb is not None:
            color = str(font.color.rgb)
        elif r_pr is not None and r_pr.color is not None and r_pr.color.val is not None:
            color = r_pr.color.val

        meta: Dict[str, Any] = {}
        if name:
            meta["name"] = name
        if size_pt is not None:
            meta["size_pt"] = size_pt
        if bold is not None:
            meta["bold"] = bool(bold)
        if italic is not None:
            meta["italic"] = bool(italic)
        if underline is not None:
            meta["underline"] = underline
        if color:
            meta["color"] = f"#{color.lstrip('#').upper()}"

        return meta

    @staticmethod
    def _count_drawings(paragraph: Paragraph) -> int:
        count = 0
        for run in paragraph.runs:
            if run._r.xpath(".//w:drawing"):
                count += 1
        return count

    def _count_drawings_in_cell(self, cell: _Cell) -> int:
        count = 0
        for paragraph in cell.paragraphs:
            count += self._count_drawings(paragraph)
        return count


def export_docx_to_markdown(docx_path: Union[str, Path], output_dir: Union[str, Path]) -> Tuple[Path, Path]:
    """
    Convenience function for one-off conversions.
    """
    exporter = DocxMarkdownExporter(docx_path)
    return exporter.export(output_dir)


__all__ = ["DocxMarkdownExporter", "export_docx_to_markdown"]
