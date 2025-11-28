"""
AI文档编辑器 - 独立模块
AI Document Editor - Standalone Module

可直接集成到其他Flask项目中使用
"""

from .app import create_app, app
from .editor import editor_bp, EditorSession, SessionManager

__all__ = ['create_app', 'app', 'editor_bp', 'EditorSession', 'SessionManager']

__version__ = '1.0.0'
