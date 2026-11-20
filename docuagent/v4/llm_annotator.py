"""
使用 Kimi LLM 对模板特征进行标注分析
"""

import json
import os
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import httpx


# ============ 自定义异常 ============

class TemplateTooComplexError(Exception):
    """模板过于复杂，超出模型max_tokens限制，无法处理"""
    def __init__(self, model: str, max_tokens: int, message: str = ""):
        self.model = model
        self.max_tokens = max_tokens
        default_msg = (
            f"❌ 模板过于复杂，超出模型 {model} 的 {max_tokens} tokens 限制。\n"
            f"   建议操作：\n"
            f"   1. 简化模板内容（减少字段、缩短文本）\n"
            f"   2. 更换更大上下文的模型（如 qwen-plus 支持 81K tokens）\n"
            f"   3. 将模板拆分为多个小模板分别处理"
        )
        super().__init__(message or default_msg)

try:
    from config.settings import KIMI_API_KEY as SETTINGS_KIMI_API_KEY
except ImportError:
    SETTINGS_KIMI_API_KEY = ""

try:
    from config.settings import DASHSCOPE_API_KEY as SETTINGS_DASHSCOPE_API_KEY
except ImportError:
    SETTINGS_DASHSCOPE_API_KEY = ""

try:
    from config.settings import FIREWORKS_API_KEY as SETTINGS_FIREWORKS_API_KEY
except ImportError:
    SETTINGS_FIREWORKS_API_KEY = ""

try:
    from config.settings import SHENMA_API_KEY as SETTINGS_GPT_API_KEY, OPENAI_PROXY_BASE as SETTINGS_OPENAI_BASE
except ImportError:
    SETTINGS_GPT_API_KEY = ""
    SETTINGS_OPENAI_BASE = "https://api.whatai.cc/v1"

try:
    from config.settings import GROQ_API_KEY as SETTINGS_GROQ_API_KEY
except ImportError:
    SETTINGS_GROQ_API_KEY = ""

try:
    from config.settings import SILICON_API_KEY as SETTINGS_SILICON_API_KEY
except ImportError:
    SETTINGS_SILICON_API_KEY = ""

_raw_token = (
    os.getenv("KIMI_API_KEY")
    or os.getenv("MOONSHOT_API_KEY")
    or SETTINGS_KIMI_API_KEY
    or ""
)

KIMI_API_BASE = os.getenv("KIMI_API_BASE", "https://api.moonshot.cn/v1")

# 通义千问配置
USE_QWEN = os.getenv("USE_QWEN_FOR_ANNOTATION", "false").lower() == "true"  # 默认不启用，需显式设置
DASHSCOPE_API_KEY = (
    os.getenv("DASHSCOPE_API_KEY")
    or SETTINGS_DASHSCOPE_API_KEY
    or ""
)

# 导入通义千问SDK
HAS_DASHSCOPE = False
if USE_QWEN:
    try:
        from dashscope import Generation
        import dashscope
        dashscope.api_key = DASHSCOPE_API_KEY
        HAS_DASHSCOPE = True
        print("✅ 通义千问SDK已加载，将使用Qwen模型进行标注和生成")
    except ImportError:
        print("⚠️ 未安装dashscope，将回退到Kimi API")
        USE_QWEN = False

# Fireworks配置（用于32B模型）
USE_FIREWORKS = os.getenv("USE_FIREWORKS_FOR_ANNOTATION", "false").lower() == "true"
FIREWORKS_API_KEY = (
    os.getenv("FIREWORKS_API_KEY")
    or SETTINGS_FIREWORKS_API_KEY
    or ""
)

# 导入Fireworks SDK
HAS_FIREWORKS = False
if USE_FIREWORKS:
    try:
        from fireworks.client import Fireworks
        fireworks_client = Fireworks(api_key=FIREWORKS_API_KEY)
        HAS_FIREWORKS = True
        print("✅ Fireworks SDK已加载，将使用Qwen2.5-32B模型")
    except ImportError:
        print("⚠️ 未安装fireworks-ai，将回退到其他API")
        USE_FIREWORKS = False

# PackyAPI配置（GPT-5.1超级模型）
USE_PACKY = os.getenv("USE_PACKY_FOR_ANNOTATION", "false").lower() == "true"

# 导入PackyAPI
HAS_PACKY = False
if USE_PACKY:
    try:
        from docuagent.packy_api import call_packy_api, HAS_PACKY_API
        HAS_PACKY = HAS_PACKY_API
        if HAS_PACKY:
            print("✅ PackyAPI已加载，将使用GPT-5.1超级模型")
        else:
            print("⚠️ PackyAPI token未配置，请设置PACKY_API_TOKEN")
            USE_PACKY = False
    except ImportError as e:
        print(f"⚠️ PackyAPI导入失败: {e}，将回退到其他API")
        USE_PACKY = False

# GPT配置（使用Packy的GPT API）
USE_GPT = os.getenv("USE_GPT_FOR_ANNOTATION", "false").lower() == "true"
GPT_API_KEY = (
    os.getenv("SHENMA_API_KEY")
    or SETTINGS_GPT_API_KEY
    or ""
)

# 导入GPT SDK
HAS_GPT = False
if USE_GPT:
    try:
        from openai import OpenAI
        gpt_client = OpenAI(
            api_key=GPT_API_KEY,
            base_url=os.getenv("OPENAI_PROXY_BASE", SETTINGS_OPENAI_BASE)
        )
        HAS_GPT = True
        print("✅ GPT SDK已加载，将使用 GPT-5.1 2025 模型")
    except ImportError:
        print("⚠️ 未安装openai，将回退到其他API")
        USE_GPT = False

# Groq配置
USE_GROQ = os.getenv("USE_GROQ_FOR_ANNOTATION", "false").lower() == "true"
GROQ_API_KEY = (
    os.getenv("GROQ_API_KEY")
    or SETTINGS_GROQ_API_KEY
    or ""
)

# SiliconFlow配置
USE_SILICON = os.getenv("USE_SILICON_FOR_ANNOTATION", "false").lower() == "true"
SILICON_API_KEY = (
    os.getenv("SILICON_API_KEY")
    or SETTINGS_SILICON_API_KEY
    or ""
)
SILICON_API_BASE = "https://api.siliconflow.cn/v1"
if USE_GROQ and not GROQ_API_KEY:
    print("⚠️ Groq API Key未配置，请设置GROQ_API_KEY")
    USE_GROQ = False
elif USE_GROQ:
    print("✅ Groq API已启用")

# 标注模型配置
if USE_GPT and HAS_GPT:
    # 使用 GPT-5.1 2025 模型
    _DEFAULT_ANNOTATION_MODEL = os.getenv("GPT_ANNOTATION_MODEL", "gpt-5.1-2025-11-13")
    GITCODE_JSON_REPAIR_MODEL = os.getenv("GPT_JSON_REPAIR_MODEL", "gpt-5.1-2025-11-13")
    GITCODE_CHECKER_MODEL = os.getenv("GPT_CHECKER_MODEL", "gpt-5.1-2025-11-13")
    GITCODE_GENERATION_MODEL = os.getenv("GPT_GENERATION_MODEL", "gpt-5.1-2025-11-13")
elif USE_PACKY and HAS_PACKY:
    # 使用PackyAPI GPT-5.1 超级模型
    _DEFAULT_ANNOTATION_MODEL = os.getenv("PACKY_ANNOTATION_MODEL", "gpt-5.1-2025-11-13")
    GITCODE_JSON_REPAIR_MODEL = os.getenv("PACKY_JSON_REPAIR_MODEL", "gpt-5.1-2025-11-13")
    GITCODE_CHECKER_MODEL = os.getenv("PACKY_CHECKER_MODEL", "gpt-5.1-2025-11-13")
    GITCODE_GENERATION_MODEL = os.getenv("PACKY_GENERATION_MODEL", "gpt-5.1-2025-11-13")
elif USE_FIREWORKS and HAS_FIREWORKS:
    # 使用Fireworks的Qwen模型（支持128K tokens）
    _DEFAULT_ANNOTATION_MODEL = os.getenv("FIREWORKS_ANNOTATION_MODEL", "accounts/fireworks/models/qwen3-235b-a22b-instruct-2507")
    GITCODE_JSON_REPAIR_MODEL = os.getenv("FIREWORKS_JSON_REPAIR_MODEL", "accounts/fireworks/models/qwen3-235b-a22b-instruct-2507")
    GITCODE_CHECKER_MODEL = os.getenv("FIREWORKS_CHECKER_MODEL", "accounts/fireworks/models/qwen3-235b-a22b-instruct-2507")
    GITCODE_GENERATION_MODEL = os.getenv("FIREWORKS_GENERATION_MODEL", "accounts/fireworks/models/qwen3-235b-a22b-instruct-2507")
elif USE_QWEN and HAS_DASHSCOPE:
    # 使用通义千问
    _DEFAULT_ANNOTATION_MODEL = os.getenv("QWEN_ANNOTATION_MODEL", "qwen-plus")
    GITCODE_JSON_REPAIR_MODEL = os.getenv("QWEN_JSON_REPAIR_MODEL", "qwen-turbo")
    GITCODE_CHECKER_MODEL = os.getenv("QWEN_CHECKER_MODEL", "qwen-plus")
    GITCODE_GENERATION_MODEL = os.getenv("QWEN_GENERATION_MODEL", "qwen-plus")
    GITCODE_GENERATION_MODEL = os.getenv("QWEN_GENERATION_MODEL", "qwen-plus")
elif USE_SILICON:
    # SiliconFlow 配置
    _DEFAULT_ANNOTATION_MODEL = os.getenv("SILICON_ANNOTATION_MODEL", "deepseek-ai/DeepSeek-V3")
    GITCODE_JSON_REPAIR_MODEL = os.getenv("SILICON_CHECKER_MODEL", "deepseek-ai/DeepSeek-V3")
    GITCODE_CHECKER_MODEL = os.getenv("SILICON_CHECKER_MODEL", "deepseek-ai/DeepSeek-V3")
    GITCODE_GENERATION_MODEL = os.getenv("SILICON_GENERATION_MODEL", "Qwen/Qwen2.5-7B-Instruct")
elif USE_GROQ:
    # 使用Groq
    _DEFAULT_ANNOTATION_MODEL = os.getenv("GROQ_ANNOTATION_MODEL", "moonshotai/kimi-k2-instruct-0905")
    GITCODE_JSON_REPAIR_MODEL = os.getenv("GROQ_JSON_REPAIR_MODEL", "moonshotai/kimi-k2-instruct-0905")
    GITCODE_CHECKER_MODEL = os.getenv("GROQ_CHECKER_MODEL", "moonshotai/kimi-k2-instruct-0905")
    GITCODE_GENERATION_MODEL = os.getenv("GROQ_GENERATION_MODEL", "meta-llama/llama-4-maverick-17b-128e-instruct")
else:
    # 使用Kimi（原逻辑）
    _DEFAULT_ANNOTATION_MODEL = os.getenv("KIMI_ANNOTATION_MODEL", "kimi-k2-0905-preview")
    GITCODE_JSON_REPAIR_MODEL = os.getenv("KIMI_JSON_REPAIR_MODEL", "kimi-k2-0905-preview")
    GITCODE_CHECKER_MODEL = os.getenv("KIMI_CHECKER_MODEL", "kimi-k2-0905-preview")
    GITCODE_GENERATION_MODEL = os.getenv("KIMI_GENERATION_MODEL", "kimi-k2-0905-preview")

GITCODE_MODEL = _DEFAULT_ANNOTATION_MODEL
CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

# Token 统计容器（估算）
TOKEN_STATS: Dict[str, Any] = {
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "calls": [],
    "by_stage": {},
}


def _approx_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _bump_stat(key: str, inc: int = 1) -> None:
    try:
        path = os.getenv("STATS_LOG_PATH")
        if not path:
            return
        data: Dict[str, Any] = {}
        try:
            from pathlib import Path

            p = Path(path)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
        except Exception:
            data = {}
        data[key] = int(data.get(key, 0)) + inc
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _add_metric(key: str, inc: float) -> None:
    try:
        path = os.getenv("STATS_LOG_PATH")
        if not path:
            return
        data: Dict[str, Any] = {}
        try:
            from pathlib import Path

            p = Path(path)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
        except Exception:
            data = {}
        try:
            base = float(data.get(key, 0.0))
        except Exception:
            base = 0.0
        data[key] = round(base + float(inc), 6)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _log_token_usage(messages: List[Dict[str, str]], output_text: str, model: str) -> None:
    try:
        stage = os.getenv("TOKEN_STAGE", "unknown")
        # 汇总输入文本
        input_text = "\n".join([m.get("content", "") for m in messages])
        in_tokens = _approx_tokens(input_text)
        out_tokens = _approx_tokens(output_text)

        TOKEN_STATS["total_input_tokens"] += in_tokens
        TOKEN_STATS["total_output_tokens"] += out_tokens
        TOKEN_STATS["calls"].append(
            {
                "stage": stage,
                "model": model,
                "input_tokens": in_tokens,
                "output_tokens": out_tokens,
            }
        )
        by_stage = TOKEN_STATS.setdefault("by_stage", {})
        st = by_stage.get(stage, {"input": 0, "output": 0, "calls": 0})
        st["input"] += in_tokens
        st["output"] += out_tokens
        st["calls"] += 1
        by_stage[stage] = st

        path = os.getenv("TOKEN_LOG_PATH")
        if path:
            try:
                from pathlib import Path

                Path(path).parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(TOKEN_STATS, f, ensure_ascii=False, indent=2)
            except Exception as e:  # pragma: no cover - 日志失败不影响主流程
                print(f"⚠️ 写入 token 日志失败: {e}")
        
        # 同时记录到数据库用于统计（每个API调用都会被记录）
        try:
            from utils.llm_logger import log_llm_call
            log_llm_call(
                user_id=None,  # V5 generation doesn't have user context at this level
                feature='v5_generation',
                model_name=model,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                api_provider='qwen' if 'qwen' in model.lower() else 'other'
            )
        except Exception:
            # 数据库日志失败不影响主流程
            pass
    except Exception:
        # 不影响主流程
        pass


def _strip_code_blocks(text: str) -> str:
    """移除 Markdown 代码块包裹（Kimi 不输出 <think> 标签）。"""
    if not text:
        return ""
    cleaned = CODE_FENCE_PATTERN.sub("", text)
    return cleaned.strip()


def _to_langchain_messages(messages: List[Dict[str, str]]) -> List[Tuple[str, str]]:
    """将 OpenAI 风格消息转换为 LangChain ChatOpenAI 接受的 (role, content) 列表。"""
    return [(msg.get("role", "user"), msg.get("content", "")) for msg in messages]


def _extract_response_text(resp: Any) -> str:
    """从 Kimi/OpenAI 兼容响应中提取文本。"""
    try:
        if isinstance(resp, dict):
            choices = resp.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                content = msg.get("content") or ""
                if content:
                    return str(content)
    except Exception:
        pass
    try:
        return str(resp)
    except Exception:
        return ""


def _kimi_chat_completions(messages: List[Dict[str, str]], *, model: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
    """调用 Kimi API (OpenAI 兼容接口)，带有重试和退避机制"""
    if not _raw_token:
        raise RuntimeError("Set KIMI_API_KEY or MOONSHOT_API_KEY to use Kimi")
    url = f"{KIMI_API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {_raw_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "stream": False,
    }

    # 根据模型类型调整超时时间
    # thinking 模型需要更长时间进行推理，尤其是处理长文档时
    timeout = 600 if "thinking" in model else 300  # 10分钟 vs 5分钟

    # 重试配置
    max_retries = 3
    base_delay = 5.0  # 基础延迟（秒）

    for attempt in range(max_retries):
        try:
            # trust_env=False: 不使用环境变量中的代理设置（避免SOCKS代理错误）
            r = httpx.post(url, headers=headers, json=payload, timeout=timeout, trust_env=False)
            r.raise_for_status()
            result = r.json()

            # 检查是否因为达到max_tokens上限而停止
            if result.get("choices"):
                finish_reason = result["choices"][0].get("finish_reason")
                if finish_reason == "length":
                    # 模板过于复杂，超出max_tokens限制
                    raise TemplateTooComplexError(model=model, max_tokens=max_tokens)

            return result
        except TemplateTooComplexError:
            # 模板过于复杂，不可重试，直接抛出
            raise
        except httpx.TimeoutException as exc:
            # 超时错误 - 可重试
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # 指数退避: 5s, 10s, 20s
                print(f"⏱️ API 超时（尝试 {attempt + 1}/{max_retries}），{delay}秒后重试...")
                time.sleep(delay)
            else:
                print(f"❌ API 超时，已达最大重试次数")
                raise exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            # 429 (限流) 和 503 (服务不可用) - 可重试
            if status_code in [429, 503] and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"⚠️ API 返回 {status_code}（尝试 {attempt + 1}/{max_retries}），{delay}秒后重试...")
                time.sleep(delay)
            # 400 (错误请求) 和其他 4xx - 不可重试
            elif 400 <= status_code < 500:
                print(f"❌ API 返回 {status_code}: {exc.response.text[:200]}")
                raise exc
            # 5xx 服务器错误 - 可重试
            elif attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"⚠️ 服务器错误 {status_code}（尝试 {attempt + 1}/{max_retries}），{delay}秒后重试...")
                time.sleep(delay)
            else:
                raise exc
        except Exception as exc:
            # 其他错误（如网络问题）- 可重试
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"⚠️ 网络错误（尝试 {attempt + 1}/{max_retries}），{delay}秒后重试...")
                time.sleep(delay)
            else:
                raise exc

    # 理论上不会到达这里，但为了类型检查
    raise RuntimeError("重试逻辑异常")


def _qwen_chat_completions(messages: List[Dict[str, str]], *, model: str, temperature: float, max_tokens: int) -> str:
    """调用通义千问API，带有重试和退避机制"""
    if not HAS_DASHSCOPE:
        raise RuntimeError("通义千问SDK未加载")

    # 重试配置
    max_retries = 3
    base_delay = 3.0  # 基础延迟（秒）

    for attempt in range(max_retries):
        try:
            response = Generation.call(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=False,
                result_format='message',
            )

            # 检查响应状态
            if response.status_code == 200:
                # 检查是否因为达到max_tokens上限而停止
                finish_reason = response.output.choices[0].get("finish_reason")
                if finish_reason == "length":
                    # 模板过于复杂，超出max_tokens限制
                    raise TemplateTooComplexError(model=model, max_tokens=max_tokens)

                content = response.output.choices[0].message.content
                return content
            else:
                error_msg = f"API调用失败: {response.code} - {response.message}"

                # 检查是否可重试
                if response.code in ['Throttling.RateQuota', 'InternalError.Timeout'] and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"⚠️ {response.message}（尝试 {attempt + 1}/{max_retries}），{delay}秒后重试...")
                    time.sleep(delay)
                else:
                    raise RuntimeError(error_msg)

        except TemplateTooComplexError:
            # 模板过于复杂，不可重试，直接抛出
            raise
        except Exception as exc:
            # 其他错误 - 可重试
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"⚠️ 通义千问调用错误（尝试 {attempt + 1}/{max_retries}），{delay}秒后重试...")
                print(f"   错误详情: {exc}")
                time.sleep(delay)
            else:
                print(f"❌ 通义千问调用失败: {exc}")
                raise exc

    # 理论上不会到达这里
    raise RuntimeError("重试逻辑异常")


def _gpt_chat_completions(messages: List[Dict[str, str]], *, model: str, temperature: float, max_tokens: int) -> str:
    """调用GPT API，带有重试和退避机制"""
    if not HAS_GPT:
        raise RuntimeError("GPT SDK未加载")
    
    # 重试配置
    max_retries = 3
    base_delay = 3.0
    
    for attempt in range(max_retries):
        try:
            response = gpt_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            # 检查是否因为达到max_tokens上限而停止
            if response.choices[0].finish_reason == "length":
                raise TemplateTooComplexError(model=model, max_tokens=max_tokens)
            
            content = response.choices[0].message.content
            return content
            
        except TemplateTooComplexError:
            raise
        except Exception as exc:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"⚠️ GPT调用错误（尝试 {attempt + 1}/{max_retries}），{delay}秒后重试...")
                print(f"   错误详情: {exc}")
                time.sleep(delay)
            else:
                print(f"❌ GPT调用失败: {exc}")
                raise exc
    
    raise RuntimeError("重试逻辑异常")


def _fireworks_chat_completions(messages: List[Dict[str, str]], *, model: str, temperature: float, max_tokens: int) -> str:
    """调用Fireworks API，带有重试和退避机制

    超过4K tokens时自动使用流式传输
    """
    if not HAS_FIREWORKS:
        raise RuntimeError("Fireworks SDK未加载")

    # 重试配置
    max_retries = 3
    base_delay = 3.0  # 基础延迟（秒）

    # Fireworks限制：非流式传输限制为5K tokens，超过需使用流式
    use_streaming = max_tokens > 5000

    for attempt in range(max_retries):
        try:
            if use_streaming:
                # 使用流式传输（适用于 >4K tokens）
                response_stream = fireworks_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )

                # 收集流式响应块
                content_chunks = []
                final_finish_reason = None
                for chunk in response_stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content:
                            content_chunks.append(delta.content)
                        # 获取最后一个chunk的finish_reason
                        if hasattr(chunk.choices[0], 'finish_reason') and chunk.choices[0].finish_reason:
                            final_finish_reason = chunk.choices[0].finish_reason

                # 检查是否因为达到max_tokens上限而停止
                if final_finish_reason == "length":
                    raise TemplateTooComplexError(model=model, max_tokens=max_tokens)

                # 拼接完整内容
                content = "".join(content_chunks)

                if not content:
                    raise RuntimeError("Fireworks流式API返回空响应")

                return content
            else:
                # 使用非流式传输（≤4K tokens）
                response = fireworks_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                # 检查是否因为达到max_tokens上限而停止
                if response.choices and len(response.choices) > 0:
                    finish_reason = response.choices[0].finish_reason
                    if finish_reason == "length":
                        raise TemplateTooComplexError(model=model, max_tokens=max_tokens)

                    content = response.choices[0].message.content
                    return content
                else:
                    raise RuntimeError("Fireworks API返回空响应")

        except TemplateTooComplexError:
            # 模板过于复杂，不可重试，直接抛出
            raise
        except Exception as exc:
            # 错误处理 - 可重试
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                stream_info = "流式" if use_streaming else "非流式"
                print(f"⚠️ Fireworks调用错误（{stream_info}，尝试 {attempt + 1}/{max_retries}），{delay}秒后重试...")
                print(f"   错误详情: {exc}")
                time.sleep(delay)
            else:
                stream_info = "流式" if use_streaming else "非流式"
                print(f"❌ Fireworks调用失败（{stream_info}）: {exc}")
                raise exc

    # 理论上不会到达这里
    raise RuntimeError("重试逻辑异常")


def _packy_chat_completions(messages: List[Dict[str, str]], *, model: str, temperature: float, max_tokens: int) -> str:
    """调用PackyAPI GPT-5.1，带有重试和退避机制"""
    if not HAS_PACKY:
        raise RuntimeError("PackyAPI未加载或token未配置")

    # 重试配置
    max_retries = 3
    base_delay = 3.0  # 基础延迟（秒）

    for attempt in range(max_retries):
        try:
            # 构建系统和用户消息
            system_prompt = None
            user_content = ""

            for msg in messages:
                if msg.get("role") == "system":
                    system_prompt = msg.get("content", "")
                elif msg.get("role") == "user":
                    user_content = msg.get("content", "")

            # 调用PackyAPI
            content = call_packy_api(
                prompt=user_content,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt
            )

            return content

        except TemplateTooComplexError:
            # 模板过于复杂，不可重试，直接抛出
            raise
        except Exception as exc:
            # 错误处理 - 可重试
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"⚠️ PackyAPI调用错误（尝试 {attempt + 1}/{max_retries}），{delay}秒后重试...")
                print(f"   错误详情: {exc}")
                time.sleep(delay)
            else:
                print(f"❌ PackyAPI调用失败: {exc}")
                raise exc

    # 理论上不会到达这里
    raise RuntimeError("重试逻辑异常")


def _groq_chat_completions(messages: List[Dict[str, str]], *, model: str, temperature: float, max_tokens: int) -> str:
    """调用Groq API，带有重试和退避机制"""
    if not GROQ_API_KEY:
        raise RuntimeError("Groq API Key未配置")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "stream": False,
    }

    # 重试配置
    max_retries = 3
    base_delay = 3.0

    for attempt in range(max_retries):
        try:
            r = httpx.post(url, headers=headers, json=payload, timeout=60.0)
            r.raise_for_status()
            result = r.json()

            if result.get("choices"):
                finish_reason = result["choices"][0].get("finish_reason")
                if finish_reason == "length":
                    raise TemplateTooComplexError(model=model, max_tokens=max_tokens)
                
                content = result["choices"][0]["message"]["content"]
                return content
            else:
                raise RuntimeError("Groq API返回空choices")

        except TemplateTooComplexError:
            raise
        except Exception as exc:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"⚠️ Groq调用错误（尝试 {attempt + 1}/{max_retries}），{delay}秒后重试...")
                print(f"   错误详情: {exc}")
                time.sleep(delay)
            else:
                print(f"❌ Groq调用失败: {exc}")
                raise exc

    raise RuntimeError("重试逻辑异常")


def _silicon_chat_completions(messages: List[Dict[str, str]], *, model: str, temperature: float, max_tokens: int) -> str:
    """调用 SiliconFlow API，带有重试和退避机制"""
    if not SILICON_API_KEY:
        raise RuntimeError("未配置 SILICON_API_KEY")

    headers = {
        "Authorization": f"Bearer {SILICON_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False
    }

    max_retries = 3
    base_delay = 3.0

    for attempt in range(max_retries):
        try:
            r = httpx.post(
                f"{SILICON_API_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0
            )
            
            if r.status_code != 200:
                error_msg = f"SiliconFlow API Error: {r.status_code} - {r.text}"
                raise RuntimeError(error_msg)

            result = r.json()

            if result.get("choices"):
                finish_reason = result["choices"][0].get("finish_reason")
                if finish_reason == "length":
                    raise TemplateTooComplexError(model=model, max_tokens=max_tokens)
                
                content = result["choices"][0]["message"]["content"]
                return content
            else:
                raise RuntimeError("SiliconFlow API返回空choices")

        except TemplateTooComplexError:
            raise
        except Exception as exc:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"⚠️ SiliconFlow调用错误（尝试 {attempt + 1}/{max_retries}），{delay}秒后重试...")
                print(f"   错误详情: {exc}")
                time.sleep(delay)
            else:
                print(f"❌ SiliconFlow调用失败: {exc}")
                raise exc

    raise RuntimeError("重试逻辑异常")
# 各模型的最大 tokens 限制
QWEN_TURBO_MAX_TOKENS = 16384   # qwen-turbo 最大 16K tokens
QWEN_PLUS_MAX_TOKENS = 81920    # qwen-plus 最大 81K tokens
FIREWORKS_MAX_TOKENS = 128000   # Fireworks Qwen2.5-32B 最大 128K tokens
PACKY_MAX_TOKENS = int(os.getenv("PACKY_MAX_TOKENS", "8000"))  # PackyAPI GPT-5.1 可配置（默认8K）
GPT_MAX_TOKENS = 8192           # GPT-4 最大 8K tokens
KIMI_MAX_TOKENS = 128000        # kimi-k2 系列最大 128K tokens
GROQ_KIMI_MAX_TOKENS = 16384    # Groq Kimi 最大 16K tokens
GROQ_LLAMA_MAX_TOKENS = 8192    # Groq Llama 最大 8K tokens
GROQ_GPT_OSS_MAX_TOKENS = 65536 # Groq GPT-OSS 最大 65K tokens
SILICON_ANNOTATION_MAX_TOKENS = 32768 # SiliconFlow Annotation Max 32k
SILICON_GENERATION_MAX_TOKENS = 8192  # SiliconFlow Generation Max 8k

# 默认最大tokens（根据当前使用的模型）
if USE_GPT and HAS_GPT:
    DEFAULT_MAX_TOKENS = GPT_MAX_TOKENS
elif USE_FIREWORKS and HAS_FIREWORKS:
    DEFAULT_MAX_TOKENS = FIREWORKS_MAX_TOKENS
elif USE_QWEN and HAS_DASHSCOPE:
    # 根据实际模型选择
    if "turbo" in GITCODE_MODEL.lower():
        DEFAULT_MAX_TOKENS = QWEN_TURBO_MAX_TOKENS
    else:  # qwen-plus 或其他
        DEFAULT_MAX_TOKENS = QWEN_PLUS_MAX_TOKENS
elif USE_SILICON:
    # SiliconFlow token limits
    if "deepseek" in GITCODE_MODEL.lower():
        DEFAULT_MAX_TOKENS = SILICON_ANNOTATION_MAX_TOKENS
    else:
        DEFAULT_MAX_TOKENS = SILICON_GENERATION_MAX_TOKENS
elif USE_GROQ:
    # 根据模型名称判断
    if "llama" in GITCODE_MODEL.lower():
        DEFAULT_MAX_TOKENS = GROQ_LLAMA_MAX_TOKENS
    elif "gpt-oss" in GITCODE_MODEL.lower() or "openai" in GITCODE_MODEL.lower():
        DEFAULT_MAX_TOKENS = GROQ_GPT_OSS_MAX_TOKENS
    else:
        DEFAULT_MAX_TOKENS = GROQ_KIMI_MAX_TOKENS
else:
    DEFAULT_MAX_TOKENS = KIMI_MAX_TOKENS

JSON_REPAIR_MAX_TOKENS = DEFAULT_MAX_TOKENS  # JSON修复使用相同限制


def stream_gitcode_chat(
    messages: List[dict],
    model: str = GITCODE_MODEL,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.3,  # 降低温度，让模型更专注
) -> str:
    """使用 GPT、PackyAPI、Fireworks、Qwen、Groq 或 SiliconFlow API 进行对话（根据配置自动切换）"""
    try:
        # SiliconFlow 优先 (但排除 qwen-flash，因为它应该走 DashScope)
        if USE_SILICON and model != "qwen-flash":
            if "deepseek" in model.lower():
                silicon_max = SILICON_ANNOTATION_MAX_TOKENS
            else:
                silicon_max = SILICON_GENERATION_MAX_TOKENS
            
            actual_max_tokens = min(max_tokens, silicon_max)
            content = _silicon_chat_completions(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=actual_max_tokens,
            )
            cleaned = _strip_code_blocks(content)
            _log_token_usage(messages, cleaned, model)
            return cleaned

        # 优先检查是否指定了 Groq 模型 (gpt-oss 或 llama)
        if USE_GROQ and ("gpt-oss" in model.lower() or "llama" in model.lower()):
            # 使用Groq
            if "llama" in model.lower():
                groq_max = GROQ_LLAMA_MAX_TOKENS
            elif "gpt-oss" in model.lower() or "openai" in model.lower():
                groq_max = GROQ_GPT_OSS_MAX_TOKENS
            else:
                groq_max = GROQ_KIMI_MAX_TOKENS
            
            actual_max_tokens = min(max_tokens, groq_max)
            content = _groq_chat_completions(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=actual_max_tokens,
            )
            cleaned = _strip_code_blocks(content)
            _log_token_usage(messages, cleaned, model)
            return cleaned

        if USE_GPT and HAS_GPT:
            # 使用GPT-4
            actual_max_tokens = min(max_tokens, 8192)  # GPT-4 默认8K
            content = _gpt_chat_completions(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=actual_max_tokens,
            )
            cleaned = _strip_code_blocks(content)
            _log_token_usage(messages, cleaned, model)
            return cleaned
        elif USE_PACKY and HAS_PACKY:
            # 使用PackyAPI GPT-5.1
            actual_max_tokens = min(max_tokens, PACKY_MAX_TOKENS)
            content = _packy_chat_completions(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=actual_max_tokens,
            )
            cleaned = _strip_code_blocks(content)
            _log_token_usage(messages, cleaned, model)
            return cleaned
        elif USE_FIREWORKS and HAS_FIREWORKS:
            # 使用Fireworks（Qwen2.5-32B）
            # 限制到128K，超过4K自动使用流式
            actual_max_tokens = min(max_tokens, FIREWORKS_MAX_TOKENS)
            content = _fireworks_chat_completions(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=actual_max_tokens,
            )
            cleaned = _strip_code_blocks(content)
            _log_token_usage(messages, cleaned, model)
            return cleaned
        elif USE_QWEN and HAS_DASHSCOPE:
            # 使用通义千问 - 根据模型动态选择max_tokens
            model_lower = model.lower()
            if "qwen3-8b" in model_lower:
                qwen_max = 8192  # Qwen3 8B 最大 8K tokens
            elif "turbo" in model_lower:
                qwen_max = 32768  # 16K
            else:  # qwen-plus 等
                qwen_max = 32768   # 81K（默认上限）

            actual_max_tokens = min(max_tokens, qwen_max)
            content = _qwen_chat_completions(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=actual_max_tokens,
            )
            cleaned = _strip_code_blocks(content)
            _log_token_usage(messages, cleaned, model)
            return cleaned
        elif USE_GROQ:
            # 使用Groq
            if "llama" in model.lower():
                groq_max = GROQ_LLAMA_MAX_TOKENS
            elif "gpt-oss" in model.lower() or "openai" in model.lower():
                groq_max = GROQ_GPT_OSS_MAX_TOKENS
            else:
                groq_max = GROQ_KIMI_MAX_TOKENS
            
            actual_max_tokens = min(max_tokens, groq_max)
            content = _groq_chat_completions(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=actual_max_tokens,
            )
            cleaned = _strip_code_blocks(content)
            _log_token_usage(messages, cleaned, model)
            return cleaned
        else:
            # 使用Kimi（原逻辑）
            actual_max_tokens = min(max_tokens, KIMI_MAX_TOKENS)
            resp = _kimi_chat_completions(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=actual_max_tokens,
            )
            content = _extract_response_text(resp)
            cleaned = _strip_code_blocks(content)
            _log_token_usage(messages, cleaned, model)
            return cleaned
    except TemplateTooComplexError:
        # 模板过于复杂的错误，直接抛出，让上层调用者处理
        raise
    except Exception as exc:
        api_name = "PackyAPI" if (USE_PACKY and HAS_PACKY) else ("Fireworks" if (USE_FIREWORKS and HAS_FIREWORKS) else ("通义千问" if (USE_QWEN and HAS_DASHSCOPE) else ("Groq" if USE_GROQ else "Kimi")))
        print(f"❌ {api_name} Chat 调用失败: {exc}")
        _bump_stat("llm_failures", 1)
        return ""


def call_gitcode_llm(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """调用 LLM 模型进行标注分析（PackyAPI、Fireworks、Qwen 或 Kimi）。"""

    # 根据使用的模型调整system message
    if USE_PACKY and HAS_PACKY:
        assistant_name = "GPT-5.1"
        assistant_intro = "你是GPT-5.1，顶级的大语言模型，具有卓越的推理能力、精准的结构化分析和强大的文档处理能力。"
    elif USE_FIREWORKS and HAS_FIREWORKS:
        assistant_name = "Qwen2.5-32B"
        assistant_intro = "你是Qwen2.5-32B，由阿里云Qwen团队开发的强大语言模型，参数量达到32B，在中文理解、结构化分析和文档处理方面表现卓越。"
    elif USE_QWEN and HAS_DASHSCOPE:
        assistant_name = "通义千问"
        assistant_intro = "你是通义千问，由阿里云提供的大语言模型，擅长中文理解、结构化分析和精确的文档处理。"
    elif USE_GROQ:
        assistant_name = "Groq"
        assistant_intro = "你是Groq加速引擎，擅长快速、精准的文档结构化分析。"
    else:
        assistant_name = "Kimi"
        assistant_intro = "你是 Kimi，由 Moonshot AI 提供的人工智能助手，擅长深度推理和结构化分析。"

    messages = [
        {
            "role": "system",
            "content": (
                f"{assistant_intro}\n\n"
                "# 你的角色\n"
                "你是一个专业的文档模板标注专家，精通文档结构分析和占位符标注。\n\n"
                "# 你的任务\n"
                "分析提供的文档模板，识别所有需要用户填写的位置，为这些位置生成 {{占位符}} 标注，并输出完整的 JSON 标注方案。\n\n"
                "2. **占位符格式**：\n"
                "   - 必须使用双花括号包裹，例如 `{{teacher_name}}`\n"
                "   - 占位符名称使用英文小写和下划线\n"
                "   - 不要包含空格或其他字符\n\n"
                "3. **输出格式**：\n"
                "1. **深入分析**：运用你的理解能力，系统性地分析文档的每个部分\n"
                "2. **全面覆盖**：确保不遗漏任何需要标注的位置\n"
                "3. **精确判断**：准确区分固定内容和可变内容\n"
                "4. **结构化输出**：严格按照 JSON 格式输出标注结果\n\n"
                "# 重要提醒\n"
                "- 请仔细阅读用户提供的标注规则和示例\n"
                "- 输出必须是合法的 JSON 对象，不要包含 Markdown 代码块标记\n"
                "- 如果文档很长，请耐心分析每个部分\n"
                "- 标注数量通常在 50-150 个之间，不要遗漏"
            ),
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]

    print(f"🔄 正在调用 Kimi ({GITCODE_MODEL}) 模型...")
    print(f"   请求Token数: ~{len(prompt) // 4}")
    print(f"   Max Tokens: {max_tokens}")
    print(f"   Temperature: 0.3（精确模式）")

    content = stream_gitcode_chat(messages, model=GITCODE_MODEL, max_tokens=max_tokens, temperature=0.3)
    if not content:
        print("❌ 错误：Kimi 无响应或返回为空")
        return ""

    print("✅ LLM响应成功")
    print(f"   响应长度: {len(content)} 字符")
    return content


def create_annotation_prompt(features_text: str, kb_insights: str = "") -> str:
    """
    构建标注提示词（优化版：引导 Kimi 推理，保持完整上下文）

    Args:
        features_text: 模板特征文本
        kb_insights: 知识库洞察（可选，来自历史经验）

    Returns:
        完整的标注提示词
    """

    prefix = """# 文档模板标注任务

你是一名专业的文档模板标注专家。现在需要你分析一个教案模板，识别所有需要用户填写的位置。

## 📋 任务说明

你将收到一个 Markdown 格式的文档模板（从 DOCX 转换而来），需要：
1. **系统性分析**：从头到尾分析每个段落和表格单元格
2. **识别填空位置**：找出所有空白区域、示例内容、下划线等需要填写的位置
3. **生成标注方案**：为每个位置创建语义化的占位符，输出 JSON 格式的标注

## 🔍 Markdown 格式说明

- `[[DOCX-BLOCK id=Pxxxx ...]]` 后面跟的是段落内容
- `[[DOCX-CELL table=... row=... grid_col=... cell_id=...]]` 后面跟的是表格单元格内容
- 你需要保留这些标记，在合适的位置插入 {{占位符}}

## 💡 判断标准（请仔细思考）

### 什么应该标注：
- ✅ **空白区域**：段落后面没有内容，或单元格为空
- ✅ **示例内容**（极其重要）：
  - 明显的占位符：如 "XX"、"……"、"___"、"待填写"
  - 编号列表示例：如 "1.…… 2.…… 3.……" 或 "1. XXX 2. XXX"
  - 引导性示例：如 "通过真实案例激发学习兴趣……"、"结合生活实际……"
  - 模糊描述：如 "相关知识点"、"具体内容"、"教学活动"（没有具体说明）
  - 重复的示例模式：如 "活动一：…… 活动二：…… 活动三：……"
- ✅ **标签后的值**：如 "课程名称：" 后面的内容
- ✅ **可变字段**：日期、时间、姓名、章节名等

**判断是否为示例的技巧**：
- 如果内容过于通用、模糊、不具体，很可能是示例
- 如果内容以省略号结尾或包含多个省略号，通常是示例
- 如果是编号列表但每项都很简短或重复，是示例
- 如果句子像是"模板填写说明"而非实际内容，是示例

### 什么不应该标注���
- ❌ **固定标签**：表格左侧的 "姓名"、"授课章节"、"教学目标" 等标签文字本身
- ❌ **表头行**：如 "思政目标"、"知识目标"、"教师活动" 等栏目名称
- ❌ **固定说明**：如 "教务处 印制"、"教 案" 等标题

**⚠️ 极其重要：绝对禁止标注表头单元格**

表格的表头行（通常是第一行）包含列名，如："教学内容"、"教师活动"、"学生活动"、"设计意���"、"思政目标"、"知识目标" 等。

这些表头单元格的特征：
1. 通常在表格第一行
2. 包含"...活动"、"...目标"、"...内容"、"...意图" 等词汇
3. 是描述性的列名，不是具体内容

**对待表头单元格的规则**：
- ❌ **绝对不能使用 `replace` 动作**
- ❌ **不要创建任何标注**
- ❌ **即使表头单元格内容看起来像占位符，也不要标注**
- ✅ **表头必须完整保留，不做任何修改**

## 🎯 标注策略

### 1. 段落标注
- **形式**：`标签：值`
- **策略**：使用 `append` 动作，保留标签，在冒号后添加占位符
- **示例**：`课程名称：` → `课程名称：{{course_name}}`

### 2. 表格标注
- **左列（标签列）**：不标注
- **右列（值列）**：标注
- **空白单元格**：使用 `replace` 动作，完全替换为占位符

### 特殊情况：单元格包含标题和内容区
某些单元格（尤其在任务书模板中）会包含：
1. **一个标题**（通常加粗、简短、概念性）
2. **后面跟着内容填写区域**（可能是空行、示例文本或下划线）

**识别方法**：
- 单元格开头有加粗文字（如 `**课题简介**`、`**研究内容**`）
- 标题后有换行符和空白区域或示例内容
- 标题是概念性描述，不是具体内容

**标注策略**：
- ✅ 使用 `append` 动作（不是 `replace`）
- ✅ 保留标题文字不变
- ✅ 在标题后添加占位符
- **示例**：
  - 原文：`**课题简介**\n\n这里填写课题的简要介绍……`
  - 标注：`**课题简介**\n\n{{topic_introduction}}`
  - 原文：`**研究目标**\n\n___________`
  - 标注：`**研究目标**\n\n{{research_objectives}}`

**⚠️ 关键**：这种情况绝对不能使用 `replace` 替换整个单元格内容，必须使用 `append` 保留标题！

### 特殊情况2：标题行与内容行分开（不同行）⚠️ 极其重要 ⚠️
在教案模板中，经常出现**标题行和内容行在不同行**的模式：
- **标题行**：包含章节标题和说明，如 `一、教学内容分析（对教学内容进行知识和能力要素分析，说明它的地位和作用）`
- **内容行**：标题行的下一行，通常是**空白单元格**，用于填充实际内容

**识别特征**：
1. 标题行包含中文序号（一、二、三、四、五）+ 标题 + 括号说明
2. 下一行是空白单元格（或包含空白/示例文本）
3. 标题行和内容行在**不同的 row**

**⚠️ 正确标注方法**：
- 标题行（如 row=5）：**不标注**，保持原样
- 内容行（如 row=6，空白单元格）：使用 `replace` 动作，标注为 `{{teaching_content_analysis}}`

**❌ 错误示例**（绝对禁止）：
```json
{
  "cell_marker": "[[DOCX-CELL table=T0000 row=5 ...]]",  // 这是标题行！
  "action": "append",
  "result": "一、教学内容分析（...）\n\n{{teaching_content_analysis}}"  // 错误：把内容追加到标题后
}
```

**✅ 正确示例**：
```json
{
  "cell_marker": "[[DOCX-CELL table=T0000 row=6 ...]]",  // 这是内容行！
  "action": "replace",
  "result": "{{teaching_content_analysis}}"  // 正确：替换空白内容行
}
```

**如何判断**：查看 row 号，如果某行是标题（包含"一、""二、"等），下一行是空白单元格，则标注下一行！

### 3. 占位符命名
- 使用英文蛇形命名：`teacher_name`、`section_title`、`teaching_goal`
- 体现字段语义，避免通用名称如 `value_1`、`content_2`

## 📝 输出格式

请输出一个 JSON 对象（不要包含 Markdown 代码块标记）：

```
{
  "annotations": [
    {
      "location_type": "paragraph" 或 "table_cell",
      "block_id": "段落ID（段落必填）",
      "cell_marker": "完整单元格标记（表格单元格必填）",
      "action": "append" 或 "replace" 或 "insert_multiple",
      "placeholder": "占位符名称（snake_case）",
      "placeholders": ["占位符列表"（仅 insert_multiple）],
      "result": "插入占位符后的内容文本（仅内容部分，不包含 [[DOCX-CELL]] 等标记）",
      "reason": "标注理由（简要说明为什么标注这里）"
    }
  ]
}
```

**⚠️ 重要说明：`result` 字段格式**
- 对于**表格单元格**：`result` 字段应该只包含单元格的**内容文本**，不要包含 `[[DOCX-CELL]]` 标记
  - ✅ 正确示例：`"result": "{{title}}"`
  - ❌ 错误示例：`"result": "[[DOCX-CELL table=T0000...]] {{title}}"`
- 对于**段落**：`result` 字段包含插入占位符后的段落内容
  - ✅ 正确示例：`"result": "课程名称：{{course_name}}"`
- `cell_marker` 字段已经包含了完整的标记信息，所以 `result` 中不需要重复

## 🌟 关键提醒

1. **全面分析**：请分析整个模板，不要遗漏任何需要标注的位置
2. **数量参考**：教案模板通常有 50-150 个标注位置
3. **保持结构**：不要删除或修改 `[[DOCX-BLOCK]]` 和 `[[DOCX-CELL]]` 标记
4. **JSON 格式**：确保输出是合法的 JSON，所有字符串正确转义

"""

    # 添加知识库洞察（如果有）
    kb_section = ""
    if kb_insights and kb_insights.strip():
        kb_section = f"\n{kb_insights.strip()}\n\n"

    template_section = """## 📄 模板内容

以下是需要标注的模板（完整版本，请仔细分析每个部分）：

"""

    suffix = """

---

## 🚀 开始标注

请运用你的推理能力，按照以下步骤系统性地完成标注：

### Step 1: 分析文档结构
- 识别封面信息区域
- 识别表格区域
- 识别每个字段的含义

### Step 2: 识别标注位置
- 找出所有空白区域
- 找出所有示例内容
- 找出所有需要用户填写的字段

### Step 3: 生成标注方案
- 为每个位置创建语义化的占位符名称
- 确定合适的动作类型（append/replace/insert_multiple）
- 编写标注理由

### Step 4: 输出 JSON
- 按照上述格式输出完整的 JSON 对象
- 确保所有标注都包含在 annotations 数组中
- 不要包含任何额外的解释文字

现在，请开始分析并输出完整的 JSON 标注方案：
"""

    return prefix + kb_section + template_section + features_text + suffix

def create_json_repair_prompt(broken_json_text: str) -> str:
    """构建 JSON 修复提示词（简化版）"""
    return f"""# 任务：修复 JSON

以下是一个损坏的 JSON 文本，请修复它使其成为合法的 JSON 对象。

## 核心要求：
1. **保留所有数据**：不得删减 annotations 数组中的任何条目
2. **只修复语法**：补全括号、逗号、引号等，不要修改内容
3. **输出纯 JSON**：不要添加解释或 Markdown 标记

## 损坏的 JSON：
```
{broken_json_text}
```

请输出修复后的完整 JSON：
"""


def call_json_repair_llm(broken_json_text: str) -> str:
    """调用 Kimi LLM 来修复损坏的 JSON。"""

    # 只保留末尾片段以降低提示长度
    snippet = broken_json_text[-8000:] if len(broken_json_text) > 8000 else broken_json_text
    prompt = create_json_repair_prompt(snippet)

    messages = [
        {
            "role": "system",
            "content": (
                "你是一名严格的 JSON 修复专家。"
                "请利用你的推理能力分析 JSON 结构，修复语法错误，确保输出合法的 JSON。"
                "最终输出必须是一个对象，格式固定为：{\"annotations\": [...]}。"
                "**关键要求**：必须保留原始 JSON 中的所有 annotations 数组条目，不允许删减、简化或省略任何标注项。"
                "如果原始JSON有150个标注，修复后也必须有150个标注。只修复语法错误，不修改内容。"
            ),
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]

    print(f"↪️ 正在调用 JSON 修复模型 ({GITCODE_JSON_REPAIR_MODEL})...")
    print(f"   请求Token数: ~{len(prompt) // 4}")
    try:
        # 🔧 根据环境变量选择API
        if USE_FIREWORKS and HAS_FIREWORKS:
            # 使用Fireworks API
            response = fireworks_client.chat.completions.create(
                model=GITCODE_JSON_REPAIR_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=JSON_REPAIR_MAX_TOKENS,
            )
            content = _strip_code_blocks(response.choices[0].message.content or "")
        elif USE_QWEN and HAS_DASHSCOPE:
            # 使用通义千问 API
            from dashscope import Generation
            response = Generation.call(
                model=GITCODE_JSON_REPAIR_MODEL,
                messages=messages,
                temperature=0.3,
                result_format='message',
                max_tokens=JSON_REPAIR_MAX_TOKENS,
            )
            if response.status_code == 200:
                content = _strip_code_blocks(response.output.choices[0].message.content or "")
            else:
                raise Exception(f"Qwen API错误: {response.code} - {response.message}")
        else:
            # 使用Kimi API（默认）
            resp = _kimi_chat_completions(
                messages=messages,
                model=GITCODE_JSON_REPAIR_MODEL,
                temperature=0.3,
                max_tokens=JSON_REPAIR_MAX_TOKENS,
            )
            content = _strip_code_blocks(_extract_response_text(resp))
    except Exception as exc:
        print(f"ALERT JSON修复模型调用失败 {exc}")
        _bump_stat("json_repair_failures", 1)
        return ""

    if not content:
        print("❌ 错误：JSON修复模型无响应或返回为空")
        return ""

    print("✅ JSON修复模型响应成功")
    print(f"   响应长度: {len(content)} 字符")
    _log_token_usage(messages, content, GITCODE_JSON_REPAIR_MODEL)
    return content


def create_checker_prompt(response_text: str) -> str:
    """创建检查器 prompt（简化版）"""
    return (
        "请判断以下 JSON 是否完整（所有括号是否闭合）：\n\n"
        f"{response_text}\n\n"
        "如果完整，返回：{\"status\": \"complete\"}\n"
        "如果不完整，返回：{\"status\": \"continue\", \"reason\": \"原因\"}\n"
    )


def call_checker_llm(response_text: str) -> Dict[str, Any]:
    prompt = create_checker_prompt(response_text)
    messages = [
        {
            "role": "system",
            "content": "你是一名 JSON 输出检查器，负责判断回答是否包含完整且结束的 JSON。",
        },
        {"role": "user", "content": prompt},
    ]

    content = stream_gitcode_chat(
        messages,
        model=GITCODE_CHECKER_MODEL,
        max_tokens=2048,
        temperature=0.0,
    )

    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        return {"status": "continue", "reason": "无法解析检查器返回值"}


def main():
    """示例入口（推荐使用 docuagent/v4/run_llm_annotation.py 触发完整流程）"""

    print("\n" + "=" * 80)
    print("Kimi LLM 标注器 - 独立测试")
    print("=" * 80)
    print(f"\n使用模型：")
    print(f"  - 标注模型: {GITCODE_MODEL}")
    print(f"  - JSON修复模型: {GITCODE_JSON_REPAIR_MODEL}")
    print(f"  - 检查模型: {GITCODE_CHECKER_MODEL}")
    print(f"  - 生成模型: {GITCODE_GENERATION_MODEL}")
    print("\n💡 提示: 推荐使用 docuagent/v4/run_llm_annotation.py 运行完整流程")
    print("\n此脚本仅供测试 call_gitcode_llm 和 create_annotation_prompt 函数")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
