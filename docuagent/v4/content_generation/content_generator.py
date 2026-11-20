"""
内容生成器 - 根据字段分析结果生成实际内容
"""

from __future__ import annotations

import json
import os
import time
import re
from datetime import datetime
from typing import Dict, List, Optional

from ..llm_annotator import (
    stream_gitcode_chat,
    GITCODE_GENERATION_MODEL,
    _bump_stat,
    _add_metric,
    USE_QWEN,
    HAS_DASHSCOPE,
    USE_FIREWORKS,
    HAS_FIREWORKS,
    USE_GROQ,
)
from .prompts import (
    create_content_generation_prompt,
    create_quality_check_prompt,
    create_batch_generation_prompt,
)
from .state import FieldAnalysis, GeneratedField
from .field_constraints import FieldConstraintValidator

TEACHER_KEYWORDS_EN = ("teacher", "teacher_name", "instructor", "lecturer", "mentor", "tutor")
TEACHER_KEYWORDS_CN = ("教师", "讲师", "导师", "任课", "授课")


class ContentGenerator:
    """内容生成器"""
    
    def __init__(
        self,
        model: str = GITCODE_GENERATION_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 16000,  # 提高到 16k 以支持批量生成
        log_dir: str = "logs/llm_prompts",  # 日志目录
    ):
        self.model = model
        self.temperature = temperature
        # Kimi 模型的 max_tokens 限制为 32k
        if "kimi" in model.lower():
            self.max_tokens = min(max_tokens, 32000)
        elif "llama" in model.lower():
            self.max_tokens = min(max_tokens, 8192)
        else:
            self.max_tokens = max_tokens

        # 📝 创建日志目录
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.current_log_file = os.path.join(
            log_dir,
            f"generation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        print(f"📝 LLM交互日志将保存到: {self.current_log_file}")
    
    def generate_content(
        self,
        field_analysis: FieldAnalysis,
        user_input: Dict,
        generated_content: Dict[str, str],
        kb_insights: str = "",  # 支持知识库洞察
    ) -> GeneratedField:
        """
        生成单个字段的内容
        
        Args:
            field_analysis: 字段分析结果
            user_input: 用户输入
            generated_content: 已生成的其他内容
            
        Returns:
            GeneratedField: 生成的字段内容
        """
        print(f"\n🔍 [DEBUG] ContentGenerator.generate_content 被调用")
        print(f"   placeholder: {field_analysis.placeholder}")
        print(f"   kb_insights长度: {len(kb_insights)} 字符")
        print(f"   field_analysis.annotation存在: {field_analysis.annotation is not None}")
        if field_analysis.annotation:
            print(f"   annotation.marker存在: {'marker' in field_analysis.annotation}")
        
        placeholder = field_analysis.placeholder
        
        # 特殊处理：优先尝试直接映射（章节名、课程名等）
        mapped = self._direct_mapping(placeholder, user_input)
        if mapped:
            print(f"   ✅ 使用直接映射")
            mapped = self._post_process_content(mapped, field_analysis)
            return self._create_generated_field(placeholder, mapped, 0)
        
        # 特殊处理：时间/节次等格式化（避免长篇幅与编造日期）
        if field_analysis.generation_strategy == "format_conversion" or field_analysis.field_type == "time_info":
            print(f"   ✅ 使用时间格式化")
            content = self._generate_time_info(field_analysis, user_input)
            return self._create_generated_field(placeholder, self._post_process_content(content, field_analysis), 0)
        
        print(f"   🔍 准备调用 create_content_generation_prompt...")

        # 🔥 使用字段级RAG检索相关知识(替代全量知识库)
        field_specific_knowledge = self._get_field_knowledge(
            field_analysis.content_type,
            field_analysis.placeholder,
            user_input.get("doc_type", "lesson_plan")
        )

        # 创建 prompt
        prompt = create_content_generation_prompt(
            field_analysis.__dict__,
            user_input,
            generated_content,
            kb_insights=field_specific_knowledge,  # ✅ 使用字段级知识而非全量知识库
        )

        # 📝 记录Prompt到日志文件
        self._log_prompt_and_response(placeholder, prompt, None, "PROMPT")

        # 调用 LLM 生成
        print(f"   🤖 生成字段: {placeholder} ({field_analysis.content_type})")
        content = self._call_llm(prompt)

        # 📝 记录LLM响应到日志文件
        self._log_prompt_and_response(placeholder, prompt, content, "RESPONSE")
        
        if not content:
            print(f"   ⚠️ 生成失败，使用默认占位符")
            content = f"[待填写: {field_analysis.content_type}]"
        
        # 后处理
        content = self._post_process_content(content, field_analysis)
        
        return self._create_generated_field(placeholder, content, 0)
    
    def _direct_mapping(self, placeholder: str, user_input: Dict) -> Optional[str]:
        """直接从用户输入映射"""
        # 尝试从 basic_info 获取
        basic_info = user_input.get("basic_info", {})
        pl = (placeholder or "").lower()
        if pl.startswith("section_name") or pl.startswith("teaching_section") or pl in ("section", "teaching_section", "teaching_section_value"):
            pa = user_input.get("prompt_analysis", {}) or {}
            sec = basic_info.get("chapter_section") or pa.get("chapter_section") or basic_info.get("course_name") or pa.get("topic")
            if sec:
                return str(sec)
        if placeholder in basic_info:
            return str(basic_info[placeholder])
        
        # 尝试智能匹配
        mapping = {
            "course_name": "basic_info.course_name",
            "teacher_name": "basic_info.teacher_name",
            "teaching_unit": "basic_info.teaching_unit",
            "class_hours": "basic_info.class_hours",
            "credits": "basic_info.credits",
        }
        
        if placeholder in mapping:
            parts = mapping[placeholder].split(".")
            value = user_input
            for part in parts:
                value = value.get(part, {})
                if not isinstance(value, dict):
                    return str(value)

        return None
    
    def _generate_time_info(self, field_analysis: FieldAnalysis, user_input: Dict) -> str:
        """根据用户输入生成简短的时间/节次描述，避免无根据的日期扩展。"""
        pa = user_input.get("prompt_analysis", {}) or {}
        ch = None
        try:
            ch = int(user_input.get("basic_info", {}).get("class_hours") or pa.get("class_hours") or 0)
        except Exception:
            ch = 0
        ch = ch or 2
        scope = (user_input.get("teaching_context", {}).get("lesson_scope") or pa.get("lesson_scope") or "single").lower()
        is_single = scope in ["single", "one", "单节", "一次"] or ch <= 2
        label = (field_analysis.content_type or "授课时间").strip()
        if any(k in label for k in ["节次", "period", "节"]):
            return f"单次授课（约{ch}课时）"
        if any(k in label for k in ["时间", "time", "日期", "date", "周", "weekday", "week"]):
            return f"{('单次授课，' if is_single else '')}共 {ch} 课时"
        # 其他 time_info 统一简化
        return f"{('单次授课，' if is_single else '')}{ch} 课时"
    
    def _call_llm(self, prompt: str) -> str:
        """调用 LLM（Fireworks、Qwen 或 Kimi）"""
        # 根据使用的模型调整system message
        if USE_FIREWORKS and HAS_FIREWORKS:
            system_content = "你是Qwen2.5-32B，由阿里云Qwen团队开发的强大语言模型。你是专业的教案内容生成专家，擅长根据上下文生成高质量、符合要求的教学内容。"
        elif USE_QWEN and HAS_DASHSCOPE:
            system_content = "你是通义千问，由阿里云提供的大语言模型。你是专业的教案内容生成专家，擅长根据上下文生成高质量、符合要求的教学内容。"
        elif USE_GROQ:
            system_content = "你是Groq加速引擎，擅长快速生成高质量、符合要求的教学内容。"
        else:
            system_content = "你是 Kimi，由 Moonshot AI 提供的人工智能助手。你是专业的教案内容生成专家。请运用你的推理能力，根据上下文生成高质量、符合要求的教学内容。"

        messages = [
            {
                "role": "system",
                "content": system_content
            },
            {
                "role": "user",
                "content": prompt,
            }
        ]
        
        try:
            content = stream_gitcode_chat(
                messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return content.strip()
        except Exception as e:
            print(f"   ❌ LLM 调用失败: {e}")
            # 失败计数
            try:
                _bump_stat("llm_call_failures", 1)
            except Exception:
                pass
            return ""
    
    def _post_process_content(self, content: str, field_analysis: FieldAnalysis) -> str:
        """
        后处理生成的内容（最小化处理，只做基本清理）

        🔥 设计原则：
        - 只移除LLM生成的无关标签和格式标记
        - 不截断、不提取、不强制限长
        - 完全交给知识库和LLM本身控制长度
        - 统一格式：单倍行距、左对齐、无首行缩进、首尾无空格
        """
        # 1. 移除开头的字段标签（例如"教学目标：xxx" → "xxx"）
        content = re.sub(
            rf"^(?:{re.escape(field_analysis.content_type)}[:：]\s*)+",
            "",
            content,
            flags=re.IGNORECASE,
        )

        # 2. 移除通用前缀标签（例如"课程类别：""使用教材："）
        content = re.sub(r"^(?:[\u4e00-\u9fa5A-Za-z（）()\-\s]{1,12}[:：]\s*)+", "", content, count=1)

        # 3. 移除 Markdown 代码块标记
        content = re.sub(r"^```.*?\n", "", content)
        content = re.sub(r"\n```$", "", content)

        # 4. 移除 <think> reasoning tags (来自 PackyAPI GPT-5.1)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
        content = re.sub(r"</?think>", "", content)

        # 5. 格式规范化：移除首行缩进、多余空格、统一换行
        content = self._normalize_format(content)

        # 6. 如果是列表风格，规范化列表格式
        if field_analysis.style == "structured_list":
            content = self._normalize_list(content)

        # ✅ 完成！不做任何截断或提取
        return content

    def _normalize_format(self, content: str) -> str:
        """
        格式规范化：
        - 移除首行缩进（全角空格、半角空格、Tab）
        - 移除行首行尾多余空格
        - 统一为单倍行距（\n）
        - 左对齐
        """
        if not content:
            return ""

        # 分行处理
        lines = content.split('\n')
        normalized_lines = []

        for line in lines:
            # 移除行首的缩进（全角空格、半角空格、Tab）
            line = re.sub(r'^[\s\u3000\t]+', '', line)

            # 移除行尾空格
            line = line.rstrip()

            # 保留有内容的行（空行也保留，用于段落分隔）
            normalized_lines.append(line)

        # 合并行，使用单个换行符（单倍行距）
        content = '\n'.join(normalized_lines)

        # 移除开头和结尾的空行
        content = content.strip()

        # 压缩连续的空行为单个空行（保持段落间隔）
        content = re.sub(r'\n{3,}', '\n\n', content)

        return content
    
    def _normalize_list(self, content: str) -> str:
        """规范化列表格式"""
        # 将同一行内的“1. 2. 3.”拆分为多行
        def _split_inline_nums(text: str) -> str:
            # 在句边界或空白后面出现的 N. 前插入换行
            return re.sub(r"(^|[\s；;。.!?、，,])(\d+)\.\s+", lambda m: f"{m.group(1)}\n{m.group(2)}. ", text)
        content = _split_inline_nums(content or "").strip()
        lines = content.split("\n")
        normalized_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
        
            # 如果没有编号，添加编号
            if not re.match(r"^\d+\.", line) and not re.match(r"^[-•]\s", line):
                normalized_lines.append(f"{len(normalized_lines) + 1}. {line}")
            else:
                normalized_lines.append(line)
        
        return "\n".join(normalized_lines)

    def _trim_to_length(self, text: str, max_len: int) -> str:
        """在不破坏语义的情况下裁剪到最大长度（优先句末标点）。"""
        if len(text) <= max_len:
            return text
        cut = text[:max_len]
        # 优先在中文句末或常见标点处截断
        for sep in ["。", "！", "？", ".", "!", "?", "；", ";", "\n"]:
            idx = cut.rfind(sep)
            if idx >= max_len * 0.7:  # 只在后段截断，避免过短
                return cut[: idx + 1].rstrip()
        return cut.rstrip()
    
    def _create_generated_field(
        self, placeholder: str, content: str, retry_count: int, passed_checks: bool = True
    ) -> GeneratedField:
        """创建 GeneratedField 对象"""
        return GeneratedField(
            placeholder=placeholder,
            content=content,
            char_count=len(content),
            word_count=len(content.split()),
            item_count=len([l for l in content.split("\n") if l.strip()]),
            generation_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            retry_count=retry_count,
            passed_checks=passed_checks,  # 🔥 新增：设置验证状态
        )

    def _looks_like_teacher_field(self, field_analysis: FieldAnalysis) -> bool:
        placeholder = (field_analysis.placeholder or "").lower()
        content_type = (field_analysis.content_type or "").lower()
        annotation = field_analysis.annotation or {}
        reason = str(annotation.get("reason") or "")
        result = str(annotation.get("result") or "")
        combined_en = " ".join(
            [
                placeholder,
                content_type,
                reason.lower(),
                result.lower(),
            ]
        )
        if any(key in combined_en for key in TEACHER_KEYWORDS_EN):
            return True
        combined_cn = reason + result + (field_analysis.content_type or "") + (field_analysis.placeholder or "")
        return any(key in combined_cn for key in TEACHER_KEYWORDS_CN)

    def _shorten_teacher_value(self, text: str) -> str:
        s = (text or "").strip()
        parts = re.split(r"[，,。；;\n]", s, maxsplit=1)
        if parts and parts[0].strip():
            s = parts[0].strip()
        m = re.search(r"([\u4e00-\u9fa5]{2,4})(?:教授|副教授|老师|博士)?", s)
        if m:
            s = m.group(0)
        return s[:50].rstrip()
    
    def check_quality(self, generated_field: GeneratedField, field_analysis: FieldAnalysis) -> bool:
        """
        检查生成内容的质量
        
        Args:
            generated_field: 生成的字段
            field_analysis: 字段分析结果
            
        Returns:
            bool: 是否通过质量检查
        """
        content = generated_field.content
        length_req = field_analysis.length_requirement
        
        # 基本检查
        min_chars = length_req.get("min_chars", 0)
        max_chars = length_req.get("max_chars", 10000)
        
        # 1. 长度检查
        if len(content) < min_chars * 0.8:  # 允许 20% 的偏差
            print(f"   ⚠️ 内容过短: {len(content)} < {min_chars}")
            return False
        
        if len(content) > max_chars * 1.1:  # 限制 10% 的超长
            print(f"   ⚠️ 内容过长: {len(content)} > {max_chars}")
            return False
        
        # 2. 内容检查：不能是纯占位符
        if content.startswith("[") and content.endswith("]"):
            return False
        
        # 3. 列表项数量检查
        if field_analysis.style == "structured_list":
            target_items = length_req.get("target_items", 3)
            actual_items = len([l for l in content.split("\n") if l.strip()])
            
            if actual_items < target_items - 1:
                print(f"   ⚠️ 列表项不足: {actual_items} < {target_items}")
                return False
        
        return True
    
    def batch_generate(
        self,
        field_analyses: List[FieldAnalysis],
        user_input: Dict,
        generated_content: Dict[str, str],
        kb_insights: str = "",
        doc_type: str = "task_proposal",  # 新增：文档类型
        max_retries: int = 2,  # 新增：最大重试次数
    ) -> Dict[str, GeneratedField]:
        """
        批量生成多个字段（真正的批量实现，支持验证和重试）

        Args:
            field_analyses: 多个字段分析
            user_input: 用户输入
            generated_content: 已生成内容
            kb_insights: 知识库洞察（已弃用，现使用字段级RAG）
            doc_type: 文档类型（用于约束验证）
            max_retries: 最大重试次数

        Returns:
            Dict[str, GeneratedField]: 生成的字段字典
        """
        if not field_analyses:
            return {}

        # 🔥 去重：按placeholder去重字段列表
        seen_placeholders = set()
        unique_field_analyses = []
        for analysis in field_analyses:
            if analysis.placeholder not in seen_placeholders:
                seen_placeholders.add(analysis.placeholder)
                unique_field_analyses.append(analysis)
            else:
                print(f"   ⚠️  跳过重复字段: {analysis.placeholder}")

        field_analyses = unique_field_analyses

        # 如果只有一个字段，使用单个生成
        if len(field_analyses) == 1:
            # ✅ 使用字段级RAG
            field = self.generate_content(field_analyses[0], user_input, generated_content, kb_insights="")
            return {field_analyses[0].placeholder: field}

        print(f"\n   🚀 批量生成 {len(field_analyses)} 个字段（去重后）...")

        # 初始化约束验证器
        validator = FieldConstraintValidator(doc_type)

        # 准备批量生成的字段信息
        field_analyses_dict = [analysis.__dict__ for analysis in field_analyses]

        # 🔥 支持重试的生成循环
        # 🔥 在循环外初始化results，累积成功的字段
        all_results = {}

        for retry_count in range(max_retries + 1):
            if retry_count > 0:
                print(f"\n   🔄 第 {retry_count} 次重试...")

            # 🔥 为批量生成收集字段级知识库（替代全量知识库）
            batch_kb_insights = self._collect_batch_field_knowledge(
                field_analyses,
                user_input.get("doc_type", "lesson_plan"),
                top_k=3
            )

            # 创建批量生成 prompt（注入字段级知识库和强约束）
            prompt = create_batch_generation_prompt(
                field_analyses_dict,
                user_input,
                generated_content,
                kb_insights=batch_kb_insights,  # ✅ 使用字段级知识库
                doc_type=doc_type,  # ✅ 传递文档类型
                use_enhanced_constraints=True,  # ✅ 使用增强约束
            )

            # 📝 记录批量生成的Prompt到日志文件
            batch_placeholder = f"BATCH_{retry_count+1}_{len(field_analyses)}_fields"
            self._log_prompt_and_response(batch_placeholder, prompt, None, "PROMPT")

            # 调用 LLM 批量生成
            try:
                t0 = time.perf_counter()
                response = self._call_llm_batch(prompt, len(field_analyses))
                t1 = time.perf_counter()
                dt = round(t1 - t0, 3)
                print(f"   ⏱️ 批次耗时: {dt} s")
                try:
                    _bump_stat("batch_calls", 1)
                    _add_metric("batch_time_sec_total", dt)
                except Exception:
                    pass

                # 📝 记录批量生成的Response到日志文件
                self._log_prompt_and_response(batch_placeholder, prompt, response, "RESPONSE")

                # 解析 JSON 响应
                generated_dict = self._parse_batch_response(response, field_analyses)

                # 转换为 GeneratedField 对象（先做与单字段一致的后处理与裁剪）
                results = {}  # 本次循环的结果
                failed_fields = []  # 记录验证失败的字段

                for analysis in field_analyses:
                    placeholder = analysis.placeholder
                    if placeholder in generated_dict:
                        raw = generated_dict[placeholder]
                        content = self._post_process_content(str(raw or ""), analysis)

                        # 🔥 新增：验证字段内容
                        validation_result = validator.validate(placeholder, content)

                        if validation_result["passed"]:
                            results[placeholder] = self._create_generated_field(placeholder, content, 0, passed_checks=True)
                            print(f"   ✅ {placeholder}: {len(content)} 字符")
                        else:
                            # 验证失败 - 设置passed_checks=False
                            results[placeholder] = self._create_generated_field(placeholder, content, 0, passed_checks=False)
                            failed_fields.append({
                                "placeholder": placeholder,
                                "issues": validation_result["issues"],
                                "content_length": len(content)
                            })
                            print(f"   ⚠️  {placeholder}: {len(content)} 字符 - 验证失败")
                            for issue in validation_result["issues"]:
                                print(f"       - {issue}")
                    else:
                        # 如果批量生成失败某个字段，使用单独生成作为后备
                        print(f"   ⚠️  {placeholder} 批量生成缺失，回退单字段生成")
                        try:
                            _bump_stat("single_fallbacks", 1)
                        except Exception:
                            pass
                        # ✅ 修复：传递kb_insights参数
                        field = self.generate_content(analysis, user_input, generated_content, kb_insights=kb_insights)
                        results[placeholder] = field

                # 检查是否有验证失败的字段
                if not failed_fields:
                    # 全部通过，合并到总结果并返回
                    all_results.update(results)
                    print(f"   ✅ 批次完成: 共生成 {sum(len(f.content) for f in all_results.values())} 字符")
                    return all_results
                elif retry_count < max_retries:
                    # 🔥 重试前先保存成功的字段到all_results
                    failed_placeholders = [f["placeholder"] for f in failed_fields]
                    for placeholder, field in results.items():
                        if placeholder not in failed_placeholders:
                            all_results[placeholder] = field
                            print(f"   💾 保存成功字段: {placeholder} ({len(field.content)}字符)")

                    # 还有重试机会，准备重新生成失败的字段
                    print(f"\n   ⚠️  {len(failed_fields)} 个字段验证失败，准备重新生成:")
                    for failed in failed_fields:
                        print(f"       - {failed['placeholder']} ({failed['content_length']}字符)")

                    # 只重新生成失败的字段
                    field_analyses_dict = [
                        a.__dict__ for a in field_analyses if a.placeholder in failed_placeholders
                    ]
                    field_analyses = [a for a in field_analyses if a.placeholder in failed_placeholders]
                    # 🔥 关键：continue到下一次循环进行重试
                    continue
                else:
                    # 已达最大重试次数，合并当前结果并返回
                    all_results.update(results)
                    print(f"\n   ⚠️  已达最大重试次数，使用当前结果")
                    print(f"   ✅ 批次完成: 共生成 {sum(len(f.content) for f in all_results.values())} 字符")
                    return all_results

            except Exception as e:
                print(f"   ❌ 批量生成失败: {e}，回退到逐个生成")
                # 回退到逐个生成
                results = {}
                for analysis in field_analyses:
                    # ✅ 修复：传递kb_insights参数
                    field = self.generate_content(analysis, user_input, generated_content, kb_insights=kb_insights)
                    results[analysis.placeholder] = field
                    generated_content[analysis.placeholder] = field.content
                # 合并到总结果
                all_results.update(results)
            return all_results
    
    def _call_llm_batch(self, prompt: str, num_fields: int) -> str:
        """调用 LLM 批量生成（使用更大的 max_tokens）"""
        # 根据使用的模型调整system message
        if USE_FIREWORKS and HAS_FIREWORKS:
            system_content = "你是Qwen2.5-32B，由阿里云Qwen团队开发的强大语言模型。你是专业的教案内容生成专家，擅长批量生成高质量、内容连贯的教学内容。"
        elif USE_QWEN and HAS_DASHSCOPE:
            system_content = "你是通义千问，由阿里云提供的大语言模型。你是专业的教案内容生成专家，擅长批量生成高质量、内容连贯的教学内容。"
        elif USE_GROQ:
            system_content = "你是Groq加速引擎，擅长批量生成高质量、内容连贯的教学内容。"
        else:
            system_content = "你是 Kimi，由 Moonshot AI 提供的人工智能助手。你是专业的教案内容生成专家。请运用你的推理能力，批量生成高质量、内容连贯的教学内容。"

        messages = [
            {
                "role": "system",
                "content": system_content
            },
            {
                "role": "user",
                "content": prompt,
            }
        ]
        
        # 根据字段数量动态调整 max_tokens
        estimated_tokens = min(num_fields * 2000, self.max_tokens)
        
        try:
            content = stream_gitcode_chat(
                messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=estimated_tokens,
            )
            return content.strip()
        except Exception as e:
            print(f"   ❌ LLM 批量调用失败: {e}")
            raise
    
    def _parse_batch_response(self, response: str, field_analyses: List[FieldAnalysis]) -> Dict[str, str]:
        """解析批量生成的 JSON 响应"""
        # 移除可能的 markdown 代码块标记
        response = re.sub(r"^```json\s*", "", response, flags=re.IGNORECASE)
        response = re.sub(r"^```\s*", "", response)
        response = re.sub(r"\s*```$", "", response)
        response = response.strip()
        
        try:
            # 尝试解析 JSON
            result_dict = json.loads(response)
            
            # 验证所有字段都存在
            expected_placeholders = {analysis.placeholder for analysis in field_analyses}
            actual_placeholders = set(result_dict.keys())
            
            missing = expected_placeholders - actual_placeholders
            if missing:
                print(f"   ⚠️ 缺少字段: {missing}")
            
            # 后处理每个字段的内容
            for placeholder, content in result_dict.items():
                if isinstance(content, str):
                    result_dict[placeholder] = content.strip()
            
            return result_dict
            
        except json.JSONDecodeError as e:
            print(f"   ALERT JSON 解析失败: {e}")
            try:
                _bump_stat("batch_json_parse_failures", 1)
            except Exception:
                pass
            print(f"   原始响应: {response[:200]}...")
            
            # 尝试从响应中提取内容（如果 LLM 没有严格遵循 JSON 格式）
            return self._extract_fields_from_text(response, field_analyses)
    
    def _extract_fields_from_text(self, text: str, field_analyses: List[FieldAnalysis]) -> Dict[str, str]:
        """从文本中提取字段内容（后备方法）"""
        result = {}
        
        for analysis in field_analyses:
            placeholder = analysis.placeholder
            content_type = analysis.content_type
            
            # 尝试匹配字段内容
            patterns = [
                rf"{re.escape(placeholder)}[""\s]*[:：][\s\n]*(.+?)(?=\n\n|\n[a-zA-Z_]+[:：]|$)",
                rf"{re.escape(content_type)}[""\s]*[:：][\s\n]*(.+?)(?=\n\n|\n[^\n]+[:：]|$)",
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.DOTALL)
                if match:
                    result[placeholder] = match.group(1).strip()
                    break

        return result

    def _get_field_knowledge(
        self,
        content_type: str,
        placeholder: str,
        doc_type: str = "lesson_plan",
        top_k: int = 3
    ) -> str:
        """
        获取字段相关的知识库经验(使用字段级RAG)

        Args:
            content_type: 字段类型
            placeholder: 占位符
            doc_type: 文档类型
            top_k: 检索top-k条经验

        Returns:
            格式化的字段知识
        """
        try:
            # 导入字段RAG模块
            import sys
            from pathlib import Path

            # 添加v5路径到sys.path
            v5_path = Path(__file__).parent.parent.parent / "v5"
            if str(v5_path) not in sys.path:
                sys.path.insert(0, str(v5_path))

            from field_rag import get_field_knowledge

            # 检索字段知识
            knowledge = get_field_knowledge(
                field_name=content_type,
                placeholder=placeholder,
                doc_type=doc_type,
                top_k=top_k
            )

            if knowledge:
                print(f"   📚 检索到{content_type}相关知识: {len(knowledge)}字符")
            else:
                print(f"   ℹ️  未找到{content_type}相关知识,使用通用生成")

            return knowledge

        except Exception as e:
            print(f"   ⚠️  字段RAG检索失败: {e}")
            return ""

    def _collect_batch_field_knowledge(
        self,
        field_analyses: List[FieldAnalysis],
        doc_type: str = "lesson_plan",
        top_k: int = 3
    ) -> str:
        """
        为批量生成收集所有字段的相关知识库经验

        Args:
            field_analyses: 字段分析列表
            doc_type: 文档类型
            top_k: 每个字段检索top-k条经验

        Returns:
            合并后的知识库提示文本
        """
        try:
            # 导入字段RAG模块
            import sys
            from pathlib import Path

            # 添加v5路径到sys.path
            v5_path = Path(__file__).parent.parent.parent / "v5"
            if str(v5_path) not in sys.path:
                sys.path.insert(0, str(v5_path))

            from field_rag import FieldRAG

            rag = FieldRAG(doc_type=doc_type)

            # 收集所有相关经验（去重）
            all_prompts_set = set()  # 使用集合去重

            for analysis in field_analyses:
                # 提取字段名
                field_name = rag.extract_field_name(
                    analysis.content_type,
                    analysis.placeholder
                )

                # 检索相关经验
                field_prompts = rag.search_field_experiences(
                    field_name,
                    top_k=top_k
                )

                # 添加到集合（自动去重）
                for prompt in field_prompts:
                    all_prompts_set.add(prompt)

            # 转换为列表并格式化
            if not all_prompts_set:
                print(f"   ℹ️  批量生成: 未找到相关知识")
                return ""

            lines = [
                "\n## 📚 知识库提示（基于历史经验的改进建议）",
                ""
            ]

            for idx, prompt in enumerate(sorted(all_prompts_set), 1):
                lines.append(f"{idx}. {prompt}")

            lines.append("")

            result = "\n".join(lines)
            print(f"   📚 批量生成: 检索到{len(all_prompts_set)}条去重后的相关知识")

            return result

        except Exception as e:
            print(f"   ⚠️  批量字段RAG检索失败: {e}")
            return ""

    def _log_prompt_and_response(
        self,
        placeholder: str,
        prompt: str,
        response: Optional[str],
        log_type: str  # "PROMPT" or "RESPONSE"
    ):
        """记录Prompt和Response到日志文件"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with open(self.current_log_file, 'a', encoding='utf-8') as f:
                if log_type == "PROMPT":
                    f.write("\n" + "=" * 100 + "\n")
                    f.write(f"[{timestamp}] 字段: {placeholder}\n")
                    f.write("=" * 100 + "\n")
                    f.write("📤 发送给LLM的Prompt:\n")
                    f.write("-" * 100 + "\n")
                    f.write(prompt)
                    f.write("\n" + "-" * 100 + "\n")

                elif log_type == "RESPONSE" and response:
                    f.write(f"\n📥 LLM的响应:\n")
                    f.write("-" * 100 + "\n")
                    f.write(response)
                    f.write("\n" + "-" * 100 + "\n")
                    f.write(f"响应长度: {len(response)} 字符\n")
                    f.write("=" * 100 + "\n\n")

        except Exception as e:
            print(f"⚠️ 日志记录失败: {e}")
