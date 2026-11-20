"""
LLM 调用工具 - 支持多种后端
可配置为 OpenAI 兼容接口或通义千问
"""

import os
from typing import Optional

import httpx

# 尝试从项目配置导入
try:
    from config.settings import DASHSCOPE_API_KEY as SETTINGS_API_KEY
    from config.settings import OPENAI_PROXY_BASE
    from config.settings import LLM_MODEL_OUTLINE
except ImportError:
    SETTINGS_API_KEY = None
    OPENAI_PROXY_BASE = None
    LLM_MODEL_OUTLINE = None

# 配置项 - 可通过环境变量覆盖
# 默认使用 DashScope (通义千问)，也可以配置为其他 OpenAI 兼容接口

# 确定默认 API URL
# 如果使用了 settings.py 中的 DASHSCOPE_API_KEY，则默认使用阿里云官方 URL
# 因为 DashScope Key 通常不适用于第三方 OpenAI 代理
_default_dashscope_url = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'

if SETTINGS_API_KEY:
    _default_api_url = _default_dashscope_url
else:
    _default_api_url = (OPENAI_PROXY_BASE + '/chat/completions') if OPENAI_PROXY_BASE else _default_dashscope_url

LLM_API_KEY = os.environ.get('LLM_API_KEY', os.environ.get('DASHSCOPE_API_KEY', SETTINGS_API_KEY or ''))
LLM_API_URL = os.environ.get('LLM_API_URL', _default_api_url)
LLM_MODEL = os.environ.get('LLM_MODEL', LLM_MODEL_OUTLINE or 'qwen-plus')


def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None
) -> str:
    """
    调用 LLM (OpenAI 兼容协议)

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        temperature: 温度参数
        max_tokens: 最大生成token数
        model: 模型名称 (可选，默认使用环境变量配置)
        api_key: API密钥 (可选，默认使用环境变量配置)
        api_url: API地址 (可选，默认使用环境变量配置)

    Returns:
        生成的文本
    """
    _api_key = api_key or LLM_API_KEY
    _api_url = api_url or LLM_API_URL
    _model = model or LLM_MODEL

    if not _api_key:
        raise RuntimeError("未配置 LLM_API_KEY 或 DASHSCOPE_API_KEY，无法调用 LLM。")

    headers = {
        'Authorization': f'Bearer {_api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    payload = {
        'model': _model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        'temperature': temperature,
        'max_tokens': max_tokens
    }

    transport = httpx.HTTPTransport(retries=3)

    try:
        with httpx.Client(
            transport=transport,
            timeout=60.0,
            trust_env=False,  # 忽略系统代理
        ) as client:
            response = client.post(_api_url, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"LLM 请求失败: {exc}") from exc

    data = response.json()
    try:
        return data['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"LLM 响应格式异常: {data}") from exc
