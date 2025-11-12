"""
内容生成模块 - 基于 LLM 自动生成教案内容

主要功能：
1. 字段分析：识别占位符需要的内容类型和长度
2. 内容生成：根据用户输入和上下文生成具体内容
3. 质量检查：验证生成内容的质量
4. 内容注入：将生成内容填充到模板中
"""

from .state import ContentGenerationState, FieldAnalysis, GeneratedField
from .workflow import run_content_generation

__all__ = [
    "ContentGenerationState",
    "FieldAnalysis",
    "GeneratedField",
    "run_content_generation",
]
