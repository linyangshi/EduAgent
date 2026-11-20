"""
docuagent v4 module.

Contains the Markdown-based reversible preprocessing pipeline.
"""

from .docx_markdown_converter import DocxMarkdownExporter, export_docx_to_markdown
from .feature_markdown import generate_feature_markdown
from .markdown_to_docx import rebuild_docx_from_markdown
from .apply_annotations import (
    apply_annotations_to_markdown,
    apply_annotations_and_rebuild_docx,
)
from .tag_text_generator import generate_text_by_tag, generate_text_by_tags

__all__ = [
    "DocxMarkdownExporter",
    "export_docx_to_markdown",
    "rebuild_docx_from_markdown",
    "generate_feature_markdown",
    "apply_annotations_to_markdown",
    "apply_annotations_and_rebuild_docx",
    "generate_text_by_tag",
    "generate_text_by_tags",
]

