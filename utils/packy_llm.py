"""
OpenAI 代理 LLM 工厂

此前用于调用 PackyAPI 的包装器已经统一迁移到 OpenAI 兼容接口
（https://api.whatai.cc/v1）。该模块负责基于 LangChain 的 ChatOpenAI
创建可直接与核心 Agent 复用的模型实例。
"""

import os
from typing import Optional

from langchain_openai import ChatOpenAI

OPENAI_PROXY_BASE = os.getenv("OPENAI_PROXY_BASE", "https://api.whatai.cc/v1")


def create_packy_llm(
    model_name: str,
    api_key: str,
    *,
    base_url: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 12800,
) -> ChatOpenAI:
    """创建指向 OpenAI 兼容接口的 LangChain ChatOpenAI 实例。"""
    if not api_key:
        raise ValueError("OpenAI 代理 API Key 未配置")

    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=base_url or OPENAI_PROXY_BASE,
        temperature=temperature,
        max_tokens=max_tokens,
    )
