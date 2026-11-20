"""
OpenAI Proxy 集成
将原先的 PackyAPI 调用统一迁移到 OpenAI 兼容接口（https://api.whatai.cc/v1）
"""

import os
from typing import Dict, List, Optional, Iterator

try:
    from openai import OpenAI
    HAS_OPENAI_SDK = True
except ImportError:
    HAS_OPENAI_SDK = False

# 从 settings / 环境变量中读取代理配置
try:
    from config.settings import SHENMA_API_KEY as SETTINGS_PROXY_KEY, OPENAI_PROXY_BASE as SETTINGS_PROXY_BASE
except ImportError:
    SETTINGS_PROXY_KEY = ""
    SETTINGS_PROXY_BASE = "https://api.whatai.cc/v1"

OPENAI_PROXY_BASE = os.getenv("OPENAI_PROXY_BASE", SETTINGS_PROXY_BASE)
PACKY_API_TOKEN = (
    os.getenv("SHENMA_API_KEY")
    or SETTINGS_PROXY_KEY
    or ""
)

# 检查token是否已配置
HAS_PACKY_API = bool(HAS_OPENAI_SDK and PACKY_API_TOKEN)
_openai_client = OpenAI(api_key=PACKY_API_TOKEN, base_url=OPENAI_PROXY_BASE) if HAS_PACKY_API else None


def _extract_content(content_value):
    """兼容 OpenAI v1 响应中字符串或数组格式的 content 字段。"""
    if isinstance(content_value, list):
        parts = []
        for item in content_value:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    return content_value or ""

def call_packy_api(
    prompt: str,
    model: str = "gpt-5.1-2025-11-13",
    temperature: float = 0.7,
    max_tokens: int = 4000,
    system_prompt: Optional[str] = None
) -> str:
    """
    调用 OpenAI 兼容接口（Whatai）上的 GPT-5.1 2025 模型

    Args:
        prompt: 用户提示词
        model: 模型名称，默认 gpt-5.1-2025-11-13
        temperature: 温度参数
        max_tokens: 最大token数
        system_prompt: 系统提示词（可选）

    Returns:
        str: 模型生成的文本
    """
    if not HAS_PACKY_API:
        raise ValueError(
            "❌ OpenAI兼容接口未配置。请设置 SHENMA_API_KEY 或安装 openai 包。"
        )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = _openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response.choices:
            raw_content = response.choices[0].message.content
            return _extract_content(raw_content).strip()
        raise ValueError(f"❌ OpenAI兼容接口响应异常: {response}")
    except Exception as exc:
        raise ValueError(f"❌ OpenAI兼容接口调用失败: {exc}") from exc


def stream_packy_api(
    prompt: str,
    model: str = "gpt-5.1-2025-11-13",
    temperature: float = 0.7,
    max_tokens: int = 4000,
    system_prompt: Optional[str] = None
) -> Iterator[str]:
    """
    流式调用 OpenAI 兼容接口

    Args:
        prompt: 用户提示词
        model: 模型名称
        temperature: 温度参数
        max_tokens: 最大token数
        system_prompt: 系统提示词（可选）

    Yields:
        str: 生成的文本片段
    """
    if not HAS_PACKY_API:
        raise ValueError(
            "❌ OpenAI兼容接口未配置。请设置 SHENMA_API_KEY 或安装 openai 包。"
        )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        stream = _openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                extracted = _extract_content(content)
                if extracted:
                    yield extracted
    except Exception as exc:
        raise ValueError(f"❌ OpenAI兼容接口流式调用失败: {exc}") from exc


def get_available_models() -> List[Dict[str, str]]:
    """
    获取可用的模型列表

    Returns:
        List[Dict]: 模型列表，每个模型包含id和display_name
    """
    models = [
        {
            "id": "gpt-5.1-2025-11-13",
            "display_name": "GPT-5.1 2025-11-13",
            "provider": "OpenAI Proxy (Whatai)",
            "max_tokens": 8000,
            "description": "OpenAI 兼容接口 - GPT-5.1 (2025-11-13) 思考模型"
        }
    ]
    return models if HAS_PACKY_API else []
