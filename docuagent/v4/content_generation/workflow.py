"""
内容生成 LangGraph 工作流
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
import re

from langgraph.graph import END, StateGraph

from .state import ContentGenerationState, FieldAnalysis
from .field_analyzer import FieldAnalyzer
from .content_generator import ContentGenerator
from ..apply_annotations import apply_annotations_and_rebuild_docx

TEACHER_KEYWORDS_EN = ("teacher", "teacher_name", "instructor", "lecturer", "mentor", "tutor")
TEACHER_KEYWORDS_CN = ("教师", "讲师", "导师", "任课", "授课")


def _is_teacher_placeholder(placeholder: str, annotation: Dict[str, Any]) -> bool:
    ph = (placeholder or "").lower()
    if any(key in ph for key in TEACHER_KEYWORDS_EN):
        return True
    reason = str((annotation.get("reason") if annotation else "") or "")
    result = str((annotation.get("result") if annotation else "") or "")
    combined_en = " ".join([reason.lower(), result.lower()])
    if any(key in combined_en for key in TEACHER_KEYWORDS_EN):
        return True
    combined_cn = reason + result
    return any(key in combined_cn for key in TEACHER_KEYWORDS_CN)


def load_inputs(state: ContentGenerationState) -> ContentGenerationState:
    """加载所有输入数据"""
    print("\n" + "=" * 80)
    print("📥 加载输入数据")
    print("=" * 80)
    
    print(f"   - 标注数量: {len(state.annotations)}")
    print(f"   - 用户输入字段: {len(state.user_input)}")
    print(f"   - Markdown 路径: {state.markdown_path}")
    
    state.total_fields = len(state.annotations)
    
    return state


def _extract_marker_value(marker: str, key: str) -> str:
    idx = marker.find(key)
    if idx == -1:
        return ""
    start = idx + len(key)
    end_space = marker.find(" ", start)
    end_bracket = marker.find("]", start)
    candidates = [x for x in [end_space, end_bracket] if x != -1]
    end = min(candidates) if candidates else len(marker)
    return marker[start:end]


def build_context_map_from_annotations(annotations: List[Dict]) -> Dict[str, str]:
    context_map: Dict[str, str] = {}
    for ann in annotations:
        if "placeholders" in ann and not ann.get("placeholder"):
            placeholders = ann.get("placeholders", [])
        else:
            placeholders = [ann.get("placeholder", "")]

        loc_type = ann.get("location_type", "")
        reason = ann.get("reason", "")
        template = ann.get("result", "").strip()

        if loc_type == "paragraph":
            block_id = ann.get("block_id", "")
            loc_desc = f"段落 {block_id}".strip()
        elif loc_type == "table_cell":
            marker = ann.get("cell_marker", "")
            table_id = _extract_marker_value(marker, "table=")
            row = _extract_marker_value(marker, "row=")
            col = _extract_marker_value(marker, "grid_col=")
            parts = []
            if table_id:
                parts.append(f"表格 {table_id}")
            if row:
                parts.append(f"行 {row}")
            if col:
                parts.append(f"列 {col}")
            loc_desc = " ".join(parts) if parts else "表格单元格"
        else:
            loc_desc = loc_type or ""

        snippet = template
        if len(snippet) > 120:
            snippet = snippet[:120] + "..."

        pieces = []
        if loc_desc:
            pieces.append(loc_desc)
        if reason:
            pieces.append(f"说明: {reason}")
        if snippet:
            pieces.append(f"模板示例: {snippet}")

        context = " | ".join(pieces)

        for p in placeholders:
            if p and p not in context_map:
                context_map[p] = context

    return context_map

def _build_marker_index(manifest: Dict) -> Dict[str, str]:
    """
    从manifest构建text→marker的映射

    Returns:
        {"教学环节": "[[DOCX-CELL table=T0000 row=0 grid_col=0 ...]]", ...}
    """
    index = {}

    # 索引表格单元格
    for table in manifest.get("tables", []):
        for row_cells in table.get("rows", []):
            for cell in row_cells:
                text = cell.get("text", "").strip()
                marker = cell.get("marker", "")
                if text and marker:
                    # 使用text作为key，可能有重复，但我们只需要找到一个marker
                    if text not in index:  # 优先保留第一次出现的
                        index[text] = marker

    # 索引段落
    for para in manifest.get("paragraphs", []):
        text = para.get("text", "").strip()
        block_id = para.get("block_id", "")
        if text and block_id:
            # 段落使用block标记
            marker = f"[[DOCX-BLOCK type=paragraph id={block_id}]]"
            if text not in index:
                index[text] = marker

    return index


def _enrich_annotations_with_markers(
    annotations: List[Dict],
    manifest: Dict
) -> List[Dict]:
    """
    将manifest中的marker信息添加到annotations

    策略：通过匹配original_text来关联marker
    """
    print(f"\n🔍 [DEBUG] _enrich_annotations_with_markers 被调用")
    print(f"   annotations数量: {len(annotations)}")
    print(f"   manifest是否为空: {not manifest}")
    
    if not manifest:
        print(f"   ❌ manifest为空，返回原annotations")
        return annotations

    marker_index = _build_marker_index(manifest)
    print(f"   marker_index大小: {len(marker_index)}")
    print(f"   marker_index示例keys: {list(marker_index.keys())[:3]}")

    enriched = []
    matched_count = 0

    for i, annot in enumerate(annotations):
        # 尝试通过original_text匹配marker
        original_text = annot.get("original_text", "").strip()
        placeholder = annot.get("placeholder", "N/A")

        if original_text and original_text in marker_index:
            annot["marker"] = marker_index[original_text]
            matched_count += 1
            if i < 3:  # 只打印前3个
                print(f"   ✅ [{i}] {placeholder}: 找到marker")
        else:
            if i < 3:
                print(f"   ❌ [{i}] {placeholder}: original_text='{original_text}' 未找到marker")

        enriched.append(annot)

    if matched_count > 0:
        print(f"   🔗 成功关联 {matched_count}/{len(annotations)} 个字段的marker信息")
    else:
        print(f"   ⚠️ 没有任何字段关联到marker！")

    return enriched


def analyze_fields(state: ContentGenerationState) -> ContentGenerationState:
    """分析所有字段并进行分组"""
    print("\n" + "=" * 80)
    print("🔍 分析字段")
    print("=" * 80)

    # 🔥 Step 1: Enrich annotations with markers from manifest
    enriched_annotations = _enrich_annotations_with_markers(
        state.annotations,
        state.manifest
    )

    # Step 2: Analyze with enriched annotations
    analyzer = FieldAnalyzer()
    context_map = build_context_map_from_annotations(enriched_annotations)
    analyzed_fields = analyzer.analyze_all_fields(enriched_annotations, context_map, user_input=state.user_input)
    
    state.analyzed_fields = analyzed_fields
    state.field_order = [field.placeholder for field in analyzed_fields]
    
    print(f"   ✅ 分析完成，共 {len(analyzed_fields)} 个字段")
    print(f"   - 基础信息: {sum(1 for f in analyzed_fields if f.field_type == 'basic_info')}")
    print(f"   - 目标类: {sum(1 for f in analyzed_fields if f.field_type == 'objective')}")
    print(f"   - 内容类: {sum(1 for f in analyzed_fields if f.field_type == 'content')}")
    print(f"   - 其他: {sum(1 for f in analyzed_fields if f.field_type not in ['basic_info', 'objective', 'content'])}")
    
    # 使用批量生成模式时进行分组
    if state.batch_mode:
        state.field_batches = group_fields_for_batch(analyzed_fields, state.batch_size)
        print(f"   📦 批量模式: 分为 {len(state.field_batches)} 组")
        for i, batch in enumerate(state.field_batches, 1):
            print(f"      组 {i}: {len(batch)} 个字段")
    
    return state


def group_fields_for_batch(fields: List[FieldAnalysis], batch_size: int = 5) -> List[List[FieldAnalysis]]:
    """
    将字段分组以支持批量生成
    
    按以下策略分组：
    1. 相同类型的字段优先分在一组
    2. 有依赖关系的字段分开
    3. 每组不超过 batch_size 个字段
    """
    batches = []
    remaining_fields = list(fields)
    
    while remaining_fields:
        current_batch = []
        current_batch_placeholders = set()
        
        i = 0
        while i < len(remaining_fields) and len(current_batch) < batch_size:
            field = remaining_fields[i]
            
            # 检查依赖关系：如果依赖的字段还没生成，跳过
            can_add = True
            for dep in field.dependencies:
                # 如果依赖字段在当前批次中，不能添加
                if dep in current_batch_placeholders:
                    can_add = False
                    break
            
            if can_add:
                current_batch.append(field)
                current_batch_placeholders.add(field.placeholder)
                remaining_fields.pop(i)
            else:
                i += 1
        
        if current_batch:
            batches.append(current_batch)
        else:
            # 如果无法添加任何字段（可能存在循环依赖），强制添加第一个
            if remaining_fields:
                batches.append([remaining_fields.pop(0)])
    
    return batches


def generate_batch_content(state: ContentGenerationState) -> ContentGenerationState:
    """
    批量生成当前批次的字段内容
    """
    if state.current_batch_index >= len(state.field_batches):
        state.is_complete = True
        return state
    
    current_batch = state.field_batches[state.current_batch_index]
    batch_num = state.current_batch_index + 1
    total_batches = len(state.field_batches)
    
    print(f"\n📦 [{batch_num}/{total_batches}] 批量生成 {len(current_batch)} 个字段")
    for field in current_batch:
        print(f"   - {field.placeholder} ({field.field_type})")
    
    print(f"🔍 [DEBUG] generate_batch_content - state.kb_insights长度: {len(state.kb_insights)} 字符")
    
    generator = ContentGenerator()
    
    # 获取已生成内容
    generated_content_dict = state.get_generated_content_dict()
    
    # 批量生成（注入知识库洞察和文档类型）
    generated_fields = generator.batch_generate(
        current_batch,
        state.user_input,
        generated_content_dict,
        kb_insights=state.kb_insights,  # ✅ 传递知识库洞察
        doc_type=state.doc_type,  # ✅ 传递文档类型（用于强约束验证）
    )
    
    # 保存生成结果
    for placeholder, generated_field in generated_fields.items():
        state.generated_content[placeholder] = generated_field
        state.completed_fields += 1
    
    total_chars = sum(len(f.content) for f in generated_fields.values())
    print(f"   ✅ 批次完成: 共生成 {total_chars} 字符")
    
    # 移动到下一个批次
    state.current_batch_index += 1
    
    # 检查是否完成
    if state.current_batch_index >= len(state.field_batches):
        state.is_complete = True
    
    # 显示进度
    progress = state.get_progress()
    print(f"   📊 进度: {progress:.1f}% ({state.completed_fields}/{state.total_fields})")
    
    return state


def generate_field_content(state: ContentGenerationState) -> ContentGenerationState:
    """生成当前字段的内容"""
    current_field = state.get_current_field()
    
    if not current_field:
        state.is_complete = True
        return state
    
    print(f"\n📝 [{state.current_index + 1}/{state.total_fields}] 生成字段: {current_field.placeholder}")
    print(f"   类型: {current_field.field_type} | 策略: {current_field.generation_strategy}")
    
    print(f"🔍 [DEBUG] generate_field_content - state.kb_insights长度: {len(state.kb_insights)} 字符")
    
    generator = ContentGenerator()
    
    # 获取已生成内容
    generated_content_dict = state.get_generated_content_dict()
    
    # 生成内容（✅ 传递知识库洞察）
    generated_field = generator.generate_content(
        current_field,
        state.user_input,
        generated_content_dict,
        kb_insights=state.kb_insights,  # ✅ 添加知识库洞察
    )
    
    # 保存生成结果
    state.generated_content[current_field.placeholder] = generated_field
    
    print(f"   ✅ 生成完成: {len(generated_field.content)} 字符")
    
    return state


def check_quality(state: ContentGenerationState) -> ContentGenerationState:
    """检查生成内容的质量"""
    current_field = state.get_current_field()
    
    if not current_field:
        return state
    
    generated_field = state.generated_content.get(current_field.placeholder)
    
    if not generated_field:
        return state
    
    generator = ContentGenerator()
    passed = generator.check_quality(generated_field, current_field)
    
    generated_field.passed_checks = passed
    
    if passed:
        print(f"   ✅ 质量检查通过")
        generated_field.quality_score = 0.9
    else:
        print(f"   ⚠️ 质量检查未通过")
        generated_field.quality_score = 0.5
    
    return state


def decide_retry(state: ContentGenerationState) -> str:
    """决定是否重试"""
    current_field = state.get_current_field()
    
    if not current_field:
        return "complete"
    
    generated_field = state.generated_content.get(current_field.placeholder)
    
    if not generated_field:
        return "next"  # 如果没有生成内容，跳过
    
    # 如果通过检查，继续下一个
    if generated_field.passed_checks:
        return "next"
    
    # 如果重试次数未超限，重试
    if generated_field.retry_count < state.max_retries:
        print(f"   🔄 重试第 {generated_field.retry_count + 1} 次")
        generated_field.retry_count += 1
        return "retry"
    
    # 超过重试次数，记录失败并继续
    print(f"   ❌ 重试次数已达上限，使用当前结果")
    state.failed_fields.append(current_field.placeholder)
    generated_field.passed_checks = True  # 强制通过，避免无限循环
    return "next"


def move_to_next_field(state: ContentGenerationState) -> ContentGenerationState:
    """移动到下一个字段"""
    state.completed_fields += 1
    state.current_index += 1
    
    # 检查是否完成
    if state.current_index >= len(state.analyzed_fields):
        state.is_complete = True
    
    # 显示进度
    progress = state.get_progress()
    print(f"   📊 进度: {progress:.1f}% ({state.completed_fields}/{state.total_fields})")
    
    return state


def check_completion(state: ContentGenerationState) -> str:
    """检查是否完成所有字段"""
    if state.is_complete:
        return "done"
    return "continue"


def inject_content(state: ContentGenerationState) -> ContentGenerationState:
    """将生成的内容注入到 Markdown 模板并重建 DOCX"""
    print("\n" + "=" * 80)
    print("💉 注入生成内容到模板")
    print("=" * 80)
    
    print(f"   - 已生成字段: {len(state.generated_content)}")
    print(f"   - 失败字段: {len(state.failed_fields)}")
    
    if state.failed_fields:
        print(f"   ⚠️ 以下字段生成失败:")
        for field in state.failed_fields:
            print(f"      - {field}")
    
    return state


def decide_generation_mode(state: ContentGenerationState) -> str:
    """
    决定使用批量生成还是单个生成模式
    """
    if state.batch_mode:
        return "batch"
    else:
        return "single"


def build_content_generation_graph(batch_mode: bool = True, batch_size: int = 5) -> StateGraph:
    """
    构建内容生成工作流图
    
    Args:
        batch_mode: 是否使用批量生成模式（默认 True）
        batch_size: 每批生成的字段数量（默认 5）
    """
    workflow = StateGraph(ContentGenerationState)
    
    # 添加节点
    workflow.add_node("load_inputs", load_inputs)
    workflow.add_node("analyze_fields", analyze_fields)
    workflow.add_node("generate_batch", generate_batch_content)  # 批量生成节点
    workflow.add_node("generate_content", generate_field_content)  # 单个生成节点
    workflow.add_node("check_quality", check_quality)
    workflow.add_node("move_next", move_to_next_field)
    workflow.add_node("inject_content", inject_content)
    
    # 设置入口
    workflow.set_entry_point("load_inputs")
    
    # 添加边
    workflow.add_edge("load_inputs", "analyze_fields")
    
    if batch_mode:
        # 批量生成模式
        workflow.add_edge("analyze_fields", "generate_batch")
        
        # 批量生成完成后检查是否所有批次都完成
        workflow.add_conditional_edges(
            "generate_batch",
            check_completion,
            {
                "continue": "generate_batch",  # 继续下一批
                "done": "inject_content",       # 完成
            }
        )
    else:
        # 单个生成模式（保持原有逻辑）
        workflow.add_edge("analyze_fields", "generate_content")
        workflow.add_edge("generate_content", "check_quality")
        
        # 条件分支：检查质量后决定重试或继续
        workflow.add_conditional_edges(
            "check_quality",
            decide_retry,
            {
                "retry": "generate_content",  # 重试
                "next": "move_next",          # 下一个
                "complete": "inject_content",  # 完成
            }
        )
        
        # 条件分支：检查是否完成所有字段
        workflow.add_conditional_edges(
            "move_next",
            check_completion,
            {
                "continue": "generate_content",
                "done": "inject_content",
            }
        )
    
    # 设置出口
    workflow.add_edge("inject_content", END)
    
    return workflow.compile()


def run_content_generation(
    annotation_path: str | Path,
    user_input: Dict[str, Any],
    markdown_path: str | Path,
    manifest_path: str | Path,
    output_dir: str | Path = "results/v4_generated",
    batch_mode: bool = True,
    batch_size: int = 5,
    kb_insights: str = "",
    doc_type: str = "task_proposal",  # 新增：文档类型
) -> Dict[str, Any]:
    """
    运行内容生成流程

    Args:
        annotation_path: 标注 JSON 路径
        user_input: 用户输入
        markdown_path: Markdown 模板路径
        manifest_path: Manifest 路径
        output_dir: 输出目录
        batch_mode: 是否使用批量生成模式（默认 True）
        batch_size: 每批生成的字段数量（默认 5）
        kb_insights: 知识库洞察（来自历史经验）
        doc_type: 文档类型（用于字段约束验证，如 task_proposal/lesson_plan）

    Returns:
        Dict: 包含生成结果和输出路径
    """
    print("\n" + "=" * 80)
    print("🚀 DocuAgent v4 - 内容生成流程")
    print("=" * 80)
    print(f"   模式: {'批量生成' if batch_mode else '单个生成'}")
    if batch_mode:
        print(f"   批次大小: {batch_size} 个字段/批")
    print(f"🔍 [DEBUG] kb_insights长度: {len(kb_insights)} 字符")
    if kb_insights:
        print(f"   kb_insights前100字符: {kb_insights[:100]}")
    else:
        print(f"   ⚠️ kb_insights为空！")
    
    # 加载输入文件
    annotation_path = Path(annotation_path)
    markdown_path = Path(markdown_path)
    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    
    with open(annotation_path, encoding="utf-8") as f:
        annotation_data = json.load(f)
    
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    
    annotations = annotation_data.get("annotations", [])
    
    def _analyze_user_prompt(ui: Dict[str, Any]) -> Dict[str, Any]:
        txt = " ".join(str(ui.get(k, "")) for k in ["prompt", "request", "task", "intent"]).strip()

        # 提取课程/主题
        topic = None
        # 优先匹配 "XXX课程教案" 或 "XXX教案"（排除课时数字）
        patterns = [
            r"(?:生成|写|制作|帮我)(?:\d+课时的)?\s*([\u4e00-\u9fa5A-Za-z]+(?:课程)?)\s*教案",  # "生成深度学习教案" 或 "生成深度学习课程教案"
            r"([\u4e00-\u9fa5A-Za-z]+(?:课程)?)\s*教案",  # 直接匹配 "深度学习教案"
        ]
        for pat in patterns:
            m = re.search(pat, txt)
            if m:
                topic = m.group(1).strip()
                # 去除可能的后缀
                topic = topic.replace("课程", "").strip()
                if topic:
                    break

        # 提取章节
        chapter = None
        for pat in [
            r"章节(?:名称)?为\s*([\u4e00-\u9fa5A-Za-z0-9_\-\s]+)",
            r"章节(?:名称)?是\s*([\u4e00-\u9fa5A-Za-z0-9_\-\s]+)",
            r"授课章节为\s*([\u4e00-\u9fa5A-Za-z0-9_\-\s]+)",
            r"章节[:：]\s*([\u4e00-\u9fa5A-Za-z0-9_\-\s]+)",
        ]:
            mm = re.search(pat, txt)
            if mm:
                chapter = mm.group(1).strip()
                break

        # 提取课时数
        ch = None
        mm = re.search(r"(\d+)\s*课时", txt)
        if mm:
            try:
                ch = int(mm.group(1))
            except Exception:
                ch = None

        # 判断单节课还是多节课
        scope = None
        if any(w in txt for w in ["单节", "一节", "单次", "一次"]):
            scope = "single"
        if not scope and isinstance(ch, int) and ch <= 2:
            scope = "single"

        return {"topic": topic, "chapter_section": chapter, "class_hours": ch, "lesson_scope": scope or "single"}
    
    pa = _analyze_user_prompt(user_input or {})
    user_input = dict(user_input or {})
    user_input["prompt_analysis"] = pa
    user_input["doc_type"] = doc_type  # ✅ 添加文档类型到user_input
    bi = user_input.setdefault("basic_info", {})
    tc = user_input.setdefault("teaching_context", {})

    # 🔧 修复：如果 prompt 中解析出了信息，优先使用 prompt 的信息覆盖默认值
    # 原逻辑：只有当字段为空时才填充，导致 prompt 被忽略
    # 新逻辑：prompt 解析结果优先级最高
    if pa.get("topic"):
        bi["course_name"] = pa["topic"]
    if pa.get("chapter_section"):
        bi["chapter_section"] = pa["chapter_section"]
    if pa.get("class_hours"):
        bi["class_hours"] = pa["class_hours"]
    if pa.get("lesson_scope"):
        tc["lesson_scope"] = pa["lesson_scope"]
    
    # 创建初始状态
    initial_state = ContentGenerationState(
        annotations=annotations,
        user_input=user_input,
        manifest=manifest,
        markdown_path=str(markdown_path),
        batch_mode=batch_mode,
        batch_size=batch_size,
        kb_insights=kb_insights,  # ✅ 注入知识库洞察
        doc_type=doc_type,  # ✅ 注入文档类型（用于字段约束验证）
    )
    
    print(f"🔍 [DEBUG] initial_state.kb_insights长度: {len(initial_state.kb_insights)} 字符")
    print(f"🔍 [DEBUG] initial_state.doc_type: {initial_state.doc_type}")
    
    # 构建并运行工作流
    graph = build_content_generation_graph(batch_mode=batch_mode, batch_size=batch_size)
    
    print(f"🔍 [DEBUG] 准备执行 graph.invoke...")
    final_state = graph.invoke(initial_state, {"recursion_limit": 1000})
    print(f"🔍 [DEBUG] graph.invoke 执行完成")
    
    # 兼容 LangGraph 返回 dict 的情形（而非 ContentGenerationState 实例）
    def _state_get(key, default=None):
        try:
            return final_state.get(key, default) if isinstance(final_state, dict) else getattr(final_state, key, default)
        except Exception:
            return default
    
    generated_map = _state_get("generated_content", {}) or {}
    failed_fields = _state_get("failed_fields", [])
    total_fields = _state_get("total_fields", 0)
    completed_fields = _state_get("completed_fields", 0)
    
    # 保存结果
    output_dir.mkdir(parents=True, exist_ok=True)
    
    generated_content_path = output_dir / "generated_content.json"
    user_prompt_path = output_dir / "user_input.json"
    with open(user_prompt_path, "w", encoding="utf-8") as f:
        json.dump(user_input, f, ensure_ascii=False, indent=2)
    with open(generated_content_path, "w", encoding="utf-8") as f:
        content_dict = {}
        for placeholder, field in generated_map.items():
            if hasattr(field, "content"):
                content = field.content
                char_count = getattr(field, "char_count", len(content))
                quality_score = getattr(field, "quality_score", 0.0)
                retry_count = getattr(field, "retry_count", 0)
            elif isinstance(field, dict):
                content = field.get("content", "")
                char_count = field.get("char_count", len(content))
                quality_score = field.get("quality_score", 0.0)
                retry_count = field.get("retry_count", 0)
            else:
                content = str(field)
                char_count = len(content)
                quality_score = 0.0
                retry_count = 0
            content_dict[placeholder] = {
                "content": content,
                "metadata": {
                    "char_count": char_count,
                    "quality_score": quality_score,
                    "retry_count": retry_count,
                }
            }
        json.dump(content_dict, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 80)
    print("✅ 内容生成完成！")
    print("=" * 80)
    print(f"   - 生成字段: {len(generated_map)}")
    print(f"   - 失败字段: {len(failed_fields)}")
    print(f"   - 生成内容JSON: {generated_content_path}")
    
    # 将生成的内容注入到标注中并重建 DOCX
    print("\n" + "=" * 80)
    print("📝 将内容注入到模板并生成最终 DOCX")
    print("=" * 80)
    
    # 创建填充后的标注
    # 构建回退占位符映射（当某些 {{var}} 无生成内容时，从用户输入推断）
    def _build_fallback_map(ui: Dict[str, Any]) -> Dict[str, str]:
        m: Dict[str, str] = {}
        bi = ui.get("basic_info", {}) or {}
        pa2 = ui.get("prompt_analysis", {}) or {}
        for k, v in {**bi, **pa2}.items():
            if v is None:
                continue
            m[str(k)] = str(v)
        # 常见同义键
        if "class_hours" in bi and "hours" not in m:
            m["hours"] = str(bi.get("class_hours"))
        if "credits" in bi and "credit" not in m:
            m["credit"] = str(bi.get("credits"))
        return m
    
    fallback_map = _build_fallback_map(user_input)
    label_dedup_pattern = re.compile(r"(^|[\n\r\t ])([\u4e00-\u9fa5A-Za-z（）()\-\s]{1,12}[:：])\s*\2")
    # 扩展：支持数字与常用标点，长度放宽到 24
    label_prefix_pattern = re.compile(r"^\s*[\u4e00-\u9fa5A-Za-z0-9（）()\-·、，,。；;【】\[\]—\-\s]{1,24}[:：]\s*")

    # 读取 Markdown 文本以获取单元格原始内容，用于表头保护
    md_text_for_guard = Path(markdown_path).read_text(encoding="utf-8")
    md_lines_for_guard = md_text_for_guard.splitlines()

    def _extract_cell_original_text(cell_marker: str) -> str:
        for line in md_lines_for_guard:
            if cell_marker in line and "|" in line:
                parts = line.split("|")
                for idx in range(1, len(parts) - 1):
                    seg = parts[idx]
                    if cell_marker in seg:
                        # 形如 " [[DOCX-CELL ...]] 文字 "
                        after = seg.split(cell_marker, 1)[1]
                        return after.strip()
        return ""

    def _is_real_header_label(text: str) -> bool:
        """判断是否是真正的表头标签（如'授课时间'），而不是待填充的模板（如'年 月 日'）"""
        if not text:
            return False
        t = text.strip()
        # 真正的标签通常：
        # 1. 包含实质性词汇（非纯时间/数字占位）
        # 2. 不包含大量空格（模板通常有很多空格用于占位）
        # 3. 长度适中（4-8个实质字符）

        # 如果包含大量空格（超过2个连续空格），很可能是模板占位
        if "   " in t or "  " in t:
            # 检查是否只是"年 月 日"这种纯时间占位符模板
            cleaned = re.sub(r"\s+", "", t)
            # 纯时间关键字模板，不是真正的表头
            time_template_keywords = ["年月日", "周星期", "第节", "时分", "节次"]
            if any(kw in cleaned for kw in time_template_keywords):
                return False

        # 真正的表头标签通常是有意义的词汇
        meaningful_headers = ["授课时间", "授课章节", "教学目标", "思政元素", "教学重点",
                             "教学难点", "教学方法", "教学资源", "教学内容", "教师活动",
                             "学生活动", "设计意图", "课前预习", "课中学创", "课后拓展",
                             "题目", "学院", "专业", "年级", "学号", "姓名", "环节"]
        return any(header in t for header in meaningful_headers)

    def _is_label_like(text: str) -> bool:
        if not text:
            return False
        t = text.replace("\r", "").strip()
        # 拆分多行标签（导出中用 <br> 表示）
        lines = [s.strip() for s in re.split(r"<br>+", t) if s.strip()]
        if not lines:
            return False
        # 放宽：允许数字与常见标点，长度阈值提升到 20
        pat = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9（）()\-·、，,。；;【】\[\]—\-\s]{1,20}[:：]?$")
        ok_lines = sum(1 for s in lines if pat.match(s) and ("。" not in s))
        # 行均为短语且不含句号，判定为表头/标签
        return ok_lines == len(lines)

    def _marker_has_header_hint(marker: str) -> bool:
        s = str(marker or "")
        # 垂直合并起始单元格（通常是标签列）
        if "vmerge=restart" in s:
            return True
        # row=0 需要结合列号判断：grid_col=0 才是表头，其他列是数据
        if "row=0" in s:
            try:
                col = int(_extract_marker_value(s, "grid_col=") or -1)
            except Exception:
                col = -1
            # 只有第0列（标签列）才视为表头
            return col == 0
        return False

    def _is_header_cell(marker: str, text: str) -> bool:
        return _marker_has_header_hint(marker) or _is_label_like(text)

    def _dedupe_value_label(value: str, label: str) -> str:
        if not label:
            return value
        # 去掉值前面重复的同名标签
        lab = re.escape(label.rstrip("：:"))
        rm = re.compile(r"^\s*" + lab + r"\s*[:：]\s*(.*)$")
        m = rm.match(value.strip())
        return (m.group(1) if m else value).strip()

    def _compose_with_label(label: str, value: str) -> str:
        if not label:
            return value.strip()
        lab = label.strip()
        # 若原标签是多行（含 <br>），将值放到新的一行
        if "<br>" in lab:
            return f"{lab}<br>{value.strip()}"
        # 单行标签：确保只有一个冒号
        if lab.endswith(":") or lab.endswith("："):
            return f"{lab}{value.strip()}"
        return f"{lab}：{value.strip()}"

    def _dedupe_header_text(text: str) -> str:
        t = (text or "").strip()
        parts = [s.strip() for s in re.split(r"(?:<br>|\n)+", t) if s.strip()]
        seen = set()
        out = []
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return "<br>".join(out)

    def _is_ellipsis_line(s: str) -> bool:
        x = re.sub(r"\s+", "", s or "")
        return bool(x) and re.fullmatch(r"[\.·•…]+", x) is not None

    def _cleanup_cell_value(text: str) -> str:
        t = (text or "").strip()
        # 统一分隔
        parts = [s.strip() for s in re.split(r"(?:<br>|\n)+", t) if s is not None]
        out = []
        for p in parts:
            if not p or _is_ellipsis_line(p):
                continue
            # 去除行内形如 ['文本'] 的残留括号与引号
            p = re.sub(r"\['([^\]]+?)'\]", r"\1", p)
            if out and out[-1] == p:
                continue
            out.append(p)
        return "<br>".join(out).strip()

    def _shorten_teacher_value(text: str) -> str:
        s = (text or "").strip()
        # 在第一个分隔符处截断
        parts = re.split(r"[，,。；;\n]", s, maxsplit=1)
        if parts and parts[0].strip():
            s = parts[0].strip()
        # 提取中文姓名 + 可选头衔
        m = re.search(r"([\u4e00-\u9fa5]{2,4})(?:教授|副教授|老师|博士)?", s)
        if m:
            s = m.group(0)
        # 再限长
        return s[:50].rstrip()

    def _has_meaningful_original(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        # 过滤纯占位或只有 <br>
        if "{{" in t and "}}" in t:
            return False
        t = re.sub(r"(?:<br>)+", "", t)
        t = re.sub(r"[\s\-_:：;；,，.。]+", "", t)
        # 只要还剩中英文或数字，视为有意义原文
        return bool(re.search(r"[\u4e00-\u9fa5A-Za-z0-9]", t))

    def _extract_row_header_text_for_marker(cell_marker: str) -> str:
        table_id = _extract_marker_value(cell_marker, "table=")
        row_id = _extract_marker_value(cell_marker, "row=")
        if not table_id or not row_id:
            return ""
        for line in md_lines_for_guard:
            if f"table={table_id}" in line and f"row={row_id}" in line and "|" in line:
                parts = line.split("|")
                texts = []
                for idx in range(1, len(parts) - 1):
                    seg = parts[idx]
                    if f"table={table_id}" in seg and f"row={row_id}" in seg and ("grid_col=0" in seg or "grid_col=1" in seg):
                        end = seg.find("]]")
                        if end != -1:
                            texts.append(seg[end + 2 :].strip())
                return " ".join([t for t in texts if t.strip()])
        return ""

    def _is_section_row(cell_marker: str) -> bool:
        header = _extract_row_header_text_for_marker(cell_marker)
        h = header.replace("<br>", "")
        if "授课章节" not in h:
            return False
        row_id = _extract_marker_value(cell_marker, "row=")
        return row_id == "1"

    def _shorten_section_value(text: str) -> str:
        s = (text or "").strip()
        s = label_prefix_pattern.sub("", s).strip()
        parts = re.split(r"[，,。；;、\n]", s, maxsplit=1)
        if parts and parts[0].strip():
            s = parts[0].strip()
        return s[:30].rstrip("，,。；;、")

    def _resolve_leftover_placeholders(text: str) -> str:
        def _repl(m: re.Match) -> str:
            key = (m.group(1) or "").strip()
            if key in fallback_map:
                return str(fallback_map[key])
            if key.startswith("section_name") or key.startswith("teaching_section_value"):
                # 章节相关：优先使用用户输入的章节名
                sec = fallback_map.get("chapter_section") or fallback_map.get("course_name") or ""
                return str(sec)
            return ""
        return re.sub(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", _repl, text or "")

    def _extract_paragraph_original_text(block_id: str) -> str:
        bid = str(block_id or "")
        for i, line in enumerate(md_lines_for_guard):
            s = line.strip()
            if s.startswith("[[DOCX-BLOCK ") and f"id={bid}" in s and "type=paragraph" in s:
                j = i + 1
                buf: List[str] = []
                while j < len(md_lines_for_guard):
                    ns = md_lines_for_guard[j].strip()
                    if ns.startswith("[[DOCX-BLOCK "):
                        break
                    buf.append(md_lines_for_guard[j])
                    j += 1
                return "\n".join(buf).strip()
        return ""

    label_only_re_par = re.compile(r"^\s*[\u4e00-\u9fa5A-Za-z（）()\-\s]{1,12}[:：]\s*$")
    def _has_meaningful_paragraph(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        if label_only_re_par.match(t):
            return False
        if "{{" in t and "}}" in t:
            return False
        t = re.sub(r"(?:<br>)+", "", t)
        t = re.sub(r"[\s\-_:：;；,，.。]+", "", t)
        return bool(re.search(r"[\u4e00-\u9fa5A-Za-z0-9]", t))
    # 预扫描：若同一单元格已存在 section_name* 占位符，则后续 teaching_section_value* 不再覆盖
    section_cells: set[str] = set()
    for a in annotations:
        ph0 = str(a.get("placeholder", "") or "").lower()
        if ph0.startswith("section_name") and a.get("location_type") == "table_cell" and a.get("cell_marker"):
            section_cells.add(a.get("cell_marker"))

    def _is_teaching_section_value(ph: str) -> bool:
        return str(ph or "").lower().startswith("teaching_section_value")

    def _is_section_placeholder(ph: str) -> bool:
        p = str(ph or "").lower()
        return p.startswith("section_name") or p.startswith("teaching_section_value")

    filled_annotations = []
    for annotation in annotations:
        ann_copy = annotation.copy()
        
        # 获取占位符
        placeholders = None
        if "placeholders" in ann_copy:
            maybe_list = ann_copy.get("placeholders", [])
            if isinstance(maybe_list, list):
                placeholders = [p for p in maybe_list if isinstance(p, str) and p.strip()]
            if not placeholders:
                ann_copy.pop("placeholders", None)
                placeholders = None

        if placeholders:
            # insert_multiple 类型
            # 替换所有占位符
            result = ann_copy.get("result", "")
            for placeholder in placeholders:
                # 🔥 修复：智能匹配placeholder
                matched_ph = None
                if placeholder in generated_map:
                    matched_ph = placeholder
                else:
                    # 尝试智能匹配
                    placeholder_clean = placeholder.replace("_", "").lower()
                    for key in generated_map.keys():
                        key_clean = key.replace("_", "").lower()
                        if placeholder_clean == key_clean or placeholder_clean in key_clean or key_clean in placeholder_clean:
                            matched_ph = key
                            print(f"   🔄 [Multi] Placeholder智能匹配: {placeholder} → {key}")
                            break

                if matched_ph:
                    _field = generated_map[matched_ph]
                    content = _field.content if hasattr(_field, "content") else (_field.get("content", "") if isinstance(_field, dict) else str(_field))
                    # 兼容 {{ placeholder }} 中的空格
                    pattern = re.compile(r"\{\{\s*" + re.escape(placeholder) + r"\s*\}\}")
                    result = pattern.sub(content, result)
                elif placeholder in fallback_map:
                    pattern = re.compile(r"\{\{\s*" + re.escape(placeholder) + r"\s*\}\}")
                    result = pattern.sub(str(fallback_map[placeholder]), result)
            if (ann_copy.get("location_type") == "table_cell"):
                cell_marker = ann_copy.get("cell_marker", "")
                original_text = _extract_cell_original_text(cell_marker)
                # 对于 insert_multiple，更严格的保护：只保护真正的表头标签
                # 如果原文是模板占位（如"年 月 日"），应该允许替换
                if _is_real_header_label(original_text):
                    # 真正的表头标签，保留原文
                    result = _dedupe_header_text(original_text)
                elif _has_meaningful_original(original_text) and not _is_real_header_label(original_text):
                    # 有意义的原文但不是表头标签，也可能需要保护
                    # 但如果已经成功替换了占位符，就不要覆盖
                    if "{{" in result and "}}" in result:
                        # 还有未替换的占位符，使用原文
                        result = original_text
                    # 否则保留已替换的 result
                else:
                    # 非表头：可安全去掉生成结果中多余的前缀标签
                    result = label_prefix_pattern.sub("", result).strip()
                    result = _resolve_leftover_placeholders(result)
                    result = _cleanup_cell_value(result)
                    if _is_section_row(cell_marker):
                        result = _shorten_section_value(result)
            # 去重：可能存在“标签：标签：内容”
            result = label_dedup_pattern.sub(r"\1\2", result)
            ann_copy["result"] = result
        else:
            # 单个占位符
            placeholder = ann_copy.get("placeholder", "")
            teacher_like = _is_teacher_placeholder(placeholder, annotation)
            if ann_copy.get("location_type") == "table_cell" and _is_teaching_section_value(placeholder):
                cm = ann_copy.get("cell_marker", "")
                if cm in section_cells:
                    continue

            # 🔥 修复：智能匹配placeholder（支持concept_content -> conception_content）
            matched_placeholder = None
            if placeholder in generated_map:
                matched_placeholder = placeholder
            else:
                # 尝试智能匹配（去除下划线、大小写不敏感）
                placeholder_clean = placeholder.replace("_", "").lower()
                for key in generated_map.keys():
                    key_clean = key.replace("_", "").lower()
                    if placeholder_clean == key_clean or placeholder_clean in key_clean or key_clean in placeholder_clean:
                        matched_placeholder = key
                        print(f"   🔄 Placeholder智能匹配: {placeholder} → {key}")
                        break

            if matched_placeholder:
                _field = generated_map[matched_placeholder]  # 🔥 使用匹配后的placeholder
                content = _field.content if hasattr(_field, "content") else (_field.get("content", "") if isinstance(_field, dict) else str(_field))
                # 根据 action 类型更新 result
                action = ann_copy.get("action", "")
                if action == "replace":
                    # 表格替换：若原单元格是表头/标签样式，则保留标签并与值合并
                    if (ann_copy.get("location_type") == "table_cell"):
                        cell_marker = ann_copy.get("cell_marker", "")
                        original_text = _extract_cell_original_text(cell_marker)
                        if _is_header_cell(cell_marker, original_text) or _has_meaningful_original(original_text):
                            ann_copy["result"] = _dedupe_header_text(original_text)
                        else:
                            content = label_prefix_pattern.sub("", content).strip()
                            content = _resolve_leftover_placeholders(content)
                            content = _cleanup_cell_value(content)
                            if _is_section_row(cell_marker):
                                sec = str(fallback_map.get("chapter_section") or fallback_map.get("course_name") or "").strip()
                                content = _shorten_section_value(sec or content)
                            ann_copy["result"] = content
                    else:
                        # 段落：teacher 类占位符保持简短
                        if teacher_like:
                            content = _shorten_teacher_value(content)
                        else:
                            orig_par = _extract_paragraph_original_text(ann_copy.get("block_id", ""))
                            if _has_meaningful_paragraph(orig_par):
                                content = orig_par
                        ann_copy["result"] = content
                elif action == "append":
                    # 保留标签部分，只替换占位符
                    result = ann_copy.get("result", "")
                    print(f"   🔍 [APPEND] {placeholder}: 原始result = {result[:100]}")

                    pattern = re.compile(r"\{\{\s*" + re.escape(placeholder) + r"\s*\}\}")
                    # 段落 teacher 类占位符：替换前先收缩内容
                    if ann_copy.get("location_type") == "paragraph" and teacher_like:
                        content = _shorten_teacher_value(content)
                    result = pattern.sub(content, result)
                    print(f"   🔍 [APPEND] {placeholder}: 替换后result = {result[:100]}")

                    # 🔧 FIX Bug #3: 检查占位符是否成功替换，如果成功则不要用 original_text 覆盖
                    has_unfilled_placeholders = bool(re.search(r"\{\{.+?\}\}", result))

                    if (ann_copy.get("location_type") == "table_cell"):
                        cell_marker = ann_copy.get("cell_marker", "")
                        original_text = _extract_cell_original_text(cell_marker)
                        # 检查original_text是否只是标题（result的前缀）
                        result_prefix = result.split("<br>")[0].strip() if "<br>" in result else result.strip()
                        original_normalized = re.sub(r'<br>', '', original_text).strip()
                        result_prefix_normalized = re.sub(r'<br>', '', result_prefix).strip()
                        is_only_header = (original_normalized == result_prefix_normalized)

                        print(f"   🔍 [APPEND] {placeholder}: has_unfilled={has_unfilled_placeholders}, is_only_header={is_only_header}")

                        # 只有在占位符未成功替换时，才考虑使用 original_text 覆盖
                        if has_unfilled_placeholders and not is_only_header and (_is_header_cell(cell_marker, original_text) or _has_meaningful_original(original_text)):
                            result = _dedupe_header_text(original_text)
                            print(f"   🔍 [APPEND] {placeholder}: 使用original_text")
                        else:
                            # 🔥 修复: append模式下不删除标签前缀，保留标题(如"一、目的与意义<br>内容")
                            # 只删除leftover占位符和清理格式
                            result_before_cleanup = result
                            result = _resolve_leftover_placeholders(result)
                            result = _cleanup_cell_value(result)
                            print(f"   🔍 [APPEND] {placeholder}: 清理后result = {result[:100]}")
                            if _is_section_row(cell_marker):
                                sec = str(fallback_map.get("chapter_section") or fallback_map.get("course_name") or "").strip()
                                result = _shorten_section_value(sec or result)
                                print(f"   🔍 [APPEND] {placeholder}: 缩短后result = {result[:100]}")
                    # 去重标签
                    result_before_dedup = result
                    result = label_dedup_pattern.sub(r"\1\2", result)
                    if result != result_before_dedup:
                        print(f"   🔍 [APPEND] {placeholder}: 去重后result = {result[:100]}")
                    ann_copy["result"] = result
                    print(f"   ✅ [APPEND] {placeholder}: 最终result = {result[:100]}")
            elif placeholder in fallback_map:
                action = ann_copy.get("action", "")
                if action == "replace":
                    if (ann_copy.get("location_type") == "table_cell"):
                        cell_marker = ann_copy.get("cell_marker", "")
                        original_text = _extract_cell_original_text(cell_marker)
                        if _is_header_cell(cell_marker, original_text):
                            ann_copy["result"] = _dedupe_header_text(original_text)
                        else:
                            val = str(fallback_map[placeholder])
                            if teacher_like:
                                val = _shorten_teacher_value(val)
                            if _is_section_row(cell_marker):
                                sec = str(fallback_map.get("chapter_section") or fallback_map.get("course_name") or "").strip()
                                val = _shorten_section_value(sec or val)
                            val = _cleanup_cell_value(val)
                            ann_copy["result"] = val
                    else:
                        val = str(fallback_map[placeholder])
                        if teacher_like:
                            val = _shorten_teacher_value(val)
                        ann_copy["result"] = val
                elif action == "append":
                    result = ann_copy.get("result", "")
                    pattern = re.compile(r"\{\{\s*" + re.escape(placeholder) + r"\s*\}\}")
                    rep = str(fallback_map[placeholder])
                    if ann_copy.get("location_type") == "paragraph" and teacher_like:
                        rep = _shorten_teacher_value(rep)
                    result = pattern.sub(rep, result)

                    # 🔧 FIX Bug #3: 检查占位符是否成功替换，如果成功则不要用 original_text 覆盖
                    has_unfilled_placeholders = bool(re.search(r"\{\{.+?\}\}", result))

                    if (ann_copy.get("location_type") == "table_cell"):
                        cell_marker = ann_copy.get("cell_marker", "")
                        original_text = _extract_cell_original_text(cell_marker)
                        # 🔧 FIX: 检查original_text是否只是标题（result的前缀）
                        # 需要标准化：移除<br>标签后再比较
                        result_prefix = result.split("<br>")[0].strip() if "<br>" in result else result.strip()
                        original_normalized = re.sub(r'<br>', '', original_text).strip()
                        result_prefix_normalized = re.sub(r'<br>', '', result_prefix).strip()
                        is_only_header = (original_normalized == result_prefix_normalized)

                        # 只有在占位符未成功替换时，才考虑使用 original_text 覆盖
                        if has_unfilled_placeholders and not is_only_header and _is_header_cell(cell_marker, original_text):
                            result = _dedupe_header_text(original_text)
                        else:
                            result = label_prefix_pattern.sub("", result).strip()
                            result = _cleanup_cell_value(result)
                            if _is_section_row(cell_marker):
                                sec = str(fallback_map.get("chapter_section") or fallback_map.get("course_name") or "").strip()
                                result = _shorten_section_value(sec or result)
                    result = label_dedup_pattern.sub(r"\1\2", result)
                    ann_copy["result"] = result
            else:
                # 兜底：章节相关占位符，使用用户输入章节名
                if _is_section_placeholder(placeholder):
                    if ann_copy.get("location_type") == "table_cell":
                        cell_marker = ann_copy.get("cell_marker", "")
                        original_text = _extract_cell_original_text(cell_marker)
                        if _is_header_cell(cell_marker, original_text):
                            ann_copy["result"] = original_text
                        else:
                            sec = str(fallback_map.get("chapter_section") or fallback_map.get("course_name") or "").strip()
                            sec = _shorten_section_value(sec)
                            ann_copy["result"] = sec
        
        filled_annotations.append(ann_copy)
    
    # 保存填充后的标注
    filled_annotation_data = {"annotations": filled_annotations}
    filled_annotation_path = output_dir / "filled_annotation.json"
    with open(filled_annotation_path, "w", encoding="utf-8") as f:
        json.dump(filled_annotation_data, f, ensure_ascii=False, indent=2)
    
    print(f"   - 填充后标注: {filled_annotation_path}")
    
    # 应用到 Markdown 并重建 DOCX
    apply_result = apply_annotations_and_rebuild_docx(
        md_path=markdown_path,
        annotations_json_path=filled_annotation_path,
        manifest_path=manifest_path,
        output_md_path=output_dir / f"{markdown_path.stem}_annotated.md",
        output_docx_path=output_dir / "final.docx",
    )
    
    print(f"   ✅ 填充后 Markdown: {apply_result['markdown']}")
    print(f"   ✅ 最终 DOCX: {apply_result['docx']}")
    
    return {
        "generated_content": {p: (v.content if hasattr(v, "content") else (v.get("content", "") if isinstance(v, dict) else str(v))) for p, v in generated_map.items()},
        "generated_content_path": str(generated_content_path),
        "filled_annotation_path": str(filled_annotation_path),
        "annotated_markdown_path": str(apply_result["markdown"]),
        "final_docx_path": str(apply_result["docx"]),
        "failed_fields": failed_fields,
        "total_fields": total_fields,
        "completed_fields": completed_fields,
    }


def reinject_with_existing_generation(
    *,
    annotation_path: str | Path,
    markdown_path: str | Path,
    manifest_path: str | Path,
    generated_content_json_path: str | Path,
    output_dir: str | Path,
    user_input_path: str | Path | None = None,
) -> Dict[str, Any]:
    """仅使用已有的 generated_content.json 重新注入并重建 DOCX。
    不进行任何 LLM 调用，便于快速验证注入/清洗规则。
    """
    annotation_path = Path(annotation_path)
    markdown_path = Path(markdown_path)
    manifest_path = Path(manifest_path)
    gen_json_path = Path(generated_content_json_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(annotation_path, encoding="utf-8") as f:
        ann_data = json.load(f)
    annotations = ann_data.get("annotations", [])

    with open(gen_json_path, encoding="utf-8") as f:
        gen_map_raw = json.load(f)
    
    # 🔥 修复：兼容嵌套的 {"generated_content": {...}, "generation_stats": {...}} 结构
    if isinstance(gen_map_raw, dict) and "generated_content" in gen_map_raw:
        gen_map_raw = gen_map_raw["generated_content"]
    
    # 兼容 {placeholder: {content: str, metadata: {...}}} 或 {placeholder: str}
    generated_map: Dict[str, str] = {}
    for k, v in (gen_map_raw or {}).items():
        if isinstance(v, dict) and "content" in v:
            generated_map[k] = str(v.get("content", ""))
        else:
            generated_map[k] = str(v)

    # 可选：用于 fallback 的用户输入
    ui: Dict[str, Any] = {}
    if user_input_path:
        try:
            with open(user_input_path, encoding="utf-8") as f:
                ui = json.load(f)
        except Exception:
            ui = {}

    def _build_fallback_map(ui: Dict[str, Any]) -> Dict[str, str]:
        m: Dict[str, str] = {}
        bi = ui.get("basic_info", {}) or {}
        pa2 = ui.get("prompt_analysis", {}) or {}
        for kk, vv in {**bi, **pa2}.items():
            if vv is None:
                continue
            m[str(kk)] = str(vv)
        if "class_hours" in bi and "hours" not in m:
            m["hours"] = str(bi.get("class_hours"))
        if "credits" in bi and "credit" not in m:
            m["credit"] = str(bi.get("credits"))
        return m

    fallback_map = _build_fallback_map(ui) if ui else {}
    label_dedup_pattern = re.compile(r"(^|[\n\r\t ])([\u4e00-\u9fa5A-Za-z（）()\-\s]{1,12}[:：])\s*\2")
    # 扩展：支持数字与常用标点，长度放宽到 24
    label_prefix_pattern = re.compile(r"^\s*[\u4e00-\u9fa5A-Za-z0-9（）()\-·、，,。；;【】\[\]—\-\s]{1,24}[:：]\s*")

    md_text_for_guard = Path(markdown_path).read_text(encoding="utf-8")
    md_lines_for_guard = md_text_for_guard.splitlines()

    def _extract_cell_original_text(cell_marker: str) -> str:
        for line in md_lines_for_guard:
            if cell_marker in line and "|" in line:
                parts = line.split("|")
                for idx in range(1, len(parts) - 1):
                    seg = parts[idx]
                    if cell_marker in seg:
                        after = seg.split(cell_marker, 1)[1]
                        return after.strip()
        return ""

    def _is_label_like(text: str) -> bool:
        if not text:
            return False
        t = text.replace("\r", "").strip()
        lines = [s.strip() for s in re.split(r"<br>+", t) if s.strip()]
        if not lines:
            return False
        pat = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9（）()\-·、，,。；;【】\[\]—\-\s]{1,20}[:：]?$")
        return all(pat.match(s) and ("。" not in s) for s in lines)

    def _marker_has_header_hint(marker: str) -> bool:
        s = str(marker or "")
        return ("row=0" in s) or ("vmerge=restart" in s)

    def _is_header_cell(marker: str, text: str) -> bool:
        return _marker_has_header_hint(marker) or _is_label_like(text)

    def _dedupe_value_label(value: str, label: str) -> str:
        if not label:
            return value
        lab = re.escape(label.rstrip("：:"))
        rm = re.compile(r"^\s*" + lab + r"\s*[:：]\s*(.*)$")
        m = rm.match(value.strip())
        return (m.group(1) if m else value).strip()

    def _compose_with_label(label: str, value: str) -> str:
        if not label:
            return value.strip()
        lab = label.strip()
        if "<br>" in lab:
            return f"{lab}<br>{value.strip()}"
        if lab.endswith(":") or lab.endswith("："):
            return f"{lab}{value.strip()}"
        return f"{lab}：{value.strip()}"

    def _dedupe_header_text(text: str) -> str:
        t = (text or "").strip()
        parts = [s.strip() for s in re.split(r"(?:<br>|\n)+", t) if s.strip()]
        seen = set()
        out = []
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return "<br>".join(out)

    def _is_ellipsis_line(s: str) -> bool:
        x = re.sub(r"\s+", "", s or "")
        return bool(x) and re.fullmatch(r"[\.·•…]+", x) is not None

    def _cleanup_cell_value(text: str) -> str:
        t = (text or "").strip()
        parts = [s.strip() for s in re.split(r"(?:<br>|\n)+", t) if s is not None]
        out = []
        for p in parts:
            if not p or _is_ellipsis_line(p):
                continue
            if out and out[-1] == p:
                continue
            out.append(p)
        return "<br>".join(out).strip()

    def _resolve_leftover_placeholders(text: str) -> str:
        def _repl(m: re.Match) -> str:
            key = (m.group(1) or "").strip()
            if key in fallback_map:
                return str(fallback_map[key])
            if key.startswith("section_name") or key.startswith("teaching_section_value"):
                sec = fallback_map.get("chapter_section") or fallback_map.get("course_name") or ""
                return str(sec)
            return ""
        return re.sub(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", _repl, text or "")

    def _shorten_teacher_value(text: str) -> str:
        s = (text or "").strip()
        parts = re.split(r"[，,。；;\n]", s, maxsplit=1)
        if parts and parts[0].strip():
            s = parts[0].strip()
        m = re.search(r"([\u4e00-\u9fa5]{2,4})(?:教授|副教授|老师|博士)?", s)
        if m:
            s = m.group(0)
        return s[:50].rstrip()

    def _extract_row_header_text_for_marker(cell_marker: str) -> str:
        table_id = _extract_marker_value(cell_marker, "table=")
        row_id = _extract_marker_value(cell_marker, "row=")
        if not table_id or not row_id:
            return ""
        for line in md_lines_for_guard:
            if f"table={table_id}" in line and f"row={row_id}" in line and "|" in line:
                parts = line.split("|")
                texts = []
                for idx in range(1, len(parts) - 1):
                    seg = parts[idx]
                    if f"table={table_id}" in seg and f"row={row_id}" in seg and ("grid_col=0" in seg or "grid_col=1" in seg):
                        end = seg.find("]]")
                        if end != -1:
                            texts.append(seg[end + 2 :].strip())
                return " ".join([t for t in texts if t.strip()])
        return ""

    def _is_section_row(cell_marker: str) -> bool:
        header = _extract_row_header_text_for_marker(cell_marker)
        h = header.replace("<br>", "")
        if "授课章节" not in h:
            return False
        row_id = _extract_marker_value(cell_marker, "row=")
        return row_id == "1"

    def _shorten_section_value(text: str) -> str:
        s = (text or "").strip()
        s = label_prefix_pattern.sub("", s).strip()
        parts = re.split(r"[，,。；;、\n]", s, maxsplit=1)
        if parts and parts[0].strip():
            s = parts[0].strip()
        return s[:30].rstrip("，,。；;、")

    def _extract_paragraph_original_text(block_id: str) -> str:
        bid = str(block_id or "")
        lines = md_lines_for_guard
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("[[DOCX-BLOCK ") and f"id={bid}" in s and "type=paragraph" in s:
                j = i + 1
                buf: List[str] = []
                while j < len(lines):
                    ns = lines[j].strip()
                    if ns.startswith("[[DOCX-BLOCK "):
                        break
                    buf.append(lines[j])
                    j += 1
                return "\n".join(buf).strip()
        return ""

    label_only_re_par = re.compile(r"^\s*[\u4e00-\u9fa5A-Za-z（）()\-\s]{1,12}[:：]\s*$")
    def _has_meaningful_paragraph(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        if label_only_re_par.match(t):
            return False
        if "{{" in t and "}}" in t:
            return False
        t = re.sub(r"(?:<br>)+", "", t)
        t = re.sub(r"[\s\-_:：;；,，.。]+", "", t)
        return bool(re.search(r"[\u4e00-\u9fa5A-Za-z0-9]", t))

    # 预扫描：若同一单元格已存在 section_name* 占位符，则后续 teaching_section_value* 不再覆盖
    section_cells: set[str] = set()
    for a in annotations:
        ph0 = str(a.get("placeholder", "") or "").lower()
        if ph0.startswith("section_name") and a.get("location_type") == "table_cell" and a.get("cell_marker"):
            section_cells.add(a.get("cell_marker"))

    def _is_teaching_section_value(ph: str) -> bool:
        return str(ph or "").lower().startswith("teaching_section_value")

    filled_annotations: List[Dict[str, Any]] = []
    for annotation in annotations:
        ann_copy = dict(annotation)
        placeholders = None
        if "placeholders" in ann_copy:
            maybe_list = ann_copy.get("placeholders", [])
            if isinstance(maybe_list, list):
                placeholders = [p for p in maybe_list if isinstance(p, str) and p.strip()]
            if not placeholders:
                ann_copy.pop("placeholders", None)
                placeholders = None

        if placeholders:
            result = ann_copy.get("result", "")
            for ph in placeholders:
                if ph in generated_map:
                    pattern = re.compile(r"\{\{\s*" + re.escape(ph) + r"\s*\}\}")
                    result = pattern.sub(generated_map[ph], result)
                elif ph in fallback_map:
                    pattern = re.compile(r"\{\{\s*" + re.escape(ph) + r"\s*\}\}")
                    result = pattern.sub(str(fallback_map[ph]), result)
                if (ann_copy.get("location_type") == "table_cell"):
                    cell_marker = ann_copy.get("cell_marker", "")
                    original_text = _extract_cell_original_text(cell_marker)
                    if _is_header_cell(cell_marker, original_text):
                        result = _dedupe_header_text(original_text)
                    else:
                        result = label_prefix_pattern.sub("", result).strip()
                        result = _resolve_leftover_placeholders(result)
                        result = _cleanup_cell_value(result)
                        if _is_section_row(cell_marker):
                            sec = str(fallback_map.get("chapter_section") or fallback_map.get("course_name") or "").strip()
                            result = _shorten_section_value(sec or result)
                    result = label_dedup_pattern.sub(r"\1\2", result)
                    ann_copy["result"] = result
        else:
            ph = ann_copy.get("placeholder", "")
            action = ann_copy.get("action", "")
            is_teacher = _is_teacher_placeholder(ph, annotation)
            if ann_copy.get("location_type") == "table_cell" and _is_teaching_section_value(ph):
                cm = ann_copy.get("cell_marker", "")
                if cm in section_cells:
                    # 跳过冗余的 teaching_section_value，以免覆盖 section_name*
                    continue
            if ph in generated_map:
                if action == "replace":
                    if (ann_copy.get("location_type") == "table_cell"):
                        cell_marker = ann_copy.get("cell_marker", "")
                        original_text = _extract_cell_original_text(cell_marker)
                        if _is_header_cell(cell_marker, original_text):
                            ann_copy["result"] = _dedupe_header_text(original_text)
                        else:
                            # 仍在表格场景：去前缀、占位清理、去冗余行
                            val = label_prefix_pattern.sub("", generated_map[ph]).strip()
                            val = _resolve_leftover_placeholders(val)
                            val = _cleanup_cell_value(val)
                            if _is_section_row(cell_marker):
                                sec = str(fallback_map.get("chapter_section") or fallback_map.get("course_name") or "").strip()
                                val = _shorten_section_value(sec or val)
                            ann_copy["result"] = val
                    elif ann_copy.get("location_type") == "paragraph":
                        # 段落：教师字段收短；其他字段保护原文
                        if is_teacher:
                            ann_copy["result"] = _shorten_teacher_value(generated_map[ph])
                        else:
                            orig_par = _extract_paragraph_original_text(ann_copy.get("block_id", ""))
                            if _has_meaningful_paragraph(orig_par):
                                ann_copy["result"] = orig_par
                            else:
                                ann_copy["result"] = label_prefix_pattern.sub("", generated_map[ph]).strip()
                    else:
                        # 其他位置类型：简单去前缀
                        ann_copy["result"] = label_prefix_pattern.sub("", generated_map[ph]).strip()
                else:
                    result = ann_copy.get("result", "")
                    pattern = re.compile(r"\{\{\s*" + re.escape(ph) + r"\s*\}\}")
                    rep = generated_map[ph]
                    if ann_copy.get("location_type") == "paragraph" and is_teacher:
                        rep = _shorten_teacher_value(rep)
                    result = pattern.sub(rep, result)
                    if (ann_copy.get("location_type") == "table_cell"):
                        cell_marker = ann_copy.get("cell_marker", "")
                        original_text = _extract_cell_original_text(cell_marker)
                        # 🔧 FIX: 检查original_text是否只是标题（result的前缀）
                        # 如果是，则不应该覆盖已填充的result
                        # 需要标准化：移除<br>标签后再比较
                        result_prefix = result.split("<br>")[0].strip() if "<br>" in result else result.strip()
                        original_normalized = re.sub(r'<br>', '', original_text).strip()
                        result_prefix_normalized = re.sub(r'<br>', '', result_prefix).strip()
                        is_only_header = (original_normalized == result_prefix_normalized)

                        if not is_only_header and _is_header_cell(cell_marker, original_text):
                            result = _dedupe_header_text(original_text)
                        else:
                            result = label_prefix_pattern.sub("", result).strip()
                            result = _resolve_leftover_placeholders(result)
                            result = _cleanup_cell_value(result)
                            if _is_section_row(cell_marker):
                                result = _shorten_section_value(result)
                    result = label_dedup_pattern.sub(r"\1\2", result)
                    ann_copy["result"] = result
            elif ph in fallback_map:
                if action == "replace":
                    if (ann_copy.get("location_type") == "table_cell"):
                        cell_marker = ann_copy.get("cell_marker", "")
                        original_text = _extract_cell_original_text(cell_marker)
                        if _is_header_cell(cell_marker, original_text):
                            ann_copy["result"] = _dedupe_header_text(original_text)
                        elif ann_copy.get("location_type") == "paragraph" and is_teacher:
                            ann_copy["result"] = _shorten_teacher_value(str(fallback_map[ph]))
                        else:
                            val = label_prefix_pattern.sub("", str(fallback_map[ph])).strip()
                            val = _resolve_leftover_placeholders(val)
                            val = _cleanup_cell_value(val)
                            if _is_section_row(cell_marker):
                                val = _shorten_section_value(val)
                            ann_copy["result"] = val
                else:
                    result = ann_copy.get("result", "")
                    pattern = re.compile(r"\{\{\s*" + re.escape(ph) + r"\s*\}\}")
                    rep = str(fallback_map[ph])
                    if ann_copy.get("location_type") == "paragraph" and is_teacher:
                        rep = _shorten_teacher_value(rep)
                    result = pattern.sub(rep, result)
                    if (ann_copy.get("location_type") == "table_cell"):
                        cell_marker = ann_copy.get("cell_marker", "")
                        original_text = _extract_cell_original_text(cell_marker)
                        # 🔧 FIX: 检查original_text是否只是标题（result的前缀）
                        # 需要标准化：移除<br>标签后再比较
                        result_prefix = result.split("<br>")[0].strip() if "<br>" in result else result.strip()
                        original_normalized = re.sub(r'<br>', '', original_text).strip()
                        result_prefix_normalized = re.sub(r'<br>', '', result_prefix).strip()
                        is_only_header = (original_normalized == result_prefix_normalized)

                        if not is_only_header and _is_header_cell(cell_marker, original_text):
                            result = original_text
                        else:
                            result = label_prefix_pattern.sub("", result).strip()
                            if _is_section_row(cell_marker):
                                result = _shorten_section_value(result)
                    result = label_dedup_pattern.sub(r"\1\2", result)
                    ann_copy["result"] = result
        filled_annotations.append(ann_copy)

    filled_annotation_path = output_dir / "filled_annotation_reinject.json"
    with open(filled_annotation_path, "w", encoding="utf-8") as f:
        json.dump({"annotations": filled_annotations}, f, ensure_ascii=False, indent=2)

    apply_result = apply_annotations_and_rebuild_docx(
        md_path=markdown_path,
        annotations_json_path=filled_annotation_path,
        manifest_path=manifest_path,
        output_md_path=output_dir / f"{markdown_path.stem}_annotated_reinject.md",
        output_docx_path=output_dir / "final_reinject.docx",
    )

    return {
        "filled_annotation_path": str(filled_annotation_path),
        "annotated_markdown_path": str(apply_result["markdown"]),
        "final_docx_path": str(apply_result["docx"]),
    }
