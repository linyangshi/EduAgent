"""
V6 并行处理模块

提供并行标注和并行内容生成功能，通过多线程并发处理提升处理速度。

主要特性:
- 多线程并发处理文档段落和字段生成
- 自动并发控制，避免API限流
- 完全兼容V4的标注和生成逻辑
- 支持降级到顺序处理模式

使用示例:
    from docuagent.v6 import parallel_annotate, parallel_generate_all_batches
    from pathlib import Path

    # 并行标注
    result = parallel_annotate(
        md_path=Path("template.md"),
        max_concurrent=10,
    )

    # 并行生成
    gen_result = parallel_generate_all_batches(
        field_batches=batches,
        user_input=user_input,
        max_concurrent=10,
    )
"""

from .parallel_annotator import (
    parallel_annotate,
    ParallelAnnotationResult,
    remove_segment_prefixes,
)
from .parallel_generator import (
    parallel_generate_batch,
    parallel_generate_all_batches,
    ParallelGenerationResult,
)

__all__ = [
    # 并行标注
    "parallel_annotate",
    "ParallelAnnotationResult",
    "remove_segment_prefixes",
    # 并行生成
    "parallel_generate_batch",
    "parallel_generate_all_batches",
    "ParallelGenerationResult",
]

__version__ = "0.1.0"
