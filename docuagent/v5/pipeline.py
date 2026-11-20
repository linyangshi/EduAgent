"""
DocuAgent v5 pipeline: DOCX -> Markdown -> LLM annotation -> Annotated DOCX -> Generation -> Final DOCX
- Preserves all intermediate artifacts
- Records per-stage timing
- Exposes CLI: python -m docuagent.v5.pipeline --docx <path> --requirement "..." --outdir <dir>
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# v4 utilities
from docuagent.v4.docx_markdown_converter import DocxMarkdownExporter
from docuagent.v4.run_llm_annotation import annotate_markdown
from docuagent.v4.apply_annotations import apply_annotations_and_rebuild_docx
from docuagent.v4.content_generation.workflow import run_content_generation

# v5 utilities
from .vlm_checker import check_docx_quality
from .reflection import analyze_errors
from .knowledge_base import KnowledgeBase
from .doc_classifier import classify_from_markdown_file


@dataclass
class StageRecord:
    name: str
    start: float
    end: float
    extra: Dict[str, Any]

    @property
    def elapsed(self) -> float:
        return round(self.end - self.start, 3)


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def review_and_reflect(
    docx_path: str | Path,
    *,
    user_requirement: str = "",
    doc_type: Optional[str] = None,
    doc_classification: Optional[Dict[str, Any]] = None,
    outdir: str | Path = "results/v5_vlm_review"
) -> Dict[str, Any]:
    """
    VLM审查和反思分析

    Args:
        docx_path: DOCX文档路径
        user_requirement: 用户需求
        doc_type: 文��类型（可选，用于指定知识库）
        doc_classification: 文档分类详情（可选，用于记录）
        outdir: 输出目录

    Returns:
        审查摘要
    """
    docx_path = str(docx_path)
    outdir = Path(outdir) / f"vlm_review_{_ts()}"
    outdir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    vlm = check_docx_quality(Path(docx_path), user_requirement, outdir, doc_type)
    t1 = time.time()

    t2 = time.time()
    analysis = analyze_errors(vlm, user_requirement, outdir=outdir)
    t3 = time.time()

    # 根据文档类型加载知识库
    if doc_type:
        kb = KnowledgeBase.for_doc_type(doc_type)
        print(f"📚 使用分类知识库: {doc_type}")
    else:
        kb = KnowledgeBase(Path("results/v5_kb/experiences.jsonl"))
        print(f"📚 使用通用知识库")

    kb.add_experience(vlm, analysis, {
        "template_name": Path(docx_path).name,
        "user_requirement": user_requirement,
        "doc_type": doc_type,
        "doc_classification": doc_classification or {},
    })

    # 🆕 自动清理知识库（删除无用建议）
    print("\n" + "="*60)
    print("🧹 自动清理知识库（基于规则）...")
    print("="*60)
    from .knowledge_cleaner import cleanup_knowledge_base
    cleanup_result = cleanup_knowledge_base(kb.kb_path, doc_type=doc_type or "unknown", mode="rule")
    if cleanup_result.get("status") == "success":
        print(f"✅ 清理完成 (方法: {cleanup_result.get('method', 'rule_based')}):")
        print(f"   保留建议: {cleanup_result['prompts_kept']} 条")
        print(f"   删除建议: {cleanup_result['prompts_removed']} 条")
        if "reason_distribution" in cleanup_result:
            print(f"   删除原因: {cleanup_result['reason_distribution']}")
    elif cleanup_result.get("status") == "no_change":
        print(f"✅ 知识库已是最优状态，无需清理")
    else:
        print(f"⚠️  清理跳过: {cleanup_result.get('message', '未知原因')}")

    summary = {
        "docx_path": docx_path,
        "user_requirement": user_requirement,
        "vlm": {
            "model": "qvq-max",
            "work_dir": str(outdir),
            "issues": vlm.get("issues", []),
        },
        "root_cause": {
            "type": next((i.get("root_cause", "unknown") for i in analysis.get("analysis", []) if i), analysis.get("overall_recommendation", {}).get("priority", "unknown")),
        },
        "recommendations": analysis.get("overall_recommendation", {}),
        "timing": {
            "vlm_seconds": round(t1 - t0, 3),
            "reflection_seconds": round(t3 - t2, 3),
        },
        "kb_file": str(kb.kb_path),
    }

    summary_path = outdir.parent / f"v5_review_summary_{_ts()}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Review summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def run_pipeline(docx_path: str | Path, *, requirement: str, outdir: str | Path) -> Dict[str, Any]:
    docx_path = Path(docx_path)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    overall: Dict[str, Any] = {
        "start": datetime.now().isoformat(),
        "docx_path": str(docx_path),
        "requirement": requirement,
        "outputs": {},
        "stages": [],
    }

    stages: list[StageRecord] = []

    # 1) Export DOCX to Markdown + manifest
    s = time.time()
    md_dir = outdir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    exporter = DocxMarkdownExporter(docx_path)
    md_path, manifest_path = exporter.export(md_dir)
    e = time.time()
    stages.append(StageRecord("docx_export", s, e, {"markdown": str(md_path), "manifest": str(manifest_path)}))

    # 1.5) 文档分类：判断文档类型
    print("\n" + "="*60)
    print("🔍 阶段 1.5: 文档类型分类")
    print("="*60)
    s = time.time()
    doc_classification = classify_from_markdown_file(md_path)
    doc_type = doc_classification.get("type", "other")
    doc_type_name = doc_classification.get("type_name", "其他")
    e = time.time()
    stages.append(StageRecord("doc_classification", s, e, doc_classification))

    print(f"\n📋 文档类型: {doc_type_name} ({doc_type})")
    print(f"   置信度: {doc_classification.get('confidence', 0):.2%}")
    print(f"   理由: {doc_classification.get('reason', '未知')}")

    # 2) LLM annotation (v4 pipeline, inject KB insights from doc-type-specific KB)
    print("\n" + "="*60)
    print(f"📚 阶段 2: 加载 {doc_type_name} 知识库")
    print("="*60)

    # 根据文档类型加载对应的知识库
    kb = KnowledgeBase.for_doc_type(doc_type)
    kb_insights = kb.format_for_annotator_prompt(max_entries=30, min_severity="low")
    s = time.time()
    ann_outdir = outdir / "annotation"
    ann_outdir.mkdir(parents=True, exist_ok=True)
    ann_summary = annotate_markdown(md_path=md_path, features_path=None, output_dir=ann_outdir, no_segment=False, kb_insights=kb_insights)
    ann_json = Path(ann_summary["outputs"]["annotation_json"]) if isinstance(ann_summary, dict) else ann_outdir / "annotation.json"
    e = time.time()
    stages.append(StageRecord("annotation", s, e, {"summary": ann_summary}))

    # 3) Apply annotations -> annotated markdown + annotated docx
    s = time.time()
    apply_res = apply_annotations_and_rebuild_docx(
        md_path=str(md_path),
        annotations_json_path=str(ann_json),
        manifest_path=str(manifest_path),
        output_md_path=str(ann_outdir / "annotated.md"),
        output_docx_path=str(ann_outdir / "annotated_template.docx"),
        base_docx_path=str(docx_path),
    )
    e = time.time()
    stages.append(StageRecord("apply_annotations", s, e, apply_res))

    # 4) Content generation (v4 workflow)
    s = time.time()
    gen_outdir = outdir / "generation"
    gen_outdir.mkdir(parents=True, exist_ok=True)
    user_input = {"prompt": requirement}

    # 加载知识库洞察用于内容生成
    gen_kb_insights = kb.format_for_generator_prompt(max_entries=30, min_severity="low")

    gen_summary = run_content_generation(
        annotation_path=str(ann_json),
        user_input=user_input,
        markdown_path=str(md_path),
        manifest_path=str(manifest_path),
        output_dir=str(gen_outdir),
        batch_mode=True,
        batch_size=5,
        kb_insights=gen_kb_insights,  # ✅ 注入知识库洞察到生成阶段
        doc_type=doc_type,  # ✅ 传递文档类型（用于字段强约束验证）
    )
    e = time.time()
    stages.append(StageRecord("generation", s, e, gen_summary))

    # Try to locate final.docx under generation output
    final_docx = None
    for cand in [gen_outdir / "final.docx", gen_outdir / "generated.docx", gen_outdir / "output.docx"]:
        if cand.exists():
            final_docx = cand
            break
    # fallback to annotated docx if generation didn't create one
    if not final_docx:
        final_docx = Path(apply_res.get("docx")) if isinstance(apply_res, dict) else None

    # 5) Optional: VLM review on final docx (存储到分类知识库)
    print("\n" + "="*60)
    print(f"🔍 阶段 5: VLM审查 & 存储到 {doc_type_name} 知识库")
    print("="*60)
    s = time.time()
    vlm_summary = {}
    try:
        vlm_summary = review_and_reflect(
            str(final_docx),
            user_requirement=requirement,
            doc_type=doc_type,
            doc_classification=doc_classification,
            outdir=outdir / "vlm"
        ) if final_docx else {}
    except Exception as ex:
        vlm_summary = {"error": str(ex)}
    e = time.time()
    stages.append(StageRecord("vlm_review", s, e, vlm_summary))

    overall["doc_classification"] = doc_classification  # 添加文档分类信息
    overall["outputs"] = {
        "markdown": str(md_path),
        "manifest": str(manifest_path),
        "annotation_json": str(ann_json),
        "annotated_markdown": apply_res.get("markdown") if isinstance(apply_res, dict) else None,
        "annotated_docx": apply_res.get("docx") if isinstance(apply_res, dict) else None,
        "final_docx": str(final_docx) if final_docx else None,
        "generation_dir": str(gen_outdir),
        "knowledge_base": str(kb.kb_path),  # 添加使用的知识库路径
    }
    overall["stages"] = [
        {"name": r.name, "seconds": r.elapsed, "extra": r.extra} for r in stages
    ]
    overall["end"] = datetime.now().isoformat()
    overall["total_seconds"] = round(sum(r.elapsed for r in stages), 3)

    report_path = outdir / f"v5_run_report_{_ts()}.json"
    report_path.write_text(json.dumps(overall, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== v5 pipeline run summary ===")
    print(json.dumps(overall, ensure_ascii=False, indent=2))
    return overall


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="DocuAgent v5 pipeline")
    p.add_argument("--docx", required=True, help="Input unannotated DOCX path")
    p.add_argument("--requirement", required=True, help="User requirement/prompt")
    p.add_argument("--outdir", required=True, help="Output directory")
    args = p.parse_args()

    run_pipeline(args.docx, requirement=args.requirement, outdir=args.outdir)


if __name__ == "__main__":
    main()
