from __future__ import annotations

from typing import Dict, List

from .content_generation.field_analyzer import FieldAnalyzer
from .content_generation.content_generator import ContentGenerator
from .content_generation.state import FieldAnalysis
from .content_generation.workflow import group_fields_for_batch


def _analyze_placeholders(placeholders: List[str], user_input: Dict) -> List[FieldAnalysis]:
    analyzer = FieldAnalyzer()
    analyses: List[FieldAnalysis] = []
    for p in placeholders:
        ann = {"placeholder": p, "location_type": "paragraph", "action": "replace", "reason": ""}
        analysis = analyzer.analyze_field(ann, None, user_input=user_input)
        analyses.append(analysis)
    return analyses


def generate_text_by_tags(placeholders: List[str], user_input: Dict, batch_size: int = 5) -> Dict[str, str]:
    if not placeholders:
        return {}
    analyses = _analyze_placeholders(placeholders, user_input)
    # 先按优先级排序，保障基础信息/目标类先生成
    analyses.sort(key=lambda a: (a.priority, a.placeholder))
    generator = ContentGenerator()
    generated: Dict[str, str] = {}

    if len(analyses) == 1:
        field = generator.generate_content(analyses[0], user_input, generated)
        generated[analyses[0].placeholder] = field.content
        return generated

    # 分组以减少相互依赖的字段落在同一批次
    batches = group_fields_for_batch(analyses, batch_size=batch_size)
    for batch in batches:
        batch_results = generator.batch_generate(batch, user_input, generated)
        for k, v in batch_results.items():
            generated[k] = v.content

    # 仅返回请求的占位符键
    return {p: generated.get(p, "") for p in placeholders}


def generate_text_by_tag(placeholder: str, user_input: Dict) -> str:
    res = generate_text_by_tags([placeholder], user_input)
    return res.get(placeholder, "")
