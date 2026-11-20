"""
V6 并行内容生成器

核心优化:
- 对每个批次(batch)内的字段进行并行生成
- 批次之间保持顺序（因为存在依赖关系）
- 使用ThreadPoolExecutor + Semaphore控制并发
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Semaphore
from typing import Any, Callable, Dict, List, Optional

from ..v4.content_generation.content_generator import ContentGenerator
from ..v4.content_generation.state import FieldAnalysis, GeneratedField
from ..v4.content_generation.prompts import create_batch_generation_prompt
from ..v4.llm_annotator import (
    GITCODE_GENERATION_MODEL,
    stream_gitcode_chat,
    USE_QWEN,
    HAS_DASHSCOPE,
)
from dashscope import Generation  # 用于批量生成


@dataclass
class ParallelGenerationResult:
    """并行生成结果"""
    generated_content: Dict[str, GeneratedField] = field(default_factory=dict)
    batch_results: List[Dict[str, Any]] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    total_time: float = 0.0
    individual_times: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        if not self.individual_times:
            return {
                "total_fields": len(self.generated_content),
                "failed_fields": len(self.failures),
                "total_time": self.total_time,
                "avg_field_time": 0,
                "max_field_time": 0,
                "speedup_ratio": 1.0,
            }

        avg_time = sum(self.individual_times) / len(self.individual_times)
        max_time = max(self.individual_times)
        sequential_time = sum(self.individual_times)
        speedup = sequential_time / self.total_time if self.total_time > 0 else 1.0

        return {
            "total_fields": len(self.generated_content),
            "failed_fields": len(self.failures),
            "total_time": self.total_time,
            "avg_field_time": avg_time,
            "max_field_time": max_time,
            "sequential_estimate": sequential_time,
            "speedup_ratio": speedup,
        }


def generate_single_field(
    field_idx: int,
    field_analysis: FieldAnalysis,
    user_input: Dict,
    generated_content: Dict[str, str],
    kb_insights: str,
    doc_type: str,
    semaphore: Semaphore,
    output_dir: Optional[Path] = None,
) -> tuple[int, str, Optional[GeneratedField], float, Optional[str]]:
    """
    生成单个字段内容（线程安全）

    Args:
        field_idx: 字段索引
        field_analysis: 字段分析结果
        user_input: 用户输入
        generated_content: 已生成的内容
        kb_insights: 知识库洞察
        doc_type: 文档类型
        semaphore: 并发控制信号量
        output_dir: 输出目录

    Returns:
        (field_idx, placeholder, generated_field, elapsed_time, error_msg)
    """
    placeholder = field_analysis.placeholder
    start_time = time.time()

    try:
        with semaphore:
            print(f"   🔄 [字段 {field_idx}] {placeholder} ({field_analysis.field_type})")

            generator = ContentGenerator(model=GITCODE_GENERATION_MODEL)

            # 生成内容
            generated_field = generator.generate_content(
                field_analysis,
                user_input,
                generated_content,
                kb_insights=kb_insights,  # ✅ 传递知识库洞察
            )

            elapsed_time = time.time() - start_time

            # 保存原始响应
            if output_dir:
                raw_dir = output_dir / "raw_parallel"
                raw_dir.mkdir(parents=True, exist_ok=True)

                raw_file = raw_dir / f"field_{field_idx:03d}_{placeholder}.txt"
                raw_file.write_text(
                    f"字段: {placeholder}\n"
                    f"类型: {field_analysis.field_type}\n"
                    f"耗时: {elapsed_time:.2f}秒\n"
                    f"---\n"
                    f"{generated_field.content}\n",
                    encoding='utf-8'
                )

            return field_idx, placeholder, generated_field, elapsed_time, None

    except Exception as e:
        elapsed_time = time.time() - start_time
        error_msg = str(e)
        print(f"   ❌ [字段 {field_idx}] {placeholder} 失败: {error_msg}")
        return field_idx, placeholder, None, elapsed_time, error_msg


def parallel_generate_batch(
    field_analyses: List[FieldAnalysis],
    user_input: Dict,
    generated_content: Dict[str, str],
    kb_insights: str = "",
    doc_type: str = "",
    output_dir: Optional[Path] = None,
    max_concurrent: int = 5,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> ParallelGenerationResult:
    """
    多线程并行生成一个批次的字段

    Args:
        field_analyses: 字段分析列表
        user_input: 用户输入
        generated_content: 已生成的内容字典
        kb_insights: 知识库洞察
        doc_type: 文档类型
        output_dir: 输出目录
        max_concurrent: 最大并发线程数（默认5）

    Returns:
        ParallelGenerationResult
    """
    print(f"\n{'='*60}")
    print(f"V6 多线程并行内容生成")
    print(f"{'='*60}")
    print(f"\n📊 待生成字段: {len(field_analyses)} 个")
    print(f"🔧 并发线程数: {max_concurrent}")
    print(f"🚀 策略: 多线程并行（每个字段独立API调用）\n")

    result = ParallelGenerationResult()
    start_time = time.time()
    total_fields = len(field_analyses)

    # 如果只有1个字段，直接生成
    if len(field_analyses) <= 1:
        print("⚠️  只有1个字段，无需并行处理\n")
        if field_analyses:
            fa = field_analyses[0]
            semaphore = Semaphore(1)
            _, placeholder, gen_field, elapsed, error = generate_single_field(
                field_idx=0,
                field_analysis=fa,
                user_input=user_input,
                generated_content=generated_content,
                kb_insights=kb_insights,
                doc_type=doc_type,
                semaphore=semaphore,
                output_dir=output_dir,
            )
            if gen_field:
                result.generated_content[placeholder] = gen_field
                generated_content[placeholder] = gen_field.content
            else:
                result.failures.append(f"{placeholder}: {error}")
            result.individual_times.append(elapsed)
            if progress_callback:
                try:
                    progress_callback(1, total_fields or 1, placeholder)
                except Exception as exc:
                    print(f"⚠️ 生成进度回调失败: {exc}")
        result.total_time = time.time() - start_time
        return result

    # 创建信号量控制并发数
    semaphore = Semaphore(max_concurrent)

    # 使用线程池执行并行生成
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        # 提交所有任务
        future_to_idx = {}
        for idx, fa in enumerate(field_analyses):
            future = executor.submit(
                generate_single_field,
                field_idx=idx,
                field_analysis=fa,
                user_input=user_input,
                generated_content=generated_content.copy(),  # 传递副本避免竞争
                kb_insights=kb_insights,
                doc_type=doc_type,
                semaphore=semaphore,
                output_dir=output_dir,
            )
            future_to_idx[future] = idx

        # 收集结果（按完成顺序）
        results_dict = {}
        completed_fields = 0
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                field_idx, placeholder, gen_field, elapsed_time, error_msg = future.result()

                results_dict[field_idx] = {
                    "placeholder": placeholder,
                    "gen_field": gen_field,
                    "elapsed_time": elapsed_time,
                    "error": error_msg,
                }

                result.individual_times.append(elapsed_time)

                if error_msg:
                    result.failures.append(f"{placeholder}: {error_msg}")
                elif gen_field:
                    result.generated_content[placeholder] = gen_field
                    generated_content[placeholder] = gen_field.content
                    print(f"   ✅ {placeholder}: {len(gen_field.content)} 字符 ({elapsed_time:.2f}s)")

                completed_fields += 1
                if progress_callback:
                    try:
                        progress_callback(completed_fields, total_fields or 1, placeholder)
                    except Exception as exc:
                        print(f"⚠️ 生成进度回调失败: {exc}")

            except Exception as e:
                fa = field_analyses[idx]
                placeholder = fa.placeholder if hasattr(fa, 'placeholder') else fa.get('placeholder', f'field_{idx}')
                error_msg = f"线程执行异常: {str(e)}"
                result.failures.append(f"{placeholder}: {error_msg}")
                print(f"   ❌ {placeholder}: {error_msg}")
                completed_fields += 1
                if progress_callback:
                    try:
                        progress_callback(completed_fields, total_fields or 1, placeholder)
                    except Exception as exc:
                        print(f"⚠️ 生成进度回调失败: {exc}")

    result.total_time = time.time() - start_time

    # 打印统计
    print(f"\n{'='*60}")
    print(f"多线程并行生成完成")
    print(f"{'='*60}")
    print(f"✅ 总字段数: {len(field_analyses)}")
    print(f"✅ 成功字段: {len(result.generated_content)}")
    print(f"❌ 失败字段: {len(result.failures)}")
    print(f"⏱️  总耗时: {result.total_time:.2f} 秒")

    if result.individual_times:
        sequential_time = sum(result.individual_times)
        speedup = sequential_time / result.total_time if result.total_time > 0 else 1.0
        avg_time = sum(result.individual_times) / len(result.individual_times)
        max_time = max(result.individual_times)

        print(f"⏱️  平均单字段耗时: {avg_time:.2f} 秒")
        print(f"⏱️  最长单字段耗时: {max_time:.2f} 秒")
        print(f"🚀 加速比: {speedup:.2f}x")
        print(f"   顺序预计耗时: {sequential_time:.2f} 秒")
        print(f"   并行实际耗时: {result.total_time:.2f} 秒")

    return result


def parallel_generate_all_batches(
    field_batches: List[List[FieldAnalysis]],
    user_input: Dict,
    kb_insights: str = "",
    doc_type: str = "",
    output_dir: Optional[Path] = None,
    max_concurrent: int = 5,
) -> ParallelGenerationResult:
    """
    并行生成所有批次的字段（批次间顺序执行，批次内并行）

    Args:
        field_batches: 字段批次列表（每个批次是一个字段列表）
        user_input: 用户输入
        kb_insights: 知识库洞察
        doc_type: 文档类型
        output_dir: 输出目录
        max_concurrent: 最大并发数

    Returns:
        ParallelGenerationResult
    """
    print(f"\n{'='*60}")
    print(f"V6 多线程并行内容生成 - 多批次处理")
    print(f"{'='*60}")
    print(f"\n📦 总批次数: {len(field_batches)}")
    total_fields = sum(len(batch) for batch in field_batches)
    print(f"📊 总字段数: {total_fields}")
    print(f"🔧 并发线程数: {max_concurrent}\n")

    all_results = ParallelGenerationResult()
    generated_content_dict = {}
    overall_start = time.time()

    for batch_idx, batch_fields in enumerate(field_batches, start=1):
        print(f"\n{'─'*60}")
        print(f"📦 批次 {batch_idx}/{len(field_batches)}: {len(batch_fields)} 个字段")
        print(f"{'─'*60}")

        batch_result = parallel_generate_batch(
            field_analyses=batch_fields,
            user_input=user_input,
            generated_content=generated_content_dict,
            kb_insights=kb_insights,
            doc_type=doc_type,
            output_dir=output_dir / f"batch_{batch_idx:02d}" if output_dir else None,
            max_concurrent=max_concurrent,
        )

        # 合并结果
        all_results.generated_content.update(batch_result.generated_content)
        all_results.failures.extend(batch_result.failures)
        all_results.individual_times.extend(batch_result.individual_times)
        all_results.batch_results.append({
            "batch_index": batch_idx,
            "fields_count": len(batch_fields),
            "success_count": len(batch_result.generated_content),
            "failed_count": len(batch_result.failures),
            "time": batch_result.total_time,
        })

        # 更新已生成内容 - 提取GeneratedField的content字符串
        for placeholder, gen_field in batch_result.generated_content.items():
            generated_content_dict[placeholder] = gen_field.content

        print(f"\n   📈 当前进度: {len(all_results.generated_content)}/{total_fields} 字段完成")

    all_results.total_time = time.time() - overall_start

    # 最终统计
    print(f"\n{'='*60}")
    print(f"✅ 所有批次完成！")
    print(f"{'='*60}")
    print(f"\n📊 最终统计:")
    print(f"   总字段数: {total_fields}")
    print(f"   成功生成: {len(all_results.generated_content)}")
    print(f"   失败字段: {len(all_results.failures)}")
    print(f"   总批次数: {len(field_batches)}")
    print(f"   总耗时: {all_results.total_time:.2f} 秒 ({all_results.total_time/60:.1f} 分钟)")

    if all_results.individual_times:
        stats = all_results.to_dict()
        print(f"\n🚀 性能提升（{max_concurrent}线程并行）:")
        print(f"   顺序预计耗时: {stats['sequential_estimate']:.2f} 秒")
        print(f"   并行实际耗时: {all_results.total_time:.2f} 秒")
        print(f"   加速比: {stats['speedup_ratio']:.2f}x")

    if all_results.failures:
        print(f"\n⚠️  失败字段:")
        for failure in all_results.failures:
            print(f"   - {failure}")

    return all_results
