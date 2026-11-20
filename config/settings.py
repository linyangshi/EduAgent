"""EduAgent settings. Export environment variables before starting a process."""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "")
GITCODE_API_KEY = os.getenv("GITCODE_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
KIMI_API_KEY = os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY", "")
PACKY_API_KEY = os.getenv("PACKY_API_KEY", "")
PACKY_GPT_API_KEY = os.getenv("PACKY_GPT_API_KEY", "")
PACKY_CLAUDE_KEY = os.getenv("PACKY_CLAUDE_KEY", "")
PACKY_GEMINI_KEY = os.getenv("PACKY_GEMINI_KEY", "")
SHENMA_API_KEY = os.getenv("SHENMA_API_KEY", "")
OPENAI_PROXY_BASE = os.getenv("OPENAI_PROXY_BASE", "")
GEMINI_THINKING_MODEL = os.getenv("GEMINI_THINKING_MODEL", "gemini-3-pro-preview")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
XINGHU_API_KEY = os.getenv("XINGHU_API_KEY", "")
SILICON_API_KEY = os.getenv("SILICON_API_KEY", "")

FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5029"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{PROJECT_ROOT / 'eduagent.db'}"
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("Set SECRET_KEY to a persistent random secret before starting EduAgent.")

MAIL_CONFIG = {
    "MAIL_SERVER": os.getenv("MAIL_SERVER", "localhost"),
    "MAIL_PORT": int(os.getenv("MAIL_PORT", "465")),
    "MAIL_USE_TLS": os.getenv("MAIL_USE_TLS", "false").lower() == "true",
    "MAIL_USE_SSL": os.getenv("MAIL_USE_SSL", "true").lower() == "true",
    "MAIL_USERNAME": os.getenv("MAIL_USERNAME", ""),
    "MAIL_PASSWORD": os.getenv("MAIL_PASSWORD", ""),
    "MAIL_DEFAULT_SENDER": os.getenv("MAIL_DEFAULT_SENDER") or os.getenv("MAIL_USERNAME", ""),
    "MAIL_MAX_EMAILS": int(os.getenv("MAIL_MAX_EMAILS", "100")),
    "MAIL_SUPPRESS_SEND": os.getenv("MAIL_SUPPRESS_SEND", "false").lower() == "true",
    "MAIL_ASCII_ATTACHMENTS": os.getenv("MAIL_ASCII_ATTACHMENTS", "false").lower() == "true",
}

WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "")
WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "")
WECHAT_CALLBACK_URL = os.getenv("WECHAT_CALLBACK_URL", "")
QQ_APP_ID = os.getenv("QQ_APP_ID", "")
QQ_APP_SECRET = os.getenv("QQ_APP_SECRET", "")
QQ_CALLBACK_URL = os.getenv("QQ_CALLBACK_URL", "")

MAX_CONTENT_LENGTH = 16 * 1024 * 1024
UPLOAD_FOLDER = PROJECT_ROOT / "uploads"
EXPORT_FOLDER = PROJECT_ROOT / "exports"
KNOWLEDGE_BASE_FOLDER = PROJECT_ROOT / "knowledge_base"
VECTOR_DB_FOLDER = PROJECT_ROOT / "vector_db"
for folder in (UPLOAD_FOLDER, EXPORT_FOLDER, KNOWLEDGE_BASE_FOLDER, VECTOR_DB_FOLDER):
    folder.mkdir(parents=True, exist_ok=True)

LLM_MODEL_OUTLINE = os.getenv("LLM_MODEL_OUTLINE", "qwen-plus")
LLM_MODEL_LESSON = os.getenv("LLM_MODEL_LESSON", "qwen-turbo")
VLM_MODEL = os.getenv("VLM_MODEL", "qwen-vl-plus")
MAX_CONCURRENT_ANNOTATE = int(os.getenv("MAX_CONCURRENT_ANNOTATE", "5"))
MAX_CONCURRENT_GENERATE = int(os.getenv("MAX_CONCURRENT_GENERATE", "10"))
BATCH_SIZE_GENERATE = int(os.getenv("BATCH_SIZE_GENERATE", "5"))
PARALLEL_VLM_REVIEW = os.getenv("PARALLEL_VLM_REVIEW", "true").lower() == "true"
