"""
Core模块 - 核心功能
"""

from .document_generator import (
    DocumentGenerator,
    DocumentGenerationResult,
    generate_document,
)

__all__ = [
    'DocumentGenerator',
    'DocumentGenerationResult',
    'generate_document',
]
