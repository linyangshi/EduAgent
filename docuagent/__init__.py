"""
DocuAgent - 零样本、高鲁棒性的 Word 模板智能填充系统
Zero-shot, Robust Word Template Filling System

核心理念：
- 完全依赖 LLM API，无需训练模型
- 格式安全优先，绝不生成损坏的 .docx 文件
- v4: Markdown-based reversible preprocessing pipeline

作者: DocuAgent Team
版本: 4.0.0
"""

__version__ = "4.0.0"
__author__ = "DocuAgent Team"

# v4 是当前主要版本
from .v4 import (
    DocxMarkdownExporter,
    export_docx_to_markdown,
    rebuild_docx_from_markdown,
    generate_feature_markdown,
    apply_annotations_to_markdown,
    apply_annotations_and_rebuild_docx,
    generate_text_by_tag,
    generate_text_by_tags,
)

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



