"""
错误分析与反思模块

功能：
1. 分析 VLM 检查结果
2. 判断错误来源（标注器 vs 生成器）
3. 生成改进建议
4. 返回结构化分析结果供知识库存储
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import dashscope
    from dashscope import Generation
    from config.settings import DASHSCOPE_API_KEY
    dashscope.api_key = DASHSCOPE_API_KEY
    HAS_DASHSCOPE = True
except ImportError:
    HAS_DASHSCOPE = False

# 优先使用通义千问，备选 Kimi API
USE_QWEN = bool(os.getenv("USE_QWEN_FOR_REFLECTION", "true").lower() in ["true", "1", "yes"])
REFLECTION_MODEL = os.getenv("REFLECTION_MODEL", "qwen-plus" if USE_QWEN else "kimi-k2-turbo-preview")
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
KIMI_API_BASE = os.getenv("KIMI_API_BASE", "https://api.moonshot.cn/v1")


def _call_reflection_llm(prompt: str, temperature: float = 0.3) -> str:
    """
    调用 LLM 进行错误分析和反思

    Args:
        prompt: 分析提示词
        temperature: 采样温度

    Returns:
        LLM 响应文本
    """
    # 优先使用通义千问
    if USE_QWEN and HAS_DASHSCOPE:
        try:
            system_msg = "你是一个专业的文档质量分析专家，擅长诊断模板标注和内容生成过程中的问题。"
            full_prompt = f"{system_msg}\n\n{prompt}"

            response = Generation.call(
                model=REFLECTION_MODEL,
                prompt=full_prompt,
                temperature=temperature,
                result_format='message',
                max_tokens=4096,
            )

            if response.status_code == 200:
                return response.output.choices[0].message.content or ""
            else:
                raise RuntimeError(f"通义千问API调用失败: {response.message}")
        except Exception as e:
            print(f"⚠️  通义千问调用失败: {e}")
            # 如果通义千问失败，尝试使用Kimi
            if KIMI_API_KEY and HAS_OPENAI:
                print("🔄 尝试使用Kimi API...")
            else:
                raise RuntimeError(f"通义千问调用失败且无备选方案: {e}")

    # 使用 Kimi API
    if not HAS_OPENAI:
        raise RuntimeError("openai 包未安装。请运行：pip install openai")

    if not KIMI_API_KEY:
        raise RuntimeError(
            "KIMI_API_KEY 未设置。\n"
            "请设置环境变量：export KIMI_API_KEY='your_key'\n"
            "或者系统将自动使用通义千问（已设置DASHSCOPE_API_KEY）"
        )

    client = OpenAI(
        api_key=KIMI_API_KEY,
        base_url=KIMI_API_BASE
    )

    try:
        response = client.chat.completions.create(
            model="kimi-k2-turbo-preview",
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的文档质量分析专家，擅长诊断模板标注和内容生成过程中的问题。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=temperature,
            max_tokens=4096,
        )

        return response.choices[0].message.content or ""

    except Exception as e:
        raise RuntimeError(f"Kimi API 调用失败: {e}")


def _build_reflection_prompt(
    vlm_result: Dict[str, Any],
    user_requirement: str,
    annotation_summary: Optional[Dict[str, Any]] = None,
    generation_summary: Optional[Dict[str, Any]] = None,
) -> str:
    """
    构建错误分析提示词

    Args:
        vlm_result: VLM 检查结果
        user_requirement: 用户需求描述
        annotation_summary: 标注阶段摘要（可选，用于辅助诊断）
        generation_summary: 生成阶段摘要（可选，用于辅助诊断）

    Returns:
        格式化的分析提示词
    """
    issues = vlm_result.get("issues", [])
    summary = vlm_result.get("summary", {})

    prompt_parts = [
        "# 任务：文档质量问题分析",
        "",
        "## VLM 检查结果",
        "",
        f"**整体严重程度**: {summary.get('severity', 'unknown')}",
        f"**整体评价**: {summary.get('notes', '无')}",
        "",
        "**发现的问题**:",
    ]

    for idx, issue in enumerate(issues, start=1):
        prompt_parts.append(
            f"{idx}. [{issue.get('severity', 'unknown')}] "
            f"{issue.get('kind', 'unknown')} @ {issue.get('location', '未知位置')}: "
            f"{issue.get('detail', '无详情')}"
        )

    prompt_parts.extend([
        "",
        "## 用户需求",
        user_requirement or "无特殊要求",
        "",
    ])

    if annotation_summary:
        prompt_parts.extend([
            "## 标注阶段信息",
            f"- 标注数量: {len(annotation_summary.get('annotations', []))}",
            f"- 失败片段: {annotation_summary.get('failures', [])}",
            "",
        ])

    if generation_summary:
        prompt_parts.extend([
            "## 生成阶段信息",
            f"- 生成字段数: {len(generation_summary.get('generated_content', {}))}",
            f"- 重试次数: {generation_summary.get('total_retries', 0)}",
            "",
        ])

    prompt_parts.extend([
        "## 分析要求",
        "",
        "请对每个问题进行根因分析，判断：",
        "1. **错误来源**: annotator（标注器）、generator（生成器）、both（两者）、template（模板本身）",
        "2. **具体原因**: 详细说明为什么会出现这个问题",
        "3. **改进建议**: 针对标注器和/或生成器的具体改进措施",
        "",
        "## 错误来源判断标准",
        "",
        "- **annotator（标注器错误）**:",
        "  - 遗漏了应该标注的占位符（导致未替换）",
        "  - 错误标注了表头单元格（导致表头被覆盖）",
        "  - 标注位置错误（导致内容出现在错误位置）",
        "  - 占位符命名不规范（导致生成器无法理解）",
        "",
        "- **generator（生成器错误）**:",
        "  - 识别到占位符但未生成内容（导致占位符未填充）",
        "  - 生成内容不符合字数/格式要求（导致空白或溢出）",
        "  - 生成内容与用户需求不符（导致内容不一致）",
        "  - 格式化错误（导致排版混乱）",
        "",
        "- **both（两者都有问题）**:",
        "  - 标注器标注了不合理的占位符，生成器也未能正确处理",
        "",
        "- **template（模板本身问题）**:",
        "  - 模板设计缺陷（如表格结构不合理）",
        "  - 模板中有硬编码的示例内容需要替换但未标注",
        "",
        "## 输出格式（必须是合法 JSON）",
        "",
        "```json",
        "{",
        '  "analysis": [',
        "    {",
        '      "issue_index": 1,  // 对应上述问题编号',
        '      "root_cause": "annotator | generator | both | template",',
        '      "reason": "详细原因说明",',
        '      "recommendation": {',
        '        "for_annotator": "针对标注器的改进建议（如果相关）",',
        '        "for_generator": "针对生成器的改进建议（如果相关）"',
        "      }",
        "    }",
        "  ],",
        '  "overall_recommendation": {',
        '    "priority": "high | medium | low",  // 整体改进优先级',
        '    "key_insights": ["关键发现1", "关键发现2"],  // 2-3条核心洞察',
        '    "next_steps": ["改进步骤1", "改进步骤2"]  // 具体行动建议',
        "  }",
        "}",
        "```",
        "",
        "请只输出 JSON，不要额外说明。",
    ])

    return "\n".join(prompt_parts)


def _extract_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    """
    从 LLM 响应中提取 JSON

    Args:
        text: LLM 响应文本

    Returns:
        解析后的 JSON 对象，失败返回 None
    """
    text = text.strip()

    # 移除 markdown 代码块标记
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()

    # 尝试解析 JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取花括号内容
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass

    return None


def analyze_errors(
    vlm_result: Dict[str, Any],
    user_requirement: str = "",
    annotation_summary: Optional[Dict[str, Any]] = None,
    generation_summary: Optional[Dict[str, Any]] = None,
    outdir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    分析 VLM 检查结果，判断错误来源并生成改进建议

    Args:
        vlm_result: VLM 检查结果
        user_requirement: 用户需求描述
        annotation_summary: 标注阶段摘要（可选）
        generation_summary: 生成阶段摘要（可选）
        outdir: 输出目录（保存分析结果）

    Returns:
        结构化的错误分析结果:
        {
            "analysis": [
                {
                    "issue_index": 1,
                    "root_cause": "annotator | generator | both | template",
                    "reason": "...",
                    "recommendation": {
                        "for_annotator": "...",
                        "for_generator": "..."
                    }
                }
            ],
            "overall_recommendation": {
                "priority": "high | medium | low",
                "key_insights": [...],
                "next_steps": [...]
            }
        }
    """
    issues = vlm_result.get("issues", [])

    # 如果没有问题，直接返回空分析
    if not issues:
        return {
            "analysis": [],
            "overall_recommendation": {
                "priority": "low",
                "key_insights": ["文档质量良好，未发现问题"],
                "next_steps": []
            }
        }

    print(f"🔍 错误分析开始: 共 {len(issues)} 个问题")

    # 1. 构建分析提示词
    prompt = _build_reflection_prompt(
        vlm_result,
        user_requirement,
        annotation_summary,
        generation_summary,
    )

    # 2. 调用 LLM 分析
    print("   🤖 正在调用 LLM 进行根因分析...")
    response = _call_reflection_llm(prompt)

    # 3. 解析响应
    analysis = _extract_json_from_response(response)

    if not analysis:
        # 如果解析失败，返回默认分析
        print("   ⚠️  LLM 响应解析失败，使用默认分析")
        analysis = {
            "analysis": [
                {
                    "issue_index": idx + 1,
                    "root_cause": "unknown",
                    "reason": issue.get("detail", ""),
                    "recommendation": {
                        "for_annotator": "需要人工审查",
                        "for_generator": "需要人工审查"
                    }
                }
                for idx, issue in enumerate(issues)
            ],
            "overall_recommendation": {
                "priority": "high",
                "key_insights": ["LLM 分析失败，需要人工介入"],
                "next_steps": ["人工审查 VLM 结果", "检查分析模块配置"]
            }
        }

    print(f"   ✅ 分析完成: {len(analysis.get('analysis', []))} 个问题已分析")

    # 4. 保存分析结果
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

        # 保存完整分析结果
        analysis_path = outdir / "error_analysis.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        print(f"   💾 分析结果已保存到: {analysis_path}")

        # 保存 LLM 原始响应（用于调试）
        raw_path = outdir / "reflection_raw.txt"
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(response)
        print(f"   📝 LLM 原始响应已保存到: {raw_path}")

    return analysis


def format_for_knowledge_base(
    vlm_result: Dict[str, Any],
    analysis: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    将分析结果格式化为知识库条目

    Args:
        vlm_result: VLM 检查结果
        analysis: 错误分析结果
        context: 上下文信息（如用户需求、模板名称等）

    Returns:
        知识库条目（JSONL 格式的一行）
    """
    return {
        "timestamp": context.get("timestamp", ""),
        "template_name": context.get("template_name", "unknown"),
        "user_requirement": context.get("user_requirement", ""),
        "vlm_severity": vlm_result.get("summary", {}).get("severity", "unknown"),
        "issue_count": len(vlm_result.get("issues", [])),
        "analysis": analysis,
        "metadata": {
            "annotation_count": context.get("annotation_count", 0),
            "generation_count": context.get("generation_count", 0),
            "pipeline_version": "v5",
        }
    }


if __name__ == "__main__":
    # 测试示例
    import sys

    if len(sys.argv) < 2:
        print("用法: python reflection.py <vlm_result.json> [user_requirement]")
        sys.exit(1)

    vlm_result_path = Path(sys.argv[1])
    user_req = sys.argv[2] if len(sys.argv) > 2 else ""

    if not vlm_result_path.exists():
        print(f"错误: VLM 结果文件不存在: {vlm_result_path}")
        sys.exit(1)

    with open(vlm_result_path, "r", encoding="utf-8") as f:
        vlm_result = json.load(f)

    analysis = analyze_errors(
        vlm_result,
        user_req,
        outdir=Path("results/v5_reflection_test")
    )

    print("\n" + "=" * 60)
    print("错误分析结果：")
    print("=" * 60)
    print(json.dumps(analysis, ensure_ascii=False, indent=2))
