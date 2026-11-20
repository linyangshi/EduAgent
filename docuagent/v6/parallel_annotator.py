"""
V6 并行标注器 - 使用多线程实现并发标注

核心思路：
1. 将文档分段（复用V4的segment_markdown）
2. 使用ThreadPoolExecutor并行调用LLM
3. 使用Semaphore控制并发数，避免API限流
4. 收集并合并结果
"""

import re
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Semaphore
from typing import Any, Callable, Dict, List, Optional, Tuple

# 使用V6改进的核心组件（包含行标签单元格保护规则）
from .run_llm_annotation import (
    segment_markdown,
    build_prompt_input,
    extract_json,
    load_text,
    MAX_SEGMENT_CHARS,
)
from .llm_annotator import (
    create_annotation_prompt,
    stream_gitcode_chat,
    TemplateTooComplexError,
)


class ParallelAnnotationResult:
    """并行标注结果"""
    def __init__(self):
        self.combined_annotations: List[Dict[str, Any]] = []
        self.segment_results: List[Dict[str, Any]] = []
        self.failures: List[str] = []
        self.total_time: float = 0.0
        self.individual_times: List[float] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "annotations": self.combined_annotations,
            "segment_results": self.segment_results,
            "failures": self.failures,
            "total_time": self.total_time,
            "avg_segment_time": sum(self.individual_times) / len(self.individual_times) if self.individual_times else 0,
            "max_segment_time": max(self.individual_times) if self.individual_times else 0,
            "speedup_ratio": sum(self.individual_times) / self.total_time if self.total_time > 0 else 1.0,
        }


def _emit_progress(
    progress_callback: Optional[Callable[[int, int, str], None]],
    completed: int,
    total: int,
    message: str,
) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(completed, total, message)
    except Exception as exc:
        print(f"⚠️ 并行标注进度回调失败: {exc}")


def _summarize_exception(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    if "Invalid format specifier" in message:
        return "标注提示词构建失败"
    if len(message) > 180:
        return message[:177] + "..."
    return message


def annotate_single_segment(
    segment_idx: int,
    segment_text: str,
    total_segments: int,
    features_text: Optional[str],
    kb_insights: Optional[str],
    semaphore: Semaphore,
    output_dir: Optional[Path] = None,
    doc_type: str = "lesson_plan",
) -> Tuple[int, Optional[Dict[str, Any]], float, Optional[str]]:
    """
    标注单个segment（线程安全）

    返回: (segment_idx, parsed_result, elapsed_time, error_message)
    """
    segment_label = f"{segment_idx}/{total_segments}"
    start_time = time.time()
    error_msg = None
    parsed = None

    try:
        # 使用信号量控制并发
        with semaphore:
            print(f"🔄 [线程 {segment_label}] 开始标注...")

            # 构建prompt（为每个segment添加唯一前缀）
            prompt_input = build_prompt_input(
                segment_text,
                features_text=features_text,
                segment_label=segment_label,
            )

            # 修改prompt，添加segment前缀指示
            prompt = create_annotation_prompt(prompt_input, kb_insights=kb_insights, doc_type=doc_type)

            # 在 prompt 开头直接插入段前缀要求，避免依赖 replace 命中某个固定短语。
            segment_prefix_instruction = (
                f"⚠️ 重要：由于文档被分段处理，请在所有占位符名称前添加前缀 \"seg{segment_idx}_\"\n"
                f"例如: \"course_name\" → \"seg{segment_idx}_course_name\"\n"
                "这样可以避免不同段落之间的命名冲突。\n\n"
            )
            prompt = segment_prefix_instruction + prompt

            # 调用LLM
            messages = [{"role": "user", "content": prompt}]
            response = stream_gitcode_chat(messages, temperature=0.3)

            # 保存原始响应
            if output_dir:
                raw_dir = output_dir / "raw_parallel"
                raw_dir.mkdir(parents=True, exist_ok=True)
                raw_path = raw_dir / f"segment_{segment_idx:02d}_parallel.txt"
                raw_path.write_text(response, encoding="utf-8")

            # 解析JSON
            parsed = extract_json(response)

            if parsed is None:
                error_msg = f"Segment {segment_idx} 无法解析为合法 JSON"
            else:
                annotations = parsed.get("annotations", [])
                if not isinstance(annotations, list):
                    error_msg = f"Segment {segment_idx} 的 JSON 缺少 annotations 列表"
                    parsed = None
                else:
                    print(f"✅ [线程 {segment_label}] 完成，找到 {len(annotations)} 个标注")

    except TemplateTooComplexError as e:
        error_msg = f"Segment {segment_idx}: {_summarize_exception(e)}"
        print(f"❌ [线程 {segment_label}] {error_msg}")

    except Exception as e:
        error_msg = f"Segment {segment_idx} 处理失败: {_summarize_exception(e)}"
        print(f"❌ [线程 {segment_label}] {error_msg}")

    elapsed_time = time.time() - start_time
    return segment_idx, parsed, elapsed_time, error_msg


def parallel_annotate(
    md_path: Path,
    features_path: Optional[Path] = None,
    kb_insights: Optional[str] = None,
    output_dir: Optional[Path] = None,
    max_concurrent: int = 3,
    no_segment: bool = False,
    doc_type: str = "lesson_plan",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> ParallelAnnotationResult:
    """
    并行标注主函数

    参数:
        md_path: Markdown文件路径
        features_path: 特征文件路径
        kb_insights: 知识库洞察
        output_dir: 输出目录
        max_concurrent: 最大并发数（建议3-5）
        no_segment: 是否禁用分段（True=单段处理）

    返回:
        ParallelAnnotationResult 对象
    """
    print(f"\n{'='*60}")
    print(f"V6 并行标注 - 最大并发数: {max_concurrent}")
    print(f"{'='*60}\n")

    result = ParallelAnnotationResult()
    overall_start = time.time()

    # 加载文档
    markdown_text = load_text(md_path)
    features_text = load_text(features_path) if features_path and features_path.exists() else None

    # 分段
    segments = [markdown_text] if no_segment else segment_markdown(markdown_text, MAX_SEGMENT_CHARS)
    total_segments = len(segments)

    print(f"📄 文档已分为 {total_segments} 个段落")
    print(f"🔧 并发配置: 最大 {max_concurrent} 个线程同时处理\n")
    _emit_progress(progress_callback, 0, total_segments, f"文档分为 {total_segments} 段，开始并行标注")

    # 如果只有1个segment，降级为顺序处理
    if total_segments == 1:
        print("⚠️  只有1个段落，无需并行处理\n")
        max_concurrent = 1

    # 创建信号量控制并发数
    semaphore = Semaphore(max_concurrent)

    # 使用线程池执行并行标注
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        # 提交所有任务
        future_to_idx = {}
        for idx, segment in enumerate(segments, start=1):
            future = executor.submit(
                annotate_single_segment,
                segment_idx=idx,
                segment_text=segment,
                total_segments=total_segments,
                features_text=features_text,
                kb_insights=kb_insights,
                semaphore=semaphore,
                output_dir=output_dir,
                doc_type=doc_type,
            )
            future_to_idx[future] = idx

        # 收集结果（按完成顺序）
        segment_results_dict = {}
        completed_segments = 0
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                segment_idx, parsed, elapsed_time, error_msg = future.result()

                segment_results_dict[segment_idx] = {
                    "segment_idx": segment_idx,
                    "parsed": parsed,
                    "elapsed_time": elapsed_time,
                    "error": error_msg,
                }

                result.individual_times.append(elapsed_time)

                if error_msg:
                    result.failures.append(error_msg)
                    completed_segments += 1
                    _emit_progress(
                        progress_callback,
                        completed_segments,
                        total_segments,
                        f"并行标注 {completed_segments}/{total_segments} 段完成，{segment_idx} 段失败",
                    )
                else:
                    annotation_count = 0
                    if parsed and isinstance(parsed.get("annotations"), list):
                        annotation_count = len(parsed["annotations"])
                    completed_segments += 1
                    _emit_progress(
                        progress_callback,
                        completed_segments,
                        total_segments,
                        f"并行标注 {completed_segments}/{total_segments} 段完成，识别到 {annotation_count} 个标注",
                    )

            except Exception as e:
                error_msg = f"Segment {idx} 线程执行异常: {_summarize_exception(e)}"
                result.failures.append(error_msg)
                print(f"❌ {error_msg}")
                completed_segments += 1
                _emit_progress(
                    progress_callback,
                    completed_segments,
                    total_segments,
                    f"并行标注 {completed_segments}/{total_segments} 段完成，{idx} 段异常",
                )

    # 按segment顺序合并结果（保持文档顺序）
    for idx in sorted(segment_results_dict.keys()):
        segment_result = segment_results_dict[idx]
        result.segment_results.append(segment_result)

        if segment_result["parsed"]:
            annotations = segment_result["parsed"].get("annotations", [])
            result.combined_annotations.extend(annotations)

    result.total_time = time.time() - overall_start

    # 打印性能统计
    print(f"\n{'='*60}")
    print("并行标注完成")
    print(f"{'='*60}")
    print(f"✅ 总段落数: {total_segments}")
    print(f"✅ 成功段落: {total_segments - len(result.failures)}")
    print(f"❌ 失败段落: {len(result.failures)}")
    print(f"📊 总标注数: {len(result.combined_annotations)}")
    print(f"⏱️  总耗时: {result.total_time:.2f} 秒")

    if result.individual_times:
        avg_time = sum(result.individual_times) / len(result.individual_times)
        max_time = max(result.individual_times)
        sequential_time = sum(result.individual_times) + (total_segments - 1) * 3  # 加上V4的延迟
        speedup = sequential_time / result.total_time if result.total_time > 0 else 1.0

        print(f"⏱️  平均单段耗时: {avg_time:.2f} 秒")
        print(f"⏱️  最长单段耗时: {max_time:.2f} 秒")
        print(f"🚀 预计加速比: {speedup:.2f}x (相比V4顺序处理)")
        print(f"   V4预计耗时: {sequential_time:.2f} 秒")
        print(f"   V6实际耗时: {result.total_time:.2f} 秒")

    if result.failures:
        print(f"\n⚠️  失败详情:")
        for failure in result.failures:
            print(f"   - {failure}")

    return result


def remove_segment_prefixes(annotations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    移除占位符名称中的segment前缀（后处理）

    例如: "seg1_course_name" → "course_name"
    """
    prefix_pattern = re.compile(r'^seg\d+_')
    marker_pattern = re.compile(r'\{\{(seg\d+_[^}]+)\}\}')

    cleaned_annotations = []
    for anno in annotations:
        if isinstance(anno, dict):
            anno_copy = anno.copy()

            for key in ("placeholder_name", "placeholder"):
                if key in anno_copy and isinstance(anno_copy[key], str):
                    anno_copy[key] = prefix_pattern.sub('', anno_copy[key])

            if "result" in anno_copy and isinstance(anno_copy["result"], str):
                anno_copy["result"] = marker_pattern.sub(
                    lambda match: "{{" + prefix_pattern.sub('', match.group(1)) + "}}",
                    anno_copy["result"],
                )

            generated_content = anno_copy.get("generated_content")
            if isinstance(generated_content, dict):
                placeholder = generated_content.get("placeholder")
                if isinstance(placeholder, str):
                    generated_content["placeholder"] = prefix_pattern.sub('', placeholder)

            cleaned_annotations.append(anno_copy)
        else:
            cleaned_annotations.append(anno)

    return cleaned_annotations


if __name__ == "__main__":
    # 简单测试
    print("V6 并行标注器已加载")
    print("使用示例:")
    print("  from docuagent.v6.parallel_annotator import parallel_annotate")
    print("  result = parallel_annotate(md_path=Path('template.md'), max_concurrent=3)")
