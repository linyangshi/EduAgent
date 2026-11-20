
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import DASHSCOPE_API_KEY, VECTOR_DB_FOLDER, KNOWLEDGE_BASE_FOLDER
from services.knowledge_base_service import KnowledgeBaseService

print(f"DASHSCOPE_API_KEY: configured={bool(DASHSCOPE_API_KEY)}")
print(f"VECTOR_DB_FOLDER: {VECTOR_DB_FOLDER}")
print(f"KNOWLEDGE_BASE_FOLDER: {KNOWLEDGE_BASE_FOLDER}")

try:
    kb_service = KnowledgeBaseService(
        vector_db_path=str(VECTOR_DB_FOLDER),
        kb_folder=str(KNOWLEDGE_BASE_FOLDER),
        api_key=DASHSCOPE_API_KEY,
        embedding_provider='qwen',
        embedding_model_name='text-embedding-v4'
    )
    print("✅ KnowledgeBaseService initialized successfully.")
except Exception as e:
    print(f"❌ KnowledgeBaseService initialization failed: {e}")
    import traceback
    traceback.print_exc()
