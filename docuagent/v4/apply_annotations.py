from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple, Union

from .markdown_to_docx import rebuild_docx_from_markdown


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    if not text.endswith("\n"):
        text = text + "\n"
    path.write_text(text, encoding="utf-8")


def _load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_block_marker(line: str) -> bool:
    s = line.strip()
    return s.startswith("[[DOCX-BLOCK ") and s.endswith("]]")


def _match_paragraph_marker(line: str, block_id: str) -> bool:
    s = line.strip()
    return s.startswith("[[DOCX-BLOCK ") and f"id={block_id}" in s and "type=paragraph" in s


def _find_paragraph_content_range(lines: List[str], block_id: str) -> Optional[Tuple[int, int]]:
    i = 0
    while i < len(lines):
        if _match_paragraph_marker(lines[i], block_id):
            start = i + 1
            j = start
            while j < len(lines):
                if _is_block_marker(lines[j].strip()):
                    break
                if lines[j].strip() == "" and j + 1 < len(lines) and _is_block_marker(lines[j + 1].strip()):
                    j += 1
                    break
                j += 1
            return start, j
        i += 1
    return None


def _replace_paragraph(lines: List[str], block_id: str, new_text: str) -> bool:
    rng = _find_paragraph_content_range(lines, block_id)
    if not rng:
        return False
    start, end = rng
    new_lines = new_text.splitlines()
    lines[start:end] = new_lines
    return True


def _append_paragraph(lines: List[str], block_id: str, extra_text: str) -> bool:
    rng = _find_paragraph_content_range(lines, block_id)
    if not rng:
        return False
    start, end = rng
    existing = lines[start:end]
    if not existing:
        lines[start:end] = extra_text.splitlines()
        return True
    # 识别“标签：”单行，并将追加文本合并到同一行，避免“标签：\n标签：值”
    existing_text = "\n".join(existing).strip()
    label_only_re = re.compile(r"^\s*([\u4e00-\u9fa5A-Za-z（）()\-\s]{1,12})[:：]\s*$")
    m = label_only_re.match(existing_text)
    if m:
        label = m.group(1).strip()
        # 如果追加内容也带相同标签，去重后合并；否则将值接在标签后
        extra = extra_text.strip()
        # 去掉追加文本开头的重复标签
        prefix_re = re.compile(r"^\s*" + re.escape(label) + r"\s*[:：]\s*(.*)$")
        m2 = prefix_re.match(extra)
        value = m2.group(1) if m2 else extra
        merged = f"{label}：{value}".strip()
        lines[start:end] = merged.splitlines()
        return True
    # 默认：按行追加
    content = "\n".join(existing).rstrip("\n")
    if content:
        content = content + "\n" + extra_text
    else:
        content = extra_text
    lines[start:end] = content.splitlines()
    return True


def _is_ellipsis_line(s: str) -> bool:
    x = re.sub(r"\s+", "", s or "")
    return bool(x) and re.fullmatch(r"[\.·•…]+", x) is not None


def _cleanup_cell_text(text: str) -> str:
    # unify breaks to <br>
    t = (text or "").replace("\r", "").strip()
    parts = [s.strip() for s in re.split(r"(?:<br>|\n)+", t) if s is not None]
    out: List[str] = []
    for p in parts:
        if not p or _is_ellipsis_line(p):
            continue
        # strip residual bracketed quotes e.g. ['文本'] or ['文本
        p = re.sub(r"^\['([^\]]*?)'\]$", r"\1", p)
        p = p.replace("['", "").replace("']", "")
        if out and out[-1] == p:
            continue
        out.append(p)
    return "<br>".join(out).strip()


def _update_cell_in_line(line: str, cell_marker: str, new_text: str) -> Optional[str]:
    if cell_marker not in line:
        return None
    parts = line.split("|")
    changed = False
    for idx in range(1, len(parts) - 1):
        seg = parts[idx]
        if seg.strip().startswith(cell_marker):
            safe_text = new_text.replace("\r", "").replace("\n", "<br>")
            safe_text = _cleanup_cell_text(safe_text)
            parts[idx] = f" {cell_marker} {safe_text} "
            changed = True
            break
    if not changed:
        return None
    return "|".join(parts)


def _collect_logical_table_row(lines: List[str], start_idx: int) -> Tuple[str, int]:
    logical_row = lines[start_idx]
    end_idx = start_idx + 1
    while not logical_row.strip().endswith("|") and end_idx < len(lines):
        if _is_block_marker(lines[end_idx].strip()):
            break
        logical_row += "\n" + lines[end_idx]
        end_idx += 1
    return logical_row, end_idx


def _apply_cell_update(lines: List[str], cell_marker: str, new_text: str) -> bool:
    for i in range(len(lines)):
        if not lines[i].strip().startswith("|"):
            continue

        logical_row, end_idx = _collect_logical_table_row(lines, i)
        if cell_marker not in logical_row:
            continue

        updated = _update_cell_in_line(logical_row, cell_marker, new_text)
        if updated is not None:
            lines[i:end_idx] = updated.splitlines()
            return True
    return False


def apply_annotations_to_markdown(
    md_path: Union[str, Path],
    annotations_json_path: Union[str, Path],
    output_md_path: Optional[Union[str, Path]] = None,
) -> Tuple[Path, Dict[str, List[str]]]:
    md_path = Path(md_path)
    annotations_json_path = Path(annotations_json_path)
    lines = _read_text(md_path).splitlines()
    data = _load_json(annotations_json_path)
    annotations: List[Dict] = data.get("annotations", []) if isinstance(data, dict) else []

    updated_paragraphs: List[str] = []
    updated_cells: List[str] = []
    not_found: List[str] = []

    for item in annotations:
        loc = item.get("location_type")
        action = (item.get("action") or "").lower()
        result_text = item.get("result") or ""
        if loc == "paragraph":
            block_id = item.get("block_id")
            if not block_id:
                continue
            ok = False
            if action == "append":
                ok = _append_paragraph(lines, block_id, result_text)
            else:
                ok = _replace_paragraph(lines, block_id, result_text)
            if ok:
                updated_paragraphs.append(block_id)
            else:
                not_found.append(f"paragraph:{block_id}")
        elif loc == "table_cell":
            marker = item.get("cell_marker")
            if not marker:
                continue
            # 🔧 修复：区分 append 和 replace 操作
            # append: 保留标题，追加占位符 (如: "一、目的与意义<br>{{purpose}}")
            # replace: 完全替换单元格内容 (如: "{{thesis_title}}")
            ok = _apply_cell_update(lines, marker, result_text)
            if ok:
                updated_cells.append(marker)
            else:
                not_found.append(f"cell:{marker}")
        else:
            continue

    # 全文表格单元格清理：即便未被更新也统一去掉“……/•/…”行与相邻重复
    def _cleanup_line_cells(line: str) -> str:
        if "[[DOCX-CELL " not in line:
            return line
        parts = line.split("|")
        for idx in range(1, len(parts) - 1):
            seg = parts[idx]
            s = seg.strip()
            if not s.startswith("[[DOCX-CELL "):
                continue
            # 拆出 marker 与内容
            try:
                end = s.index("]]")
            except ValueError:
                continue
            marker = s[: end + 2]
            content = s[end + 2 :].strip()
            cleaned = _cleanup_cell_text(content)
            parts[idx] = f" {marker} {cleaned} "
        return "|".join(parts)

    lines = [_cleanup_line_cells(ln) for ln in lines]

    out_md = Path(output_md_path) if output_md_path else md_path.with_name(f"{md_path.stem}_annotated.md")
    _write_text(out_md, "\n".join(lines))

    report = {
        "updated_paragraphs": updated_paragraphs,
        "updated_cells": updated_cells,
        "not_found": not_found,
    }
    return out_md, report


def apply_annotations_and_rebuild_docx(
    md_path: Union[str, Path],
    annotations_json_path: Union[str, Path],
    *,
    manifest_path: Optional[Union[str, Path]] = None,
    output_docx_path: Optional[Union[str, Path]] = None,
    base_docx_path: Optional[Union[str, Path]] = None,
    output_md_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Union[str, Dict[str, List[str]]]]:
    md_path = Path(md_path)
    annotations_json_path = Path(annotations_json_path)

    if manifest_path is None:
        guess_manifest = md_path.with_name(f"{md_path.stem}_manifest.json")
        alt_manifest = md_path.with_name(f"{md_path.stem}_v4_manifest.json")
        manifest_path = alt_manifest if alt_manifest.exists() else guess_manifest
    manifest_path = Path(manifest_path)

    updated_md_path, report = apply_annotations_to_markdown(
        md_path=md_path,
        annotations_json_path=annotations_json_path,
        output_md_path=output_md_path,
    )

    out_docx = (
        Path(output_docx_path)
        if output_docx_path
        else updated_md_path.with_name(f"{updated_md_path.stem}.docx")
    )

    rebuilt = rebuild_docx_from_markdown(
        markdown_path=updated_md_path,
        manifest_path=manifest_path,
        output_docx_path=out_docx,
        base_docx_path=base_docx_path,
    )

    return {
        "markdown": str(updated_md_path),
        "docx": str(rebuilt),
        "report": report,
    }
