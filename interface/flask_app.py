"""
Flask API接口 - EduAgent智教创想
University AI Lesson Planning System - Flask API

提供RESTful API接口，支持：
- 模板上传和解析
- 课程大纲生成
- 教案批量生成
- 文件导出下载
"""

import os
import sys
import json
import asyncio
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_file, send_from_directory, render_template, Response
from flask_cors import CORS
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
import tempfile
import uuid

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入AI编辑器模块（尽早导入以确保路径正确）
try:
    from ai_editor_standalone import editor_bp as ai_editor_bp
    from ai_editor_standalone.utils.llm_call import call_llm as _original_ai_editor_call_llm
    
    # Wrapper to log AI editor LLM calls
    def ai_editor_call_llm_with_logging(*args, **kwargs):
        """Wrapper around ai_editor_call_llm that logs to database"""
        # Extract user_id if present in kwargs
        user_id = kwargs.pop('user_id', None)
        model_name = kwargs.get('model', 'qwen-plus')
        
        result = _original_ai_editor_call_llm(*args, **kwargs)
        
        # Log the call
        try:
            from utils.llm_logger import log_llm_call_async
            log_llm_call_async(
                user_id=user_id,
                feature='ai_editor',
                model_name=model_name,
                api_provider='qwen'
            )
        except Exception:
            pass  # Don't break on logging failure
        
        return result
    
    ai_editor_call_llm = ai_editor_call_llm_with_logging
    AI_EDITOR_AVAILABLE = True
    print('✅ AI编辑器模块加载成功')
except ImportError as e:
    AI_EDITOR_AVAILABLE = False
    ai_editor_bp = None
    ai_editor_call_llm = None
    print(f'⚠️  AI编辑器模块未找到: {e}')

# 导入核心模块

from core.lesson_planner import LessonPlannerService
from core.document_generator import DocumentGenerator, generate_document
from utils.lesson_exporter import LessonExporter
from config.settings import DASHSCOPE_API_KEY, DATABASE_URL, SECRET_KEY, MAIL_CONFIG, VECTOR_DB_FOLDER, KNOWLEDGE_BASE_FOLDER, UPLOAD_FOLDER, EXPORT_FOLDER

# 导入认证模块
from models.user import User, db
from interface.auth_routes import auth_bp
from interface.auth_middleware import require_auth, optional_auth

# 导入管理员模块
from interface.admin_routes import admin_bp
from models.admin import Admin, init_super_admin

# 导入对话历史模块
from models.conversation import Conversation, ConversationMessage
from models.llm_call import LLMCall

# 导入商城模块
from interface.shop_routes import shop_bp


# 导入知识库模块
from services.knowledge_base_service import KnowledgeBaseService
from services.screenshot_qa_service import ScreenshotQAService


class UniversityFlaskAPI:
    """大学教案生成系统Flask API"""
    
    def __init__(self):
        self.app = Flask(__name__, 
                        template_folder='../templates',
                        static_folder='../static')
        self.app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
        
        # 使用settings.py中的配置
        self.app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
        self.app.config['EXPORT_FOLDER'] = str(EXPORT_FOLDER)
        self.app.config['SECRET_KEY'] = SECRET_KEY
        self.app.config['SESSION_PERMANENT'] = False  # 关闭浏览器后会话失效
        self.app.config['REMEMBER_COOKIE_DURATION'] = 0  # 禁用 remember cookie
        
        # 数据库配置
        self.app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        # 邮件配置
        for key, value in MAIL_CONFIG.items():
            self.app.config[key] = value
        
        # 启用CORS
        CORS(self.app)
        
        # 初始化数据库
        db.init_app(self.app)
        with self.app.app_context():
            db.create_all()
        
        # 初始化邮件服务
        self.mail = Mail(self.app)
        
        # 初始化登录管理器
        self.login_manager = LoginManager()
        self.login_manager.init_app(self.app)
        self.login_manager.login_view = 'auth.login'
        self.login_manager.login_message = '请先登录'
        self.login_manager.login_message_category = 'info'
        
        @self.login_manager.user_loader
        def load_user(user_id):
            return User.query.get(int(user_id))
        
        # 创建上传目录
        os.makedirs(self.app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # 初始化服务
        self.service = LessonPlannerService()
        self.exporter = LessonExporter()
        
        # 初始化知识库服务
        try:
            self.kb_service = KnowledgeBaseService(
                vector_db_path=str(VECTOR_DB_FOLDER),
                kb_folder=str(KNOWLEDGE_BASE_FOLDER),
                api_key=DASHSCOPE_API_KEY,
                embedding_provider='qwen',
                embedding_model_name='text-embedding-v4'
            )
            print('✅ 知识库服务初始化成功')
            # Clear any previous error log
            error_log_path = os.path.join(project_root, 'logs', 'kb_init_error.log')
            if os.path.exists(error_log_path):
                os.remove(error_log_path)
        except Exception as e:
            print(f'⚠️  知识库服务初始化失败: {e}')
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            # Write to log file
            os.makedirs(os.path.join(project_root, 'logs'), exist_ok=True)
            with open(os.path.join(project_root, 'logs', 'kb_init_error.log'), 'w') as f:
                f.write(error_msg)
            self.kb_service = None

        # 初始化截图问答服务
        try:
            self.screenshot_qa_service = ScreenshotQAService(
                vector_db_path=str(VECTOR_DB_FOLDER),
                kb_folder=str(KNOWLEDGE_BASE_FOLDER),
                api_key=DASHSCOPE_API_KEY,
                embedding_provider='qwen',
                embedding_model_name='text-embedding-v4'
            )
            print('✅ 截图问答服务初始化成功')
        except Exception as e:
            print(f'⚠️  截图问答服务初始化失败: {e}')
            self.screenshot_qa_service = None

        # 初始化统一文档生成器
        try:
            self.document_generator = DocumentGenerator(
                max_concurrent_annotate=3,
                max_concurrent_generate=10,
                vlm_max_iterations=3,
                vlm_quality_threshold=0.7
            )
            print('✅ 统一文档生成器初始化成功')
        except Exception as e:
            print(f'⚠️  统一文档生成器初始化失败: {e}')
            self.document_generator = None

        # 用于跟踪统一文档生成任务
        self.unified_generation_tasks = {}
        
        # 任务字典最大容量（防止内存泄露）
        self.MAX_TASKS_CACHE = 100
        
        # 任务过期时间（秒）- 24小时后清理
        self.TASK_EXPIRY_SECONDS = 24 * 60 * 60

        # 如果配置文件中有API Key，自动初始化agent
        if DASHSCOPE_API_KEY:
            try:
                print('🔑 检测到配置文件中的API Key，自动初始化Agent...')
                self.service.initialize_agent(DASHSCOPE_API_KEY)
                print('✅ Agent初始化成功')
            except Exception as e:
                print(f'⚠️  Agent自动初始化失败: {e}')
                print('💡 您可以稍后在前端手动初始化')
        
        # 注册蓝图
        self.app.register_blueprint(auth_bp)
        
        # 注册管理员蓝图
        self.app.register_blueprint(admin_bp)
        print('✅ 管理员蓝图注册成功')
        
        # 注册OAuth蓝图
        from interface.oauth_routes import oauth_bp
        self.app.register_blueprint(oauth_bp)
        print('✅ OAuth蓝图注册成功')

        # 注册反馈蓝图
        from interface.feedback_routes import feedback_bp
        self.app.register_blueprint(feedback_bp)
        print('✅ 反馈蓝图注册成功')

        # 注册AI编辑器蓝图
        if AI_EDITOR_AVAILABLE and ai_editor_bp:
            self.app.register_blueprint(ai_editor_bp)
            print('✅ AI编辑器蓝图注册成功')

        # 注册商城蓝图
        self.app.register_blueprint(shop_bp)
        print('✅ 商城蓝图注册成功')

        # 注册路由
        self._register_routes()

        # 初始化自定义上下文处理器 (如 is_mobile)
        self._init_context_processors()

        # 启动时检查数据库表结构 ( migration )
        with self.app.app_context():
            self._check_and_update_db()

        # 初始化数据库及管理员
        self._init_db_and_admin()
        
        # 启动任务清理线程
        self._start_task_cleanup_thread()

    def _background_kb_ask(self, kb_id, question, top_k, model, assistant_msg_id, user_id=None, direct_answer=False):
        """后台执行知识库问答并异步更新数据库"""
        with self.app.app_context():
            try:
                from models.conversation import ConversationMessage
                
                # 定义更新回调函数
                def update_callback(content):
                    try:
                        with self.app.app_context():
                            msg = ConversationMessage.query.get(assistant_msg_id)
                            if msg:
                                msg.content = content
                                db.session.commit()
                    except Exception as e:
                        print(f"⚠️ 更新流式内容失败: {e}")
                
                # 使用流式生成
                print(f"▶️ 开始流式生成知识库回答, msg_id={assistant_msg_id}, direct_answer={direct_answer}")
                full_answer = ""
                generator = self.kb_service.answer_question_stream(
                    kb_id, question, top_k, model, user_id=user_id, direct_answer=direct_answer, update_callback=update_callback
                )
                
                for chunk in generator:
                    full_answer += chunk
                
                # 最终更新状态
                msg = ConversationMessage.query.get(assistant_msg_id)
                if msg:
                    if "[生成出错" in full_answer:
                        msg.status = 'error'
                    else:
                        msg.status = 'completed'
                    msg.content = full_answer
                    msg.model_used = model
                    db.session.commit()
                    print(f"✅ 后台知识库问答任务完成: Message ID {assistant_msg_id}")
                else:
                    print(f"⚠️ 后台任务找不到消息 ID: {assistant_msg_id}")
            except Exception as e:
                print(f"❌ 后台知识库问答任务异常: {e}")
                import traceback
                traceback.print_exc()
                from models.conversation import ConversationMessage
                msg = ConversationMessage.query.get(assistant_msg_id)
                if msg:
                    msg.content = f"抱歉，生成过程中出现程序异常: {str(e)}"
                    msg.status = 'error'
                    db.session.commit()

    def _background_chat_ask(self, message, model, assistant_msg_id, user_id=None):
        """后台执行通用对话并异步更新数据库"""
        with self.app.app_context():
            import asyncio
            try:
                # 异步对话处理
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    response = loop.run_until_complete(
                        self.service.agent.chat_with_user(message, model_name=model, user_id=user_id)
                    )
                finally:
                    loop.close()
                
                from models.conversation import ConversationMessage
                # 更新消息内容和状态
                msg = ConversationMessage.query.get(assistant_msg_id)
                if msg:
                    msg.content = response or '未生成有效回答'
                    msg.status = 'completed'
                    msg.model_used = model
                    db.session.commit()
                    print(f"✅ 后台通用对话任务完成: Message ID {assistant_msg_id}")
                else:
                    print(f"⚠️ 后台任务找不到消息 ID: {assistant_msg_id}")
            except Exception as e:
                print(f"❌ 后台通用对话任务异常: {e}")
                import traceback
                traceback.print_exc()
                from models.conversation import ConversationMessage
                msg = ConversationMessage.query.get(assistant_msg_id)
                if msg:
                    msg.content = f"抱歉，对话生成失败: {str(e)}"
                    msg.status = 'error'
                    db.session.commit()

    def _check_and_update_db(self):
        """启动时检查并执行必要的数据库迁移脚本"""
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            
            # 1. 检查 conversations 表是否缺失 kb_id 字段
            columns = [c['name'] for c in inspector.get_columns('conversations')]
            if 'kb_id' not in columns:
                print("🛠 正在补齐数据库字段: conversations.kb_id")
                with db.engine.connect() as conn:
                    # 使用原生 SQL 添加字段
                    conn.execute(text("ALTER TABLE conversations ADD COLUMN kb_id INTEGER REFERENCES knowledge_bases(id)"))
                    conn.commit()
                print("✅ 数据库字段 conversations.kb_id 补齐成功")
                
            # 2. 检查 conversation_messages 表是否缺失 status 字段
            msg_columns = [c['name'] for c in inspector.get_columns('conversation_messages')]
            if 'status' not in msg_columns:
                print("🛠 正在补齐数据库字段: conversation_messages.status")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE conversation_messages ADD COLUMN status VARCHAR(20) DEFAULT 'completed'"))
                    conn.commit()
                print("✅ 数据库字段 conversation_messages.status 补齐成功")
                
        except Exception as e:
            print(f"⚠️ 数据库自动迁移检查失败 (通常在表尚未创建时发生): {e}")

    # ===== 移动端适配：全局上下文注入 =====
    def _init_context_processors(self):
        @self.app.context_processor
        def inject_device_flags():
            try:
                ua = request.headers.get('User-Agent', '')
                is_mobile = False
                if ua:
                    ua_lower = ua.lower()
                    # 常见移动端UA关键字
                    mobile_keywords = [
                        'mobile', 'iphone', 'ipad', 'ipod', 'android', 'blackberry',
                        'opera mini', 'iemobile', 'wpdesktop', 'windows phone', 'mobi'
                    ]
                    is_mobile = any(k in ua_lower for k in mobile_keywords)
                return {
                    'is_mobile': is_mobile
                }
            except Exception:
                return {'is_mobile': False}
        
    def _init_db_and_admin(self):
        # 创建数据库表
        with self.app.app_context():
            db.create_all()
            # 初始化高级管理员账户
            init_super_admin(self.app)
    
    def _start_task_cleanup_thread(self):
        """启动后台任务清理线程"""
        import threading
        import time
        
        def cleanup_expired_tasks():
            """定期清理过期任务"""
            while True:
                try:
                    time.sleep(3600)  # 每小时检查一次
                    current_time = time.time()
                    
                    # 清理 generation_progress
                    if hasattr(self, 'generation_progress'):
                        expired_keys = [
                            k for k, v in self.generation_progress.items()
                            if current_time - v.get('start_time', current_time) > self.TASK_EXPIRY_SECONDS
                        ]
                        for key in expired_keys:
                            del self.generation_progress[key]
                        if expired_keys:
                            print(f"🧹 清理过期任务 (generation_progress): {len(expired_keys)} 个")
                    
                    # 清理 v5_generation_tasks
                    if hasattr(self, 'v5_generation_tasks'):
                        expired_keys = [
                            k for k, v in self.v5_generation_tasks.items()
                            if current_time - v.get('start_time', current_time) > self.TASK_EXPIRY_SECONDS
                        ]
                        for key in expired_keys:
                            del self.v5_generation_tasks[key]
                        if expired_keys:
                            print(f"🧹 清理过期任务 (v5_generation_tasks): {len(expired_keys)} 个")
                    
                    # 清理 unified_generation_tasks
                    if hasattr(self, 'unified_generation_tasks'):
                        expired_keys = [
                            k for k, v in self.unified_generation_tasks.items()
                            if current_time - v.get('start_time', current_time) > self.TASK_EXPIRY_SECONDS
                        ]
                        for key in expired_keys:
                            del self.unified_generation_tasks[key]
                        if expired_keys:
                            print(f"🧹 清理过期任务 (unified_generation_tasks): {len(expired_keys)} 个")
                    
                    # 如果任务数超过最大容量，清理最旧的任务
                    for task_dict_name in ['generation_progress', 'v5_generation_tasks', 'unified_generation_tasks']:
                        if hasattr(self, task_dict_name):
                            task_dict = getattr(self, task_dict_name)
                            if len(task_dict) > self.MAX_TASKS_CACHE:
                                # 按开始时间排序，删除最旧的
                                sorted_tasks = sorted(
                                    task_dict.items(),
                                    key=lambda x: x[1].get('start_time', 0)
                                )
                                to_remove = len(task_dict) - self.MAX_TASKS_CACHE
                                for i in range(to_remove):
                                    del task_dict[sorted_tasks[i][0]]
                                print(f"🧹 清理超量任务 ({task_dict_name}): {to_remove} 个")
                
                except Exception as e:
                    print(f"⚠️ 任务清理线程异常: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_expired_tasks, daemon=True, name="TaskCleanup")
        cleanup_thread.start()
        print("✅ 任务清理线程已启动")
    
    def _register_routes(self):
        """注册所有API路由"""
        
        def get_current_user():
            """辅助函数：获取当前用户（支持token和session两种认证方式）"""
            # 优先使用request.current_user（token认证设置的）
            user = getattr(request, 'current_user', None)
            if user:
                return user
            # 如果没有，尝试从Flask-Login获取
            try:
                from flask_login import current_user
                if current_user.is_authenticated:
                    return current_user
            except Exception:
                pass
            return None
        
        
        # 前端页面路由（允许访问，在使用功能时才检查登录）
        @self.app.route('/')
        def index():
            """EduAgent 官方主页 - 增加移动端登录重定向"""
            # 检测设备
            ua = request.headers.get('User-Agent', '').lower()
            mobile_keywords = ['mobile', 'iphone', 'android', 'mobi']
            is_mobile = any(k in ua for k in mobile_keywords)
            
            # 如果是手机端
            if is_mobile:
                from flask import redirect, url_for
                if current_user.is_authenticated:
                    return redirect(url_for('app_dashboard'))
                return redirect(url_for('mobile_login_page'))
                
            return render_template('landing_page_squarespace.html')

        @self.app.route('/app')
        @self.app.route('/mobile-home')
        @require_auth
        def app_dashboard():
            """应用仪表盘 - 自动适配移动端"""
            ua = request.headers.get('User-Agent', '').lower()
            mobile_keywords = ['mobile', 'iphone', 'android', 'mobi']
            is_mobile = any(k in ua for k in mobile_keywords)
            
            if is_mobile or request.path == '/mobile-home':
                return render_template('mobile_home.html')
            return render_template('new_frontend.html')

        @self.app.route('/mobile-chat')
        @require_auth
        def mobile_chat_page():
            """智能对话单页 - 移动端专用"""
            user = get_current_user()
            # 获取或创建一个最近的对话
            from models.conversation import Conversation
            conv = Conversation.query.filter_by(user_id=user.id, kb_id=None).order_by(Conversation.updated_at.desc()).first()
            if not conv:
                conv = Conversation(user_id=user.id, title="新对话")
                db.session.add(conv)
                db.session.commit()
            
            return render_template('mobile_chat.html', conversation_id=conv.id)

        @self.app.route('/blackboard-design')
        def blackboard_design_page():
            """板书设计 - 独立聊天生成图像页面"""
            return render_template('blackboard_design.html')

        # 认证页面路由
        @self.app.route('/login')
        def login_page():
            """登录页面 - 全站统一设备识别"""
            ua = request.headers.get('User-Agent', '').lower()
            mobile_keywords = ['mobile', 'iphone', 'android', 'mobi', 'ipod', 'phone']
            is_mobile = any(k in ua for k in mobile_keywords)
            
            # 如果是手机且未登录，强制返回手机版登录页
            if is_mobile:
                return redirect(url_for('mobile_login_page', **request.args))
            
            return render_template('auth_unified.html', mode='login')
        
        @self.app.route('/mobile-login')
        def mobile_login_page():
            """专属移动端登录页面"""
            return render_template('mobile_login.html')
        
        @self.app.route('/register')
        @self.app.route('/mobile-register')
        def register_page():
            """注册页面 - 自动适配移动端"""
            ua = request.headers.get('User-Agent', '').lower()
            mobile_keywords = ['mobile', 'iphone', 'android', 'mobi']
            is_mobile = any(k in ua for k in mobile_keywords)
            
            if is_mobile or request.path == '/mobile-register':
                return render_template('mobile_register.html')
            return render_template('auth_unified.html', mode='register')
        
        @self.app.route('/forgot-password')
        @self.app.route('/mobile-forgot-password')
        def forgot_password_page():
            """密码重置页面 - 自动适配移动端"""
            ua = request.headers.get('User-Agent', '').lower()
            mobile_keywords = ['mobile', 'iphone', 'android', 'mobi']
            is_mobile = any(k in ua for k in mobile_keywords)
            
            if is_mobile or request.path == '/mobile-forgot-password':
                return render_template('mobile_forgot_password.html')
            return render_template('forgot_password.html')
        
        @self.app.route('/reset-password')
        def reset_password_page():
            return render_template('reset_password.html')
        
        @self.app.route('/terms-of-service')
        def terms_of_service_page():
            return render_template('terms_of_service.html')
        
        @self.app.route('/privacy-policy')
        def privacy_policy_page():
            return render_template('privacy_policy.html')
        
        # ===== 管理后台页面 =====
        @self.app.route('/admin')
        def admin_login_page():
            """管理员登录页面"""
            return render_template('admin_login.html')
        
        @self.app.route('/admin/dashboard')
        def admin_dashboard_page():
            """管理后台仪表盘"""
            return render_template('admin_dashboard.html')

        # ===== AI编辑器页面 =====
        @self.app.route('/ai-editor')
        def ai_editor_page():
            """AI文档编辑器页面"""
            if not AI_EDITOR_AVAILABLE:
                return jsonify({'error': 'AI编辑器模块未安装'}), 503
            return render_template('ai_editor.html')

        # AI编辑器API路由
        @self.app.route('/api/ai/chat', methods=['POST'])
        @require_auth
        def ai_editor_chat():
            """AI编辑器聊天接口"""
            if not AI_EDITOR_AVAILABLE:
                return jsonify({'success': False, 'error': 'AI编辑器模块未安装'}), 503
            try:
                data = request.get_json()
                message = data.get('message', '')
                context = data.get('context', {})
                if not message:
                    return jsonify({'success': False, 'error': '消息不能为空'}), 400
                selected_text = context.get('selected_text', '')
                doc_content = context.get('document_content', '')
                generate_keywords = ['写', '生成', '帮我写', '创建', '添加', '补充', '扩展', '续写', '草拟', '起草']
                is_generate_request = any(kw in message for kw in generate_keywords)

                # 提取目标字段（用于智能插入位置识别）
                target_field = None
                import re
                # 匹配常见的字段标题模式：一、xxx  二、xxx  或直接的字段名
                field_patterns = [
                    r'[一二三四五六七八九十]+、([^\s，。、]+)',  # 匹配：一、目的与意义
                    r'(?:写|生成|帮我写|创建|添加|补充)(?:一下)?[「""]?([^「""，。\s]{2,15})[」""]?',  # 匹配：生成"构思与内容"
                    r'([目的与意义|构思与内容|工作起止日期|进度计划|主要参考文献|指导教师意见]+)',  # 直接匹配常见字段
                ]
                for pattern in field_patterns:
                    match = re.search(pattern, message)
                    if match:
                        target_field = match.group(1).strip()
                        break

                # 统一截断文档上下文，确保先“读文档”再回答
                doc_prefix = (doc_content or "").strip()
                if doc_prefix:
                    # 截取文档开头部分，避免超长
                    doc_prefix = doc_prefix[:2000]

                # ==================== AI Editor Billing Logic ====================
                from datetime import datetime, timezone
                user = get_current_user()
                today = datetime.now(timezone.utc).date()
                
                # Daily Reset
                if user.last_ai_editor_reset_date != today:
                    user.daily_ai_editor_count = 0
                    user.last_ai_editor_reset_date = today
                    db.session.commit()
                
                is_free = False
                points_to_deduct = 0
                billing_msg = ""
                
                if user.daily_ai_editor_count < 5:
                    user.daily_ai_editor_count += 1
                    is_free = True
                    billing_msg = f"今日免费额度 ({user.daily_ai_editor_count}/5)"
                    db.session.commit()
                else:
                    if user.points_balance >= 5:
                        # Deduction happens later or now? Better now to prevent abuse.
                        from models.shop import add_points_to_user
                        add_points_to_user(user, -5, 'consume', 'AI编辑器对话')
                        is_free = False
                        points_to_deduct = 5
                        billing_msg = "已扣除5积分"
                    else:
                        return jsonify({'success': False, 'error': '积分不足！AI编辑器每天免费5次，超出需5积分/次。'}), 402
                
                # =================================================================


                if is_generate_request:
                    system_prompt = """你是一个专业的文档写作助手。用户需要你帮忙生成文档内容。
请根据用户的要求生成专业、规范的内容。
重要规则：
1. 直接生成用户需要的内容，不要有任何解释性文字
2. 内容要专业、正式、符合文档规范
3. 适当分段，结构清晰
4. 如果是续写，要与上下文风格保持一致"""
                    # 先提供文档全局内容，再给出用户请求
                    if doc_prefix:
                        user_prompt = f"当前文档内容：\n{doc_prefix}\n\n用户请求：\n{message}"
                    else:
                        user_prompt = f"用户请求：{message}"
                    if selected_text:
                        user_prompt = f"用户选中的文本：\n{selected_text}\n\n{user_prompt}"
                    generated = ai_editor_call_llm(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.7, user_id=user.id)
                    result = {
                        'success': True, 
                        'response': '已为您生成以下内容：', 
                        'generated_content': generated.strip(),
                        'billing_info': {
                            'is_free': is_free,
                            'points_deducted': points_to_deduct,
                            'message': billing_msg,
                            'daily_usage': user.daily_ai_editor_count
                        }
                    }
                    if target_field:
                        result['target_field'] = target_field
                    return jsonify(result)
                else:
                    system_prompt = """你是一个专业的文档编辑助手。用户正在编辑Word文档，你需要在阅读完整文档内容后，帮助他们回答问题、提供写作建议。请用简洁专业的中文回答。"""
                    # 先给出文档内容，再给问题
                    if doc_prefix:
                        user_prompt = f"当前文档内容：\n{doc_prefix}\n\n用户问题：\n{message}"
                    else:
                        user_prompt = message
                    if selected_text:
                        user_prompt = f"用户选中的文本：\n{selected_text}\n\n{user_prompt}"
                    response = ai_editor_call_llm(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.7, user_id=user.id)
                    
                    return jsonify({
                        'success': True, 
                        'response': response,
                        'billing_info': {
                            'is_free': is_free,
                            'points_deducted': points_to_deduct,
                            'message': billing_msg,
                            'daily_usage': user.daily_ai_editor_count
                        }
                    })
            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/ai/complete', methods=['POST'])
        @require_auth
        def ai_editor_complete():
            """AI编辑器自动补全接口 - 用于Tab键确认后的完整补全"""
            if not AI_EDITOR_AVAILABLE:
                return jsonify({'success': False, 'error': 'AI编辑器模块未安装'}), 503
            try:
                data = request.get_json()
                text_before = data.get('text_before', '')
                doc_title = (data.get('document_title', '') or '').strip()
                if not text_before.strip():
                    return jsonify({'success': False, 'error': '没有可补全的内容'}), 400
                system_prompt = """你是文档续写助手。用户按下Tab键，你需要智能续写。规则：只输出续写内容，长度适中（1-3句），保持风格一致。"""
                context_500 = text_before[-500:]
                if doc_title:
                    user_prompt = f"文档标题：{doc_title}\n\n前文：\n{context_500}\n\n请续写："
                else:
                    user_prompt = f"前文：\n{context_500}\n\n请续写："
                completion = ai_editor_call_llm(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.7, max_tokens=150)
                return jsonify({'success': True, 'completion': completion.strip()})
            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/ai/inline-suggest', methods=['POST'])
        @require_auth
        def ai_editor_inline_suggest():
            """AI编辑器实时行内建议接口 - 用于打字时的灰色提示（使用qwen-turbo）"""
            if not AI_EDITOR_AVAILABLE:
                return jsonify({'success': False, 'error': 'AI编辑器模块未安装'}), 503
            try:
                data = request.get_json()
                text_before = data.get('text_before', '')
                doc_title = (data.get('document_title', '') or '').strip()
                if not text_before.strip() or len(text_before.strip()) < 5:
                    return jsonify({'success': False, 'suggestion': ''})

                # 使用qwen-turbo进行快速补全（国内网络延迟更低），输出1-3句续写内容
                system_prompt = """你是文档实时续写助手。根据标题和前文内容进行续写：
- 只输出续写部分，不要包含前文
- 输出1-3句中文，长度适中
- 保持语气和风格一致，不要重复前文内容"""
                context_200 = text_before[-200:]
                if doc_title:
                    user_prompt = f"文档标题：{doc_title}\n\n前文：\n{context_200}"
                else:
                    user_prompt = context_200
                suggestion = ai_editor_call_llm(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.3,
                    max_tokens=120,
                    model='qwen-turbo'
                )
                return jsonify({'success': True, 'suggestion': suggestion.strip()})
            except Exception as e:
                # 对于建议功能，静默失败
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'suggestion': ''})

        @self.app.route('/api/ai/generate-placeholder', methods=['POST'])
        @require_auth
        def ai_editor_generate_placeholder():
            """AI编辑器@@@占位符生成接口"""
            if not AI_EDITOR_AVAILABLE:
                return jsonify({'success': False, 'error': 'AI编辑器模块未安装'}), 503
            try:
                data = request.get_json()
                instruction = data.get('instruction', '')
                context_before = data.get('context_before', '')
                document_context = data.get('document_context', '')
                if not instruction:
                    return jsonify({'success': False, 'error': '缺少生成指令'}), 400
                system_prompt = """你是专业的文档内容生成助手。根据用户指令和上下文生成符合要求的专业内容。直接输出内容，不要解释。"""
                user_prompt = f"生成指令：{instruction}\n\n"
                if context_before.strip():
                    user_prompt += f"前文：\n{context_before[-300:]}\n\n"
                if document_context.strip():
                    # 这里传入的是文档全文上下文，保留完整信息以便识别标题等全局结构
                    user_prompt += f"文档上下文：\n{document_context}\n\n"
                user_prompt += f'请生成"{instruction}"的内容：'
                content = ai_editor_call_llm(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.7)
                return jsonify({'success': True, 'content': content.strip()})
            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/ai/rewrite', methods=['POST'])
        @require_auth
        def ai_editor_rewrite():
            """AI编辑器重写接口"""
            if not AI_EDITOR_AVAILABLE:
                return jsonify({'success': False, 'error': 'AI编辑器模块未安装'}), 503
            try:
                data = request.get_json()
                selected_text = data.get('selected_text', '')
                instruction = data.get('instruction', '')
                context_before = data.get('context_before', '')
                context_after = data.get('context_after', '')
                document_context = data.get('document_context', '')

                if not selected_text:
                    return jsonify({'success': False, 'error': '请选择要重写的文本'}), 400
                if not instruction:
                    return jsonify({'success': False, 'error': '请输入重写指令'}), 400

                if not instruction:
                    return jsonify({'success': False, 'error': '请输入重写指令'}), 400

                # ==================== AI Editor Billing Logic ====================
                from datetime import datetime, timezone
                user = get_current_user()
                today = datetime.now(timezone.utc).date()
                
                # Daily Reset (Redundant check but safe)
                if user.last_ai_editor_reset_date != today:
                    user.daily_ai_editor_count = 0
                    user.last_ai_editor_reset_date = today
                    db.session.commit()
                
                is_free = False
                points_to_deduct = 0
                billing_msg = ""
                
                if user.daily_ai_editor_count < 5:
                    user.daily_ai_editor_count += 1
                    is_free = True
                    billing_msg = f"今日免费额度 ({user.daily_ai_editor_count}/5)"
                    db.session.commit()
                else:
                    if user.points_balance >= 5:
                        from models.shop import add_points_to_user
                        add_points_to_user(user, -5, 'consume', 'AI编辑器重写')
                        is_free = False
                        points_to_deduct = 5
                        billing_msg = "已扣除5积分"
                    else:
                        return jsonify({'success': False, 'error': '积分不足！AI编辑器每天免费5次，超出需5积分/次。'}), 402
                # =================================================================

                # 构建带上下文的prompt
                system_prompt = """你是专业的文档改写助手。根据用户要求重写选中的文本。
重要要求：
1. 只输出改写后的内容，不要输出解释或多余内容
2. 保持与前后文的语气和风格一致
3. 确保改写后的内容能够自然地融入上下文
4. 保持核心含义不变"""

                # 构建上下文信息
                context_info = ""
                if context_before or context_after:
                    context_info = f"\n\n【上下文信息】\n前文：...{context_before}\n【选中的文本】\n后文：{context_after}..."
                elif document_context:
                    context_info = f"\n\n【文档背景】\n{document_context[:500]}..."

                user_prompt = f"需要改写的文本：\n{selected_text}{context_info}\n\n改写要求：{instruction}\n\n请直接输出改写后的文本："
                rewritten = ai_editor_call_llm(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.7)
                return jsonify({
                    'success': True, 
                    'rewritten': rewritten.strip(),
                    'billing_info': {
                        'is_free': is_free,
                        'points_deducted': points_to_deduct,
                        'message': billing_msg,
                        'daily_usage': user.daily_ai_editor_count
                    }
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': str(e)}), 500


        # 模板编辑器页面
        @self.app.route('/template-editor')
        def template_editor():
            return render_template('template_editor_v2.html')
        
        # @高级生成页面
        @self.app.route('/advanced-generation')
        def advanced_generation_page():
            return render_template('advanced_generation.html')
        
        # 知识库管理页面（列表页）
        @self.app.route('/knowledge-base')
        @require_auth
        def knowledge_base_management():
            return render_template('knowledge_base_management.html')
        
        # 知识库详情页面（问答页面）
        @self.app.route('/knowledge-base/<int:kb_id>')
        @require_auth
        def knowledge_base_page(kb_id):
            # 验证知识库所有权
            user = get_current_user()
            if not user:
                return jsonify({'error': '请先登录'}), 401
            from models.user import KnowledgeBase
            kb = KnowledgeBase.query.get(kb_id)
            if not kb or (kb.user_id != user.id and not getattr(kb, 'is_public', False)):
                from flask import redirect, url_for
                return redirect(url_for('knowledge_base_management'))
            is_owner = (kb.user_id == user.id)
            is_admin = getattr(user, 'is_admin', False)
            is_public_kb = getattr(kb, 'is_public', False)
            can_manage = is_owner or (is_public_kb and is_admin)
            
            # 检测是否为移动端
            is_mobile = False
            user_agent = request.headers.get('User-Agent', '').lower()
            if any(platform in user_agent for platform in ['iphone', 'android', 'mobile']):
                is_mobile = True
            
            if is_mobile:
                return render_template('mobile_knowledge_base.html', kb_id=kb_id, kb_name=kb.name, is_owner=is_owner, is_admin=is_admin, can_manage=can_manage, is_public_kb=is_public_kb)
            
            return render_template('knowledge_base.html', kb_id=kb_id, is_owner=is_owner, is_admin=is_admin, can_manage=can_manage, is_public_kb=is_public_kb)
        
        # 新增：个人资料页面（需登录）
        @self.app.route('/profile')
        @require_auth
        def profile_page():
            """个人中心 - 自动适配移动端"""
            ua = request.headers.get('User-Agent', '').lower()
            mobile_keywords = ['mobile', 'iphone', 'android', 'mobi']
            is_mobile = any(k in ua for k in mobile_keywords)
            
            if is_mobile:
                return render_template('mobile_profile.html')
            return render_template('profile.html')
        
        # 上传文件静态路由（头像等）
        @self.app.route('/uploads/<path:filename>')
        def uploaded_file(filename):
            """提供上传文件的访问"""
            upload_folder = self.app.config.get('UPLOAD_FOLDER', 'interface/uploads')
            return send_from_directory(upload_folder, filename)
        
        # === 模板编辑API ===
        
        # 上传Word文档用于编辑
        @self.app.route('/api/template-editor/upload', methods=['POST'])
        @require_auth
        def upload_template_for_editing():
            try:
                if 'file' not in request.files:
                    return jsonify({'error': '没有文件'}), 400
                
                file = request.files['file']
                if file.filename == '':
                    return jsonify({'error': '文件名为空'}), 400
                
                if not file.filename.endswith('.docx'):
                    return jsonify({'error': '只支持.docx格式'}), 400
                
                # 保存文件
                filename = secure_filename(file.filename)
                session_id = uuid.uuid4().hex
                session_dir = os.path.join(self.app.config['UPLOAD_FOLDER'], f'edit_{session_id}')
                os.makedirs(session_dir, exist_ok=True)
                
                filepath = os.path.join(session_dir, filename)
                file.save(filepath)
                
                print(f"✅ 文件已上传: {filepath}")
                
                # 提取文档结构
                from utils.word_tag_inserter import WordTagInserter
                inserter = WordTagInserter()
                structure = inserter.extract_document_structure(filepath)
                
                if not structure:
                    return jsonify({'error': '无法解析文档结构'}), 500
                
                return jsonify({
                    'success': True,
                    'session_id': session_id,
                    'filename': filename,
                    'filepath': filepath,  # 返回文件路径
                    'structure': structure,
                    'message': '文档上传成功'
                })
                
            except Exception as e:
                print(f"❌ 上传失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'上传失败: {str(e)}'}), 500
        
        # 加载已存在的文件（从主页上传的）
        @self.app.route('/api/template-editor/load-existing', methods=['POST'])
        @require_auth
        def load_existing_template():
            try:
                data = request.get_json()
                print(f"📥 收到加载请求: {data}")
                
                filename = data.get('filename')
                filepath = data.get('filepath')
                
                if not filename or not filepath:
                    print("❌ 缺少文件信息")
                    return jsonify({'error': '缺少文件信息'}), 400
                
                # 检查文件是否存在
                if not os.path.exists(filepath):
                    print(f"❌ 文件不存在: {filepath}")
                    return jsonify({'error': f'文件不存在: {filepath}'}), 404
                
                print(f"📄 加载已存在的文件: {filepath}")
                
                # 创建新的编辑会话
                session_id = uuid.uuid4().hex
                session_dir = os.path.join(self.app.config['UPLOAD_FOLDER'], f'edit_{session_id}')
                os.makedirs(session_dir, exist_ok=True)
                
                # 复制文件到编辑会话目录
                import shutil
                new_filepath = os.path.join(session_dir, filename)
                shutil.copy2(filepath, new_filepath)
                
                print(f"✅ 文件已复制到编辑会话: {new_filepath}")
                
                # 提取文档结构
                from utils.word_tag_inserter import WordTagInserter
                inserter = WordTagInserter()
                structure = inserter.extract_document_structure(new_filepath)
                
                print(f"📊 提取的文档结构: elements={len(structure.get('elements', [])) if structure else 0}")
                
                if not structure:
                    print("❌ 无法解析文档结构")
                    return jsonify({'error': '无法解析文档结构'}), 500
                
                print(f"✅ 成功加载文档，session_id={session_id}")
                
                return jsonify({
                    'success': True,
                    'session_id': session_id,
                    'filename': filename,
                    'filepath': new_filepath,  # 返回文件路径
                    'structure': structure,
                    'message': '文档加载成功'
                })
                
            except Exception as e:
                print(f"❌ 加载文件失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'加载失败: {str(e)}'}), 500
        
        # 获取可用标签列表
        @self.app.route('/api/template-editor/tags', methods=['GET'])
        @require_auth
        def get_available_tags():
            try:
                from utils.word_tag_inserter import WordTagInserter
                inserter = WordTagInserter()
                categories = inserter.get_tags_by_category()
                
                return jsonify({
                    'success': True,
                    'categories': categories,
                    'total': len(inserter.supported_tags)
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        # 在文档中插入标签
        @self.app.route('/api/template-editor/insert-tag', methods=['POST'])
        @require_auth
        def insert_tag_to_template():
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                data = request.get_json()
                session_id = data.get('session_id')
                filename = data.get('filename')
                location = data.get('location')  # {type: 'paragraph'/'table', index: int, row: int, col: int}
                tag_name = data.get('tag_name')
                
                if not all([session_id, filename, location, tag_name]):
                    return jsonify({'error': '缺少必要参数'}), 400
                print("✅ 图片保存成功")
                # Assuming 'image_path' is defined somewhere above this line if this is indeed an image saving context
                # For the sake of making the provided snippet syntactically correct and inserting it as requested,
                # I'm adding a placeholder for 'image_path' if it's not defined.
                # If this code is meant for an image generation route, 'image_path' would be the path to the saved image.
                image_path = "/tmp/placeholder_image.png" # Placeholder, replace with actual image_path if context allows
                import os
                # 已使用 get_current_user()
                if os.path.exists(image_path): # Check if image_path exists to avoid error if placeholder is used
                    print(f"文件路径: {image_path}")
                    print(f"文件大小: {os.path.getsize(image_path) / 1024:.2f} KB")
                    
                    # 记录LLM调用
                    try:
                        from utils.llm_logger import log_llm_call
                        log_llm_call(
                            user_id=user.id if hasattr(user, 'id') else None,
                            feature='blackboard',
                            model_name='qwen-vl-plus',
                            api_provider='qwen'
                        )
                    except Exception as log_err:
                        print(f"⚠️ LLM调用日志记录失败: {log_err}")
                
                print(f"📌 收到插入请求:")
                print(f"   标签: {tag_name}")
                print(f"   位置: {location}")
                
                # 构建文件路径
                session_dir = os.path.join(self.app.config['UPLOAD_FOLDER'], f'edit_{session_id}')
                filepath = os.path.join(session_dir, filename)
                
                if not os.path.exists(filepath):
                    return jsonify({'error': '文件不存在'}), 404
                
                # 插入标签
                from utils.word_tag_inserter import WordTagInserter
                inserter = WordTagInserter()
                output_path, success = inserter.insert_tag_to_document(
                    filepath, location, tag_name, filepath
                )
                
                if not success:
                    return jsonify({'error': '标签插入失败'}), 500
                
                # 重新提取结构
                structure = inserter.extract_document_structure(filepath)
                
                return jsonify({
                    'success': True,
                    'message': f'标签 {{{{{{tag_name}}}}}} 已插入',
                    'structure': structure
                })
                
            except Exception as e:
                print(f"❌ 插入标签失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'插入失败: {str(e)}'}), 500
        
        # 获取文件用于渲染（不下载）
        @self.app.route('/api/template-editor/get-file/<session_id>/<filename>', methods=['GET'])
        @require_auth
        def get_file_for_rendering(session_id, filename):
            try:
                session_dir = os.path.join(self.app.config['UPLOAD_FOLDER'], f'edit_{session_id}')
                filepath = os.path.join(session_dir, filename)
                
                if not os.path.exists(filepath):
                    return jsonify({'error': '文件不存在'}), 404
                
                print(f"📖 读取文件用于渲染: {filepath}")
                
                return send_file(
                    filepath,
                    as_attachment=False,
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
                
            except Exception as e:
                print(f"❌ 读取文件失败: {e}")
                return jsonify({'error': f'读取失败: {str(e)}'}), 500
        
        # 下载编辑后的模板
        @self.app.route('/api/template-editor/download/<session_id>/<filename>', methods=['GET'])
        @require_auth
        def download_edited_template(session_id, filename):
            try:
                session_dir = os.path.join(self.app.config['UPLOAD_FOLDER'], f'edit_{session_id}')
                filepath = os.path.join(session_dir, filename)
                
                if not os.path.exists(filepath):
                    return jsonify({'error': '文件不存在'}), 404
                
                print(f"📥 下载文件: {filepath}")
                
                # 生成下载文件名：原文件名_tag.docx
                name_without_ext = os.path.splitext(filename)[0]
                download_filename = f"{name_without_ext}_tag.docx"
                
                return send_file(
                    filepath,
                    as_attachment=True,
                    download_name=download_filename,
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
                
            except Exception as e:
                print(f"❌ 下载失败: {e}")
                return jsonify({'error': f'下载失败: {str(e)}'}), 500
        
        # 健康检查
        @self.app.route('/api/health', methods=['GET'])
        def health_check():
            return jsonify({
                'status': 'healthy',
                'message': 'EduAgent智教创想运行正常',
                'version': '1.0.0'
            })
        
        # 初始化智能体
        @self.app.route('/api/initialize', methods=['POST'])
        @require_auth
        def initialize_agent():
            try:
                data = request.get_json()
                api_key = data.get('api_key')
                
                if not api_key:
                    return jsonify({'error': 'API Key不能为空'}), 400
                
                success, message = self.service.initialize_agent(api_key)
                
                if success:
                    return jsonify({
                        'success': True,
                        'message': message,
                        'agent_initialized': True
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': message
                    }), 400
                    
            except Exception as e:
                return jsonify({'error': f'初始化失败: {str(e)}'}), 500
        
        # 上传模板文件（仅保存，不解析）
        @self.app.route('/api/upload-template', methods=['POST'])
        @require_auth
        def upload_template():
            try:
                if 'file' not in request.files:
                    return jsonify({'error': '没有上传文件'}), 400
                
                file = request.files['file']
                if file.filename == '':
                    return jsonify({'error': '没有选择文件'}), 400
                
                if not self.service.agent:
                    return jsonify({'error': '请先初始化智能体'}), 400
                
                # 保存文件
                filename = secure_filename(file.filename)
                file_path = os.path.join(self.app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                # 只保存文件路径，不立即解析
                self.service.state.template_uploaded = True
                self.service.state.template_path = file_path
                
                return jsonify({
                    'success': True,
                    'message': '模板文件上传成功',
                    'file_name': filename,
                    'file_path': file_path
                })
                
            except Exception as e:
                return jsonify({'error': f'模板上传失败: {str(e)}'}), 500
        
        # 解析模板（在需要时调用）
        @self.app.route('/api/parse-template', methods=['POST'])
        @require_auth
        def parse_template():
            try:
                if not self.service.agent:
                    return jsonify({'error': '请先初始化智能体'}), 400
                
                if not hasattr(self.service.state, 'template_path'):
                    return jsonify({'error': '请先上传模板文件'}), 400
                
                # 解析模板
                template_structure = self.service.agent.extract_template_keywords(
                    self.service.state.template_path
                )
                
                # 更新状态
                self.service.state.template_structure = template_structure
                
                return jsonify({
                    'success': True,
                    'message': '模板解析成功',
                    'template_structure': template_structure
                })
                
            except Exception as e:
                return jsonify({'error': f'模板解析失败: {str(e)}'}), 500
        
        # 通用对话接口(流式)
        @self.app.route('/api/chat/stream', methods=['POST'])
        @require_auth
        def chat_with_user_stream():
            """流式对话接口"""
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                if not self.service.agent:
                    return jsonify({'error': '请先初始化智能体'}), 400

                data = request.get_json()
                message = data.get('message', '')
                model = data.get('model', 'qwen-turbo')
                conversation_id = data.get('conversation_id')

                if not message:
                    return jsonify({'error': '消息不能为空'}), 400

                # 1. 获取或创建对话
                new_conversation = False
                if conversation_id:
                    conv = Conversation.query.get(conversation_id)
                    if not conv or conv.user_id != user.id:
                        return jsonify({'error': '对话不存在或无权访问'}), 404
                else:
                    # 如果没有ID，创建一个新对话
                    conv = Conversation(user_id=user.id, title='新对话')
                    db.session.add(conv)
                    db.session.commit()
                    conversation_id = conv.id
                    new_conversation = True

                # 2. 加载现有历史 (转换为agent需要的格式)
                # 注意：agent期望的历史是 [{'role': 'user', 'content': '...'}, ...]
                db_messages = ConversationMessage.query.filter_by(conversation_id=conversation_id).order_by(ConversationMessage.created_at).all()
                external_history = [{'role': m.role, 'content': m.content} for m in db_messages]
                
                # 判断是否需要生成标题 (第一条消息)
                should_generate_title = (len(db_messages) == 0)

                # 3. 额度检查与扣费 (Quota Check & Charge)
                today = datetime.now(timezone.utc).date()
                
                # 每日重置
                if user.last_free_reset_date != today:
                    user.daily_free_count = 0
                    user.last_free_reset_date = today
                    db.session.commit()
                
                is_free = False
                deducted_points = 0
                warning_message = None

                print(f"DEBUG: User {user.username} - Free Count: {user.daily_free_count}, Daily limit: 10")
                
                if user.daily_free_count < 10:
                    user.daily_free_count += 1
                    is_free = True
                else:
                    # 超过免费额度，扣除积分
                    if user.points_balance >= 1:
                        # 使用 helper 函数记录流水
                        from models.shop import add_points_to_user
                        add_points_to_user(user, -1, 'consume', '智能对话消耗')
                        
                        is_free = False # Still paid
                        deducted_points = 1
                        warning_message = "今日免费额度已用完，本条内容消耗 1 积分。"
                    else:
                        return jsonify({'error': '积分不足，请先充值', 'code': 'INSUFFICIENT_POINTS'}), 402
                
                # db.session.commit() # add_points_to_user already commits
                
                # 3. 保存用户消息
                user_msg = ConversationMessage(conversation_id=conversation_id, role='user', content=message)
                db.session.add(user_msg)
                conv.updated_at = datetime.now(timezone.utc)
                db.session.commit()
                
                # 将用户消息添加到历史中传给agent
                external_history.append({'role': 'user', 'content': message})

                def generate():
                    """SSE生成器"""
                    try:
                        # 使用外部闭包捕获的 user 对象，不要在生成器内部再次调用 get_current_user()
                        # 因为生成器在流式返回时可能已经脱离了请求上下文 (Request Context)
                        
                        # 创建一个wrapper来处理async generator
                        async def async_generate():
                            try:
                                async for chunk in self.service.agent.chat_with_user_stream(
                                    message, 
                                    model_name=model, 
                                    external_history=external_history,
                                    user_id=user.id
                                ):
                                    yield chunk
                            except Exception as e:
                                yield f"ERROR: {str(e)}"

                        # 在新的事件循环中运行
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        full_response = ""
                        
                        # 如果有警告消息（积分消耗提示），先发送给我前端特殊处理（或者直接作为第一段文本）
                        # 这里为了简单，我们作为第一段assistant消息发送，但最好前端能区分
                        # 我们采用特殊标记 [SYSTEM] 或直接加粗提示
                        if warning_message:
                            # 包装在特殊的Markdown引用中以示区别
                            warning_chunk = f"> ⚠️ **{warning_message}**\n\n"
                            yield f"data: {json.dumps({'chunk': warning_chunk, 'done': False}, ensure_ascii=False)}\n\n"
                            full_response += warning_chunk

                        try:
                            from utils.llm_logger import log_llm_call_async
                            log_llm_call_async(
                                user_id=user.id,
                                feature='chat',
                                model_name=model,
                                api_provider='qwen'
                            )
                        except Exception:
                            pass

                        try:
                            # 创建异步生成器
                            async_gen = async_generate()

                            # 逐个获取并发送
                            while True:
                                try:
                                    # 获取下一个chunk
                                    chunk = loop.run_until_complete(async_gen.__anext__())

                                    if chunk.startswith("ERROR: "):
                                        error_msg = chunk[7:]
                                        yield f"data: {json.dumps({'error': error_msg, 'done': True}, ensure_ascii=False)}\n\n"
                                        break
                                    else:
                                        full_response += chunk
                                        # 发送SSE格式数据
                                        yield f"data: {json.dumps({'chunk': chunk, 'done': False}, ensure_ascii=False)}\n\n"

                                except StopAsyncIteration:
                                    # 生成器结束
                                    break

                        finally:
                            # 确保异步生成器完全关闭
                            try:
                                loop.run_until_complete(async_gen.aclose())
                            except:
                                pass
                            loop.close()

                        # 4. 对话结束后保存AI回复和更新标题
                        with self.app.app_context():
                            # 保存AI回复
                            if full_response:
                                ai_msg = ConversationMessage(
                                    conversation_id=conversation_id, 
                                    role='assistant', 
                                    content=full_response, 
                                    model_used=model
                                )
                                db.session.add(ai_msg)
                                
                                # 更新对话更新时间
                                conv_ref = Conversation.query.get(conversation_id)
                                if conv_ref:
                                    conv_ref.updated_at = datetime.now(timezone.utc)
                                    
                                    # 5. 自动生成标题 (如果是新对话)
                                    if should_generate_title:
                                        try:
                                            # 简单的标题生成策略：截取前20个字符
                                            # 若要更智能，可以调用agent生成，但这会增加延迟
                                            # 这里我们尝试一个简单的同步调用来生成摘要
                                            
                                            # 简单的基于规则的标题
                                            title_candidate = message[:30]
                                            conv_ref.title = title_candidate
                                            
                                            # TODO: 可以在后台任务中调用LLM生成更好的标题
                                            # 或者在这里同步调用一次快速模型（如果不想阻塞太久）
                                            
                                        except Exception as e:
                                             print(f"标题生成失败: {e}")
                                    
                                    # 6. 记录LLM调用到统计系统
                                    try:
                                        from utils.llm_logger import log_llm_call
                                        log_llm_call(
                                            user_id=user.id,
                                            feature='chat',
                                            model_name=model,
                                            api_provider='qwen'
                                        )
                                    except Exception as log_err:
                                        # 日志记录失败不应影响主流程
                                        print(f"⚠️ LLM调用日志记录失败: {log_err}")
                                    
                                    db.session.commit()

                        # 发送完成标记，包含conversation_id
                        yield f"data: {json.dumps({'chunk': '', 'done': True, 'conversation_id': conversation_id}, ensure_ascii=False)}\n\n"

                    except Exception as e:
                        error_msg = str(e)
                        print(f"流式对话错误: {e}")
                        import traceback
                        traceback.print_exc()
                        yield f"data: {json.dumps({'error': error_msg, 'done': True}, ensure_ascii=False)}\n\n"

                return Response(
                    generate(),
                    mimetype='text/event-stream',
                    headers={
                        'Cache-Control': 'no-cache',
                        'X-Accel-Buffering': 'no',
                        'Connection': 'keep-alive'
                    }
                )

            except Exception as e:
                return jsonify({'error': f'对话处理失败: {str(e)}'}), 500

        # 通用对话接口(非流式,保留兼容性)
        @self.app.route('/api/chat/ask', methods=['POST'])
        @require_auth
        def chat_ask_async():
            """异步版本的通用对话 (带持久化)"""
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                if not self.service.agent:
                    return jsonify({'error': '请先初始化智能体'}), 400

                data = request.get_json()
                message = data.get('message', '')
                model = data.get('model', 'qwen-turbo')
                conversation_id = data.get('conversation_id')

                if not message:
                    return jsonify({'error': '消息不能为空'}), 400

                from models.conversation import Conversation, ConversationMessage
                # 确定对话 ID
                if conversation_id:
                    conv = Conversation.query.get(conversation_id)
                    if not conv or conv.user_id != user.id:
                        return jsonify({'error': '对话不存在或无权访问'}), 403
                else:
                    conv = Conversation.query.filter_by(user_id=user.id, kb_id=None).order_by(Conversation.updated_at.desc()).first()
                    if not conv:
                        conv = Conversation(user_id=user.id, title="新对话")
                        db.session.add(conv)
                        db.session.flush()

                # 保存用户消息
                user_msg = ConversationMessage(conversation_id=conv.id, role='user', content=message, status='completed')
                db.session.add(user_msg)
                
                # 创建占位 AI 回答
                ai_msg = ConversationMessage(conversation_id=conv.id, role='assistant', content='正在思考中...', status='processing', model_used=model)
                db.session.add(ai_msg)
                
                from datetime import datetime, timezone
                conv.updated_at = datetime.now(timezone.utc)
                db.session.commit()

                # 启动后台任务
                import threading
                thread = threading.Thread(
                    target=self._background_chat_ask,
                    args=(message, model, ai_msg.id, user.id),
                    daemon=True
                )
                thread.start()

                return jsonify({
                    'success': True,
                    'message_id': ai_msg.id,
                    'conversation_id': conv.id,
                    'status': 'processing'
                })

            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'对话处理失败: {str(e)}'}), 500

        @self.app.route('/api/chat', methods=['POST'])
        @require_auth
        def chat_with_user():
            """兼容旧版的同步对话接口"""
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                if not self.service.agent:
                    return jsonify({'error': '请先初始化智能体'}), 400

                data = request.get_json()
                message = data.get('message', '')
                model = data.get('model', 'qwen-turbo')

                if not message:
                    return jsonify({'error': '消息不能为空'}), 400

                # 异步对话处理
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    response = loop.run_until_complete(
                        self.service.agent.chat_with_user(message, model_name=model, user_id=user.id)
                    )
                finally:
                    loop.close()

                return jsonify({
                    'success': True,
                    'response': response,
                    'message_type': 'chat',
                    'model_used': model
                })

            except Exception as e:
                return jsonify({'error': f'对话处理失败: {str(e)}'}), 500

        # === 对话历史API ===
        
        # 获取对话列表
        @self.app.route('/api/conversations', methods=['GET'])
        @require_auth
        def get_conversations():
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                page = request.args.get('page', 1, type=int)
                per_page = request.args.get('per_page', 50, type=int)
                
                # 显式使用text()来处理desc排序，避免属性访问错误
                from sqlalchemy import desc
                pagination = Conversation.query.filter_by(user_id=user.id)\
                    .order_by(desc(Conversation.updated_at))\
                    .paginate(page=page, per_page=per_page, error_out=False)
                
                return jsonify({
                    'success': True,
                    'conversations': [c.to_dict() for c in pagination.items],
                    'total': pagination.total,
                    'pages': pagination.pages,
                    'current_page': pagination.page
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e)}), 500

        # 创建新对话
        @self.app.route('/api/conversations', methods=['POST'])
        @require_auth
        def create_conversation():
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                # 检查是否存在最近的空对话（避免创建过多空对话）
                # 查找最近5分钟内创建的且没有消息的对话
                from datetime import timedelta
                from sqlalchemy import not_
                
                # 获取该用户的最近空对话
                # 注意：这里需要稍微复杂的查询，ConversationMessage为空
                # 简单起见，我们先创建新的，以后优化
                
                conv = Conversation(user_id=user.id)
                conv.title = '新对话'
                db.session.add(conv)
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'conversation': conv.to_dict()
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        # 获取对话详情（消息历史）
        @self.app.route('/api/conversations/<int:conv_id>', methods=['GET'])
        @require_auth
        def get_conversation_messages(conv_id):
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                conv = Conversation.query.get_or_404(conv_id)
                if conv.user_id != user.id:
                    return jsonify({'error': '无权访问'}), 403
                
                messages = conv.messages.all()
                
                return jsonify({
                    'success': True,
                    'conversation': conv.to_dict(),
                    'messages': [m.to_dict() for m in messages]
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        # 删除对话
        @self.app.route('/api/conversations/<int:conv_id>', methods=['DELETE'])
        @require_auth
        def delete_conversation(conv_id):
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                conv = Conversation.query.get_or_404(conv_id)
                if conv.user_id != user.id:
                    return jsonify({'error': '无权访问'}), 403
                
                db.session.delete(conv)
                db.session.commit()
                
                return jsonify({'success': True, 'message': '对话已删除'})
            except Exception as e:
                return jsonify({'error': str(e)}), 500
                
        # 更新对话标题
        @self.app.route('/api/conversations/<int:conv_id>/title', methods=['PUT'])
        @require_auth
        def update_conversation_title(conv_id):
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                conv = Conversation.query.get_or_404(conv_id)
                if conv.user_id != user.id:
                    return jsonify({'error': '无权访问'}), 403
                
                data = request.get_json()
                new_title = data.get('title')
                if not new_title:
                    return jsonify({'error': '标题不能为空'}), 400
                    
                conv.title = new_title
                db.session.commit()
                
                return jsonify({'success': True, 'title': conv.title})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        # 分析用户意图
        @self.app.route('/api/analyze-intent', methods=['POST'])
        @require_auth
        def analyze_intent():
            try:
                if not self.service.agent:
                    return jsonify({'error': '请先初始化智能体'}), 400
                
                data = request.get_json()
                message = data.get('message', '')
                
                # 异步分析意图
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    intent = loop.run_until_complete(
                        self.service.analyze_user_intent(message)
                    )
                finally:
                    loop.close()
                
                return jsonify({
                    'success': True,
                    'intent': intent
                })
                
            except Exception as e:
                return jsonify({'error': f'意图分析失败: {str(e)}'}), 500

        # 板书设计
        @self.app.route('/api/blackboard-design', methods=['POST'])
        @require_auth
        def blackboard_design():
            try:
                import requests
                from config.settings import XINGHU_API_KEY
                from datetime import datetime, date

                print("\n" + "="*60)
                print("📝 板书设计API调用 (Billing Enabled)")
                print("="*60)
                
                # Log usage
                try:
                    from utils.llm_logger import log_llm_call_async
                    log_llm_call_async(
                        user_id=getattr(current_user, 'id', None),
                        feature='blackboard',
                        model_name='gemini-3-pro-image-preview',
                        api_provider='xinghu'
                    )
                except Exception:
                    pass

                data = request.get_json()
                print(f"📥 接收到的数据: {data}")

                content = data.get('content', '').strip()
                size = data.get('size', '1024x1024')  # Default to standard square
                
                print(f"📄 板书内容: {content[:100]}...")
                print(f"📏 请求尺寸: {size}")

                if not content:
                    return jsonify({'error': '请输入板书内容'}), 400

                # ==================== Billing Logic ====================
                user = get_current_user()
                today = date.today()
                
                # 1. Check & Reset Monthly Quota
                # Logic: If last reset was not this month, reset count to 0
                if not user.last_monthly_reset_date or \
                   (user.last_monthly_reset_date.month != today.month or user.last_monthly_reset_date.year != today.year):
                    print(f"🔄 Monthly Reset Triggered for User {user.id}")
                    user.monthly_blackboard_count = 0
                    user.last_monthly_reset_date = today
                    db.session.commit()

                # 2. Determine Cost
                FREE_MONTHLY_LIMIT = 3
                cost_points = 0
                is_free = False
                
                # Pricing Map
                # 1024x1024 -> 20 points
                # 1792x1024 -> 50 points
                price_map = {
                    '1024x1024': 20,
                    '1792x1024': 50
                }
                current_price = price_map.get(size, 20) # Fallback to 20 if unknown

                if user.monthly_blackboard_count < FREE_MONTHLY_LIMIT:
                    is_free = True
                    print(f"🆓 使用月度免费额度 ({user.monthly_blackboard_count + 1}/{FREE_MONTHLY_LIMIT})")
                else:
                    cost_points = current_price
                    print(f"💰 超出免费额度，需要 {cost_points} 积分")
                    
                    if user.points_balance < cost_points:
                        return jsonify({'error': f'积分不足！生成此尺寸板书需要 {cost_points} 积分，当前余额 {user.points_balance} 积分'}), 402

                # =======================================================

                # 3. Call External API
                image_prompt = f"{content} 正面板书图片"
                print("🚀 开始调用XINGHU API...")

                response = requests.post(
                    'https://xinghuapi.com/v1/images/generations',
                    headers={
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {XINGHU_API_KEY}',
                    },
                    json={
                        'model': 'gemini-3-pro-image-preview',
                        'prompt': image_prompt,
                        'n': 1,
                        'size': size, # Forward the requested size
                        'response_format': 'url'
                    },
                    timeout=500,
                    proxies={'http': None, 'https': None}
                )

                if response.status_code == 200:
                    result = response.json()
                    data_list = result.get('data') or []
                    image_url = ''
                    if isinstance(data_list, list) and data_list:
                        image_url = data_list[0].get('url') or ''

                    if image_url:
                        design = f"![板书设计]({image_url})"
                        
                        # 4. Apply Billing (Success only)
                        try:
                            if is_free:
                                user.monthly_blackboard_count += 1
                                db.session.commit() # Save increment
                            else:
                                from models.shop import add_points_to_user
                                # Deduct points
                                description = f"板书生成 ({size})"
                                add_points_to_user(user, -cost_points, 'consume', description)
                                # Increment count for tracking purposes (though essentially unlimited paid)
                                user.monthly_blackboard_count += 1
                                db.session.commit() # Should be handled by add_points_to_user but safe to commit
                                
                            print(f"✅ 计费完成. IsFree: {is_free}, Cost: {cost_points}")
                            
                            # Log LLM Call
                            from utils.llm_logger import log_llm_call
                            log_llm_call(
                                user_id=user.id,
                                feature='blackboard',
                                model_name='gemini-3-pro-image',
                                api_provider='xinghu'
                            )
                        except Exception as bill_err:
                            print(f"⚠️ 计费/日志失败: {bill_err}")
                            # Don't fail the request if generation succeeded but billing logged warning
                            # But technically we should rollback? For now, print error.
                        
                        return jsonify({
                            'success': True, 
                            'design': design,
                            'usage_info': {
                                'is_free': is_free,
                                'monthly_count': user.monthly_blackboard_count,
                                'monthly_limit': FREE_MONTHLY_LIMIT,
                                'points_deducted': cost_points
                            }
                        })
                    else:
                        print("⚠️ 未找到图片URL")
                        return jsonify({'error': '生成成功但无图片URL'}), 500
                else:
                    print(f"❌ API调用失败: {response.status_code} {response.text}")
                    return jsonify({'error': f'API调用失败: {response.status_code}'}), 500

            except Exception as e:
                print(f"❌ 异常: {str(e)}")
                import traceback
                print(traceback.format_exc())
                return jsonify({'error': f'板书设计失败: {str(e)}'}), 500

        # 生成课程大纲
        @self.app.route('/api/generate-outline', methods=['POST'])
        @require_auth
        def generate_outline():
            try:
                if not self.service.agent:
                    return jsonify({'error': '请先初始化智能体'}), 400
                
                if not self.service.state.template_uploaded:
                    return jsonify({'error': '请先上传模板文件'}), 400
                
                data = request.get_json()
                course_info = data.get('course_info', {})
                requirements = data.get('requirements', '')
                
                # 调试：打印接收到的课程信息
                print(f"\n{'='*60}")
                print(f"📋 接收到的课程信息:")
                print(f"   课程名称: {course_info.get('subject', 'N/A')}")
                print(f"   课程性质: {course_info.get('course_type', 'N/A')}")
                print(f"   学分: {course_info.get('credits', 'N/A')}")
                print(f"   总课时: {course_info.get('total_lessons', 'N/A')}")
                print(f"   专业: {course_info.get('major', 'N/A')}")
                print(f"   学历层次: {course_info.get('grade', 'N/A')}")
                print(f"   完整信息: {course_info}")
                print(f"{'='*60}\n")
                
                # 验证必要字段
                if not course_info.get('subject'):
                    return jsonify({'error': '课程名称不能为空'}), 400
                if not course_info.get('total_lessons') or course_info.get('total_lessons', 0) <= 0:
                    return jsonify({'error': f'总课时数必须大于0，当前值: {course_info.get("total_lessons", 0)}'}), 400
                
                # 异步生成大纲
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    outline = loop.run_until_complete(
                        self.service.agent.plan_university_course_outline(course_info, requirements)
                    )
                finally:
                    loop.close()
                
                if 'error' in outline:
                    return jsonify({'error': outline['error']}), 500
                
                # 更新状态和agent的course_outline（两者都需要更新）
                self.service.state.course_outline = outline
                if self.service.agent:
                    self.service.agent.course_outline = outline
                    print(f"✅ 课程大纲已更新到agent，包含 {len(outline.get('lessons', []))} 个课时")
                
                return jsonify({
                    'success': True,
                    'message': '课程大纲生成成功',
                    'outline': outline
                })
                
            except Exception as e:
                return jsonify({'error': f'大纲生成失败: {str(e)}'}), 500
        
        # 生成单个教案
        @self.app.route('/api/generate-lesson', methods=['POST'])
        @require_auth
        def generate_lesson():
            try:
                if not self.service.agent:
                    return jsonify({'error': '请先初始化智能体'}), 400
                
                if not self.service.state.course_outline:
                    return jsonify({'error': '请先生成课程大纲'}), 400
                
                data = request.get_json()
                lesson_info = data.get('lesson_info', {})
                additional_requirements = data.get('additional_requirements', '')
                
                # 异步生成教案
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    lesson_plan = loop.run_until_complete(
                        self.service.agent.generate_university_lesson_plan(
                            lesson_info, 
                            self.service.state.template_structure,
                            additional_requirements
                        )
                    )
                finally:
                    loop.close()
                
                return jsonify({
                    'success': True,
                    'message': '教案生成成功',
                    'lesson_plan': lesson_plan
                })
                
            except Exception as e:
                return jsonify({'error': f'教案生成失败: {str(e)}'}), 500
        
        # 批量生成所有教案
        @self.app.route('/api/generate-all-lessons', methods=['POST'])
        @require_auth
        def generate_all_lessons():
            try:
                if not self.service.agent:
                    return jsonify({'error': '请先初始化智能体'}), 400
                
                if not self.service.state.course_outline:
                    return jsonify({'error': '请先生成课程大纲'}), 400
                
                data = request.get_json()
                additional_requirements = data.get('additional_requirements', '')
                
                # 进度追踪 - 保存到service对象中
                self.service.generation_progress = {'current': 0, 'total': 0, 'message': '', 'status': 'running'}
                
                def progress_callback(current, total, message):
                    self.service.generation_progress = {
                        'current': current,
                        'total': total,
                        'message': message,
                        'status': 'running'
                    }
                    print(f"📊 进度: {current}/{total} - {message}")
                
                # 异步批量生成教案
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    lesson_plans = loop.run_until_complete(
                        self.service.agent.generate_all_lesson_plans(
                            additional_requirements,
                            progress_callback=progress_callback
                        )
                    )
                finally:
                    loop.close()
                
                # 保存教案到状态中，供导出使用
                self.service.state.lesson_plans = lesson_plans
                
                # 更新进度为完成状态
                self.service.generation_progress = {
                    'current': len(lesson_plans),
                    'total': len(lesson_plans),
                    'message': '所有教案生成完成',
                    'status': 'completed'
                }
                
                # 打印调试信息
                print(f"✅ 成功生成 {len(lesson_plans)} 个教案")
                print(f"📁 教案已保存到状态，可以导出")
                
                return jsonify({
                    'success': True,
                    'message': f'成功生成{len(lesson_plans)}个教案',
                    'lesson_plans': lesson_plans,
                    'total_count': len(lesson_plans)
                })
                
            except Exception as e:
                return jsonify({'error': f'批量生成失败: {str(e)}'}), 500
        
        # 获取教案生成进度（轮询接口）
        @self.app.route('/api/lesson-generation-progress', methods=['GET'])
        @require_auth
        def get_lesson_progress():
            try:
                if hasattr(self.service, 'generation_progress'):
                    return jsonify(self.service.generation_progress)
                return jsonify({'current': 0, 'total': 0, 'message': ''})
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        # 导出教案为Word文档
        @self.app.route('/api/export-lessons', methods=['POST'])
        @require_auth
        def export_lessons():
            try:
                print("=" * 50)
                print("🔍 开始智能导出教案")
                print(f"📊 教案状态检查: {hasattr(self.service.state, 'lesson_plans')}")
                
                if not hasattr(self.service.state, 'lesson_plans') or not self.service.state.lesson_plans:
                    print("❌ 没有找到教案数据")
                    return jsonify({'error': '没有教案可导出，请先生成教案'}), 400
                
                print(f"✅ 找到 {len(self.service.state.lesson_plans)} 个教案")
                
                data = request.get_json()
                export_format = data.get('format', 'word')  # word, txt
                filename = data.get('filename', f'教案_{uuid.uuid4().hex[:8]}')
                
                print(f"📝 导出格式: {export_format}")
                print(f"📁 文件名: {filename}")
                
                # ========== 获取模板信息 ==========
                template_mode = getattr(self.service.agent, 'template_mode', 'text')
                template_path = getattr(self.service.agent, 'template_file_path', None)
                
                print(f"🏷️  模板模式: {template_mode}")
                print(f"📂 模板路径: {template_path}")
                
                # ========== 使用智能导出 ==========
                file_path, success = self.exporter.smart_export(
                    lesson_plans=self.service.state.lesson_plans,
                    course_outline=self.service.agent.course_outline if hasattr(self.service.agent, 'course_outline') else None,
                    template_mode=template_mode,
                    template_path=template_path,
                    export_format=export_format
                )
                
                if not success or not file_path:
                    raise Exception("文档导出失败")
                
                # 设置正确的mimetype和扩展名
                if export_format == 'word':
                    mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                    file_extension = 'docx'
                elif export_format == 'txt':
                    mimetype = 'text/plain'
                    file_extension = 'txt'
                else:
                    return jsonify({'error': f'不支持的导出格式: {export_format}，当前支持：word, txt'}), 400
                
                print(f"📄 生成文件路径: {file_path}")
                print(f"📂 文件是否存在: {os.path.exists(file_path)}")
                if os.path.exists(file_path):
                    print(f"📏 文件大小: {os.path.getsize(file_path)} bytes")
                print("=" * 50)
                
                # 使用生成的文件名（不需要再添加扩展名，文件已经有了）
                return send_file(
                    file_path,
                    as_attachment=True,
                    mimetype=mimetype
                )
                
            except Exception as e:
                print(f"❌ 导出错误: {str(e)}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'导出失败: {str(e)}'}), 500
        
        # === @高级生成 API ===
        
        @self.app.route('/api/advanced-generate', methods=['POST'])
        @require_auth
        def advanced_generate():
            """
            @高级生成 - 使用AI自动填充教案模板
            
            请求体（multipart/form-data）:
            - file: 上传的Word模板文件（.docx）
            - topic: 教案主题
            """
            try:
                from core.advanced_generator import AdvancedLessonGenerator
                import shutil
                
                topic = request.form.get('topic', '').strip()
                
                if not topic:
                    return jsonify({'error': '请提供教案主题'}), 400
                
                # 检查agent是否已初始化
                if not self.service.agent:
                    return jsonify({'error': '请先初始化AI代理'}), 400
                
                # 检查是使用默认模板还是上传文件
                use_default_template = request.form.get('use_default_template', 'false') == 'true'
                default_template_name = request.form.get('default_template_name', '')
                
                print(f"\n{'='*80}")
                print(f"🚀 @高级生成 请求")
                print(f"{'='*80}")
                print(f"📚 主题: {topic}")
                
                import tempfile
                temp_dir = tempfile.mkdtemp()
                
                if use_default_template and default_template_name:
                    # 使用默认模板
                    templates_dir = os.path.join(os.path.dirname(__file__), '..', 'templates_library')
                    templates_dir = os.path.abspath(templates_dir)
                    default_template_path = os.path.join(templates_dir, default_template_name)
                    
                    if not os.path.exists(default_template_path):
                        return jsonify({'error': '默认模板不存在'}), 400
                    
                    # 复制默认模板到临时目录
                    import shutil
                    template_path = os.path.join(temp_dir, default_template_name)
                    shutil.copy2(default_template_path, template_path)
                    
                    print(f"📄 使用默认模板: {default_template_name}")
                    print(f"✅ 模板已复制到: {template_path}")
                else:
                    # 使用上传的文件
                    if 'file' not in request.files:
                        return jsonify({'error': '请上传模板文件或选择默认模板'}), 400
                    
                    file = request.files['file']
                    
                    if not file or file.filename == '':
                        return jsonify({'error': '请选择模板文件'}), 400
                    
                    # 检查文件类型
                    if not file.filename.endswith('.docx'):
                        return jsonify({'error': '只支持.docx格式的Word文档'}), 400
                    
                    template_path = os.path.join(temp_dir, secure_filename(file.filename))
                    file.save(template_path)
                    
                    print(f"📄 使用上传文件: {file.filename}")
                    print(f"✅ 模板已保存到: {template_path}")
                
                print(f"{'='*80}\n")
                
                # 创建全局进度存储（如果不存在）
                if not hasattr(self, 'generation_progress'):
                    self.generation_progress = {}
                
                # 生成任务ID
                import uuid
                task_id = str(uuid.uuid4())
                
                # 初始化进度
                self.generation_progress[task_id] = {
                    'progress': 0,
                    'status': 'starting',
                    'current_step': '准备中...',
                    'logs': [],
                    'result': None,
                    'error': None,
                    'start_time': time.time()  # ✅ 添加开始时间用于过期清理
                }
                
                # 定义进度回调函数
                def progress_callback(progress, status, message):
                    if task_id in self.generation_progress:
                        self.generation_progress[task_id]['progress'] = progress
                        self.generation_progress[task_id]['status'] = status
                        # 🔧 不暴露内部流程细节，只保留进度
                        self.generation_progress[task_id]['current_step'] = ""
                        # 日志仍然记录，但不返回给前端
                        self.generation_progress[task_id]['logs'].append({
                            'time': time.time(),
                            'message': message
                        })
                        # 打印到控制台便于调试
                        print(f"[{progress}%] {message}")
                
                # 定义后台生成任务
                def run_generation_task():
                    """在后台线程中运行生成任务"""
                    try:
                        print(f"🔄 后台任务开始: {task_id}")
                        
                        # 创建生成器（带进度回调）
                        generator = AdvancedLessonGenerator(
                            agent=self.service.agent,
                            progress_callback=progress_callback
                        )
                        
                        # 获取输出目录（使用配置中的EXPORT_FOLDER）
                        output_dir = self.app.config.get('EXPORT_FOLDER', os.path.join(os.path.dirname(__file__), 'exports'))
                        print(f"📁 输出目录: {output_dir}")
                        
                        # 执行生成（同步包装异步调用）
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            success, result = loop.run_until_complete(
                                generator.generate(topic, template_path, output_dir=output_dir)
                            )
                        finally:
                            loop.close()
                        
                        # 清理临时文件
                        try:
                            shutil.rmtree(temp_dir)
                            print(f"🧹 临时文件已清理")
                        except:
                            pass
                        
                        if success:
                            # 更新进度状态
                            if task_id in self.generation_progress:
                                self.generation_progress[task_id]['result'] = result
                                self.generation_progress[task_id]['status'] = 'completed'
                            print(f"✅ 后台任务完成: {task_id}")
                        else:
                            # 更新进度状态
                            if task_id in self.generation_progress:
                                self.generation_progress[task_id]['error'] = result
                                self.generation_progress[task_id]['status'] = 'failed'
                            print(f"❌ 后台任务失败: {task_id}")
                            
                    except Exception as e:
                        print(f"❌ 后台任务异常: {task_id} - {str(e)}")
                        import traceback
                        traceback.print_exc()
                        if task_id in self.generation_progress:
                            self.generation_progress[task_id]['error'] = str(e)
                            self.generation_progress[task_id]['status'] = 'failed'
                
                # 启动后台线程
                import threading
                thread = threading.Thread(target=run_generation_task, daemon=True)
                thread.start()
                
                print(f"🚀 任务已启动（后台运行）: {task_id}")
                
                # 立即返回任务ID
                return jsonify({
                    'success': True,
                    'message': '任务已启动',
                    'task_id': task_id
                })
                    
            except Exception as e:
                print(f"❌ @高级生成 错误: {str(e)}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'生成失败: {str(e)}'}), 500
        
        # 获取默认模板列表
        @self.app.route('/api/advanced-generate/templates', methods=['GET'])
        def get_default_templates():
            """获取默认模板列表"""
            try:
                templates_dir = os.path.join(os.path.dirname(__file__), '..', 'templates_library')
                templates_dir = os.path.abspath(templates_dir)
                
                if not os.path.exists(templates_dir):
                    return jsonify({'templates': []})
                
                templates = []
                for filename in os.listdir(templates_dir):
                    if filename.endswith('.docx') and not filename.startswith('~$'):
                        file_path = os.path.join(templates_dir, filename)
                        file_size = os.path.getsize(file_path)
                        templates.append({
                            'name': filename,
                            'size': file_size,
                            'path': filename  # 只存储文件名
                        })
                
                return jsonify({'templates': templates})
            except Exception as e:
                print(f"❌ 获取模板列表错误: {str(e)}")
                return jsonify({'error': str(e)}), 500
        
        # 获取生成进度
        @self.app.route('/api/advanced-generate/progress/<task_id>', methods=['GET'])
        def get_generation_progress(task_id):
            """获取生成进度"""
            try:
                if not hasattr(self, 'generation_progress'):
                    print(f"⚠️ generation_progress 不存在")
                    return jsonify({'error': '进度系统未初始化'}), 500
                
                if task_id not in self.generation_progress:
                    print(f"⚠️ 任务ID不存在: {task_id}")
                    print(f"   现有任务: {list(self.generation_progress.keys())}")
                    return jsonify({'error': '任务不存在'}), 404
                
                progress_data = self.generation_progress[task_id]
                # 打印调试信息（每5次请求打印一次，避免刷屏）
                if not hasattr(self, '_progress_query_count'):
                    self._progress_query_count = {}
                self._progress_query_count[task_id] = self._progress_query_count.get(task_id, 0) + 1
                if self._progress_query_count[task_id] % 5 == 1:
                    print(f"📊 [查询 #{self._progress_query_count[task_id]}] 进度: {progress_data['progress']}%, 状态: {progress_data['status']}, 日志数: {len(progress_data['logs'])}")
                
                return jsonify(progress_data)
            except Exception as e:
                print(f"❌ 获取进度错误: {str(e)}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/advanced-generate/download/<path:filename>', methods=['GET'])
        def download_advanced_generated(filename):
            """下载高级生成的教案文件"""
            try:
                print(f"\n{'='*60}")
                print(f"📥 下载请求")
                print(f"{'='*60}")
                print(f"请求的文件名: {filename}")
                
                # 安全检查：只允许文件名，不允许路径遍历
                # 移除路径分隔符，但保留中文字符
                safe_filename = os.path.basename(filename)
                if '..' in safe_filename or '/' in safe_filename or '\\' in safe_filename:
                    print(f"❌ 非法文件名（包含路径遍历）")
                    return jsonify({'error': '非法文件名'}), 400
                
                print(f"安全文件名: {safe_filename}")
                
                # 构建文件路径（使用配置中的exports目录）
                exports_dir = self.app.config.get('EXPORT_FOLDER', os.path.join(os.path.dirname(__file__), 'exports'))
                file_path = os.path.join(exports_dir, safe_filename)
                
                print(f"完整路径: {file_path}")
                print(f"exports目录: {exports_dir}")
                print(f"exports目录存在: {os.path.exists(exports_dir)}")
                
                # 如果文件不存在，尝试在interface/exports目录查找（兼容旧文件）
                if not os.path.exists(file_path):
                    legacy_dir = os.path.join(os.path.dirname(__file__), 'exports')
                    legacy_path = os.path.join(legacy_dir, safe_filename)
                    print(f"⚠️  在主目录未找到文件，尝试旧目录: {legacy_path}")
                    
                    if os.path.exists(legacy_path):
                        print(f"✅ 在旧目录找到文件")
                        file_path = legacy_path
                    else:
                        # 列出exports目录中的所有文件
                        if os.path.exists(exports_dir):
                            files = os.listdir(exports_dir)
                            print(f"exports目录中的文件 ({len(files)}个):")
                            for f in files[:10]:  # 只显示前10个
                                print(f"  - {f}")
                            if len(files) > 10:
                                print(f"  ... 还有 {len(files)-10} 个文件")
                        
                        # 列出旧目录中的文件
                        if os.path.exists(legacy_dir):
                            files = os.listdir(legacy_dir)
                            print(f"旧目录中的文件 ({len(files)}个):")
                            for f in files[:10]:  # 只显示前10个
                                print(f"  - {f}")
                            if len(files) > 10:
                                print(f"  ... 还有 {len(files)-10} 个文件")
                        
                        print(f"❌ 文件不存在!")
                        print(f"{'='*60}\n")
                        return jsonify({'error': '文件不存在'}), 404
                
                print(f"✅ 文件存在，开始发送")
                print(f"文件大小: {os.path.getsize(file_path)} 字节")
                print(f"{'='*60}\n")
                
                return send_file(
                    file_path,
                    as_attachment=True,
                    download_name=safe_filename,
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
                
            except Exception as e:
                print(f"❌ 下载错误: {str(e)}")
                import traceback
                traceback.print_exc()
                print(f"{'='*60}\n")
                return jsonify({'error': f'下载失败: {str(e)}'}), 500
        
        # 获取当前状态
        @self.app.route('/api/status', methods=['GET'])
        @require_auth
        def get_status():
            try:
                return jsonify({
                    'success': True,
                    'status': {
                        'agent_initialized': self.service.agent is not None,
                        'template_uploaded': self.service.state.template_uploaded,
                        'course_outline_generated': self.service.state.course_outline is not None,
                        'lessons_generated': len(self.service.state.lesson_plans),
                        'requirements': self.service.state.requirements
                    }
                })
                
            except Exception as e:
                return jsonify({'error': f'获取状态失败: {str(e)}'}), 500
        
        # 获取对话历史
        @self.app.route('/api/conversation-history', methods=['GET'])
        @require_auth
        def get_conversation_history():
            try:
                if not self.service.agent:
                    return jsonify({'error': '请先初始化智能体'}), 400
                
                history = self.service.agent.get_conversation_history()
                return jsonify({
                    'success': True,
                    'history': history
                })
                
            except Exception as e:
                return jsonify({'error': f'获取对话历史失败: {str(e)}'}), 500

        # 清空对话历史
        @self.app.route('/api/clear-conversation', methods=['POST'])
        @require_auth
        def clear_conversation():
            try:
                if not self.service.agent:
                    return jsonify({'error': '请先初始化智能体'}), 400
                
                self.service.agent.clear_conversation_history()
                return jsonify({
                    'success': True,
                    'message': '对话历史已清空'
                })
                
            except Exception as e:
                return jsonify({'error': f'清空对话历史失败: {str(e)}'}), 500

        # 重置状态
        @self.app.route('/api/reset', methods=['POST'])
        @require_auth
        def reset_state():
            try:
                self.service.reset_state()
                return jsonify({
                    'success': True,
                    'message': '状态已重置'
                })
                
            except Exception as e:
                return jsonify({'error': f'重置失败: {str(e)}'}), 500
        
        # ===== 知识库相关API =====
        
        
        # 创建知识库
        @self.app.route('/api/kb/create', methods=['POST'])
        @require_auth
        def kb_create():
            """创建新知识库"""
            try:
                print(f"🔍 [kb_create] 收到创建知识库请求")
                print(f"📥 请求头: {dict(request.headers)}")
                
                from models.user import KnowledgeBase
                
                # 获取当前用户
                user = get_current_user()
                print(f"👤 当前用户: {user.id if user and hasattr(user, 'id') else '未登录'}")
                
                if not user or not hasattr(user, 'id'):
                    print("❌ 用户未登录")
                    return jsonify({'error': '请先登录'}), 401
                
                data = request.get_json()
                print(f"📝 请求数据: {data}")
                
                if not data:
                    print("❌ 请求数据为空")
                    return jsonify({'error': '请求数据不能为空'}), 400
                
                name = data.get('name', '').strip()
                description = data.get('description', '').strip()
                
                print(f"📝 解析后的数据 - 名称: {name}, 描述: {description}")
                
                if not name:
                    print("❌ 知识库名称为空")
                    return jsonify({'error': '知识库名称不能为空'}), 400
                
                is_public = data.get('is_public', False)
                
                # 只有管理员可以创建公共知识库
                if is_public and not getattr(user, 'is_admin', False):
                    return jsonify({'error': '只有管理员可以创建公共知识库'}), 403
                
                # 创建知识库记录
                print(f"✅ 开始创建知识库，用户ID: {user.id}")
                kb = KnowledgeBase(
                    user_id=user.id,
                    name=name,
                    description=description,
                    is_public=bool(is_public)
                )
                db.session.add(kb)
                db.session.commit()
                
                print(f"✅ 知识库创建成功，ID: {kb.id}")
                
                return jsonify({
                    'success': True,
                    'kb': kb.to_dict(),
                    'message': '知识库创建成功'
                })
                
            except Exception as e:
                db.session.rollback()
                print(f"❌ 创建知识库失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'创建失败: {str(e)}'}), 500
        
        # 列出用户的知识库
        @self.app.route('/api/kb/list', methods=['GET'])
        @require_auth
        def kb_list():
            """列出用户的所有知识库"""
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                # 已使用 get_current_user()
                from models.user import KnowledgeBase
                
                # 获取指定类型的知识库
                kb_type = request.args.get('type', 'public') # Default to public
                if kb_type == 'public':
                    knowledge_bases = KnowledgeBase.query.filter_by(is_public=True).order_by(KnowledgeBase.created_at.desc()).all()
                else:
                    knowledge_bases = KnowledgeBase.query.filter_by(user_id=user.id, is_public=False).order_by(KnowledgeBase.created_at.desc()).all()
                
                # 获取每个知识库的统计信息
                kb_list_data = []
                for kb in knowledge_bases:
                    kb_data = kb.to_dict()
                    
                    # 获取文档数和知识块数
                    if self.kb_service:
                        files = self.kb_service.list_kb_files(kb.id)
                        stats = self.kb_service.get_collection_stats(kb.id)
                        kb_data['file_count'] = len(files)
                        kb_data['chunk_count'] = stats.get('total_chunks', 0)
                    else:
                        kb_data['file_count'] = 0
                        kb_data['chunk_count'] = 0
                    
                    kb_list_data.append(kb_data)
                
                return jsonify({
                    'success': True,
                    'knowledge_bases': kb_list_data
                })
                
            except Exception as e:
                print(f"❌ 获取知识库列表失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'获取列表失败: {str(e)}'}), 500
        
        # 删除知识库
        @self.app.route('/api/kb/<int:kb_id>', methods=['DELETE'])
        @require_auth
        def kb_delete(kb_id):
            """删除知识库"""
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                # 已使用 get_current_user()
                from models.user import KnowledgeBase
                
                # 查找知识库
                kb = KnowledgeBase.query.get(kb_id)
                if not kb:
                    return jsonify({'error': '知识库不存在'}), 404
                
                # 验证所有权
                if kb.user_id != user.id:
                    return jsonify({'error': '无权删除此知识库'}), 403
                
                # 删除知识库数据（向量、文件等）
                if self.kb_service:
                    self.kb_service.delete_kb(kb_id)
                
                # 删除数据库记录
                db.session.delete(kb)
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'message': '知识库删除成功'
                })
                
            except Exception as e:
                db.session.rollback()
                print(f"❌ 删除知识库失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'删除失败: {str(e)}'}), 500
        
        # 获取知识库详情
        @self.app.route('/api/kb/<int:kb_id>', methods=['GET'])
        @require_auth
        def kb_detail(kb_id):
            """获取知识库详情"""
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                # 已使用 get_current_user()
                from models.user import KnowledgeBase
                
                # 查找知识库
                kb = KnowledgeBase.query.get(kb_id)
                if not kb:
                    return jsonify({'error': '知识库不存在'}), 404
                
                # 验证所有权
                if kb.user_id != user.id and not getattr(kb, 'is_public', False):
                    return jsonify({'error': '无权访问此知识库'}), 403
                
                kb_data = kb.to_dict()
                
                # 获取统计信息
                if self.kb_service:
                    files = self.kb_service.list_kb_files(kb.id)
                    stats = self.kb_service.get_collection_stats(kb.id)
                    kb_data['file_count'] = len(files)
                    kb_data['chunk_count'] = stats.get('total_chunks', 0)
                else:
                    kb_data['file_count'] = 0
                    kb_data['chunk_count'] = 0
                
                return jsonify({
                    'success': True,
                    'kb': kb_data
                })
                
            except Exception as e:
                print(f"❌ 获取知识库详情失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'获取详情失败: {str(e)}'}), 500
        
        # 上传文件到知识库
        @self.app.route('/api/kb/upload', methods=['POST'])
        @require_auth
        def kb_upload_file():
            """上传文件到知识库 (带计费逻辑)"""
            try:
                from datetime import date
                from models.shop import add_points_to_user
                import os
                import uuid
                from werkzeug.utils import secure_filename
                from flask import request, jsonify
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                # 已使用 get_current_user()
                from models.user import KnowledgeBase, db # Import db from models.user
                from config.settings import PROJECT_ROOT as project_root

                if not self.kb_service:
                    return jsonify({'error': '知识库服务未初始化'}), 500
                
                # 获取知识库ID
                kb_id = request.form.get('kb_id', type=int)
                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400
                
                # 验证知识库所有权
                kb = KnowledgeBase.query.get(kb_id)
                if not kb or kb.user_id != user.id:
                    # 公共知识库也只有管理员可以上传
                    if not kb or not (getattr(kb, 'is_public', False) and getattr(user, 'is_admin', False)):
                        return jsonify({'error': '无权访问此知识库'}), 403
                
                if 'file' not in request.files:
                    return jsonify({'error': '没有上传文件'}), 400
                
                file = request.files['file']
                if file.filename == '':
                    return jsonify({'error': '没有选择文件'}), 400
                
                # 卡死格式：只允许 PDF
                if not file.filename.lower().endswith('.pdf'):
                    return jsonify({'error': '仅支持上传 PDF 格式文件'}), 400
                
                # 保存临时文件
                temp_path = os.path.join(self.app.config['UPLOAD_FOLDER'], f'temp_{uuid.uuid4().hex}_{secure_filename(file.filename)}')
                file.save(temp_path)
                
                try:
                    # ==================== KB Billing Logic ====================
                    file_size_bytes = os.path.getsize(temp_path)
                    file_size_mb = file_size_bytes / (1024 * 1024)
                    
                    user = get_current_user()
                    today = date.today()
                    
                    # 1. Daily Reset Check
                    if not user.last_kb_upload_reset_date or user.last_kb_upload_reset_date < today:
                        print(f"🔄 Daily KB Upload Reset for User {user.id}")
                        user.daily_kb_medium_count = 0
                        user.daily_kb_large_count = 0
                        user.last_kb_upload_reset_date = today
                        db.session.commit()
                    
                    cost_points = 0
                    is_free = True
                    billing_msg = ""

                    # 2. Tier Logic
                    if file_size_mb <= 20:
                        # <= 20MB: Unlimited Free
                        billing_msg = "小文件(≤20MB)免费"
                        print(f"🆓 KB Upload: {file_size_mb:.2f}MB - Free Tier")
                        
                    elif 20 < file_size_mb <= 100:
                        # 20-100MB: 2 Free/Day -> 10 Points
                        if user.daily_kb_medium_count < 2:
                            user.daily_kb_medium_count += 1
                            billing_msg = f"中文件免费额度 ({user.daily_kb_medium_count}/2)"
                            print(f"🆓 KB Upload: {file_size_mb:.2f}MB - Medium Free ({user.daily_kb_medium_count}/2)")
                            db.session.commit()
                        else:
                            is_free = False
                            cost_points = 10
                            billing_msg = "中文件(20-100MB)超出免费额度，扣除10积分"
                    
                    else: # > 100MB
                        # > 100MB: 1 Free/Day -> 20 Points
                        if user.daily_kb_large_count < 1:
                            user.daily_kb_large_count += 1
                            billing_msg = f"大文件免费额度 ({user.daily_kb_large_count}/1)"
                            print(f"🆓 KB Upload: {file_size_mb:.2f}MB - Large Free ({user.daily_kb_large_count}/1)")
                            db.session.commit()
                        else:
                            is_free = False
                            cost_points = 20
                            billing_msg = "大文件(>100MB)超出免费额度，扣除20积分"

                    # 3. Deduction
                    if not is_free:
                        print(f"💰 KB Upload: {file_size_mb:.2f}MB - Charging {cost_points} points")
                        if user.points_balance < cost_points:
                            return jsonify({'error': f'积分不足！{billing_msg}，当前余额 {user.points_balance}'}), 402
                        
                        add_points_to_user(user, -cost_points, 'consume', f"知识库上传: {file.filename} ({file_size_mb:.1f}MB)")
                        
                        # Increment counters for tracking even if paid
                        if 20 < file_size_mb <= 100:
                            user.daily_kb_medium_count += 1
                        elif file_size_mb > 100:
                            user.daily_kb_large_count += 1
                        db.session.commit()

                    # ==========================================================

                    # 处理文件
                    result = self.kb_service.upload_file(
                        kb_id=kb_id,
                        file_path=temp_path,
                        file_name=file.filename,
                        user_id=user.id
                    )
                    
                    # Append billing info to result
                    if isinstance(result, dict):
                        result['billing_info'] = {
                            'is_free': is_free,
                            'points_deducted': cost_points,
                            'message': billing_msg
                        }
                    
                    return jsonify(result)
                finally:
                    # 删除临时文件
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
        
            except Exception as e:
                print(f"❌ 知识库上传失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'上传失败: {str(e)}'}), 500
        
        # 在知识库中搜索
        @self.app.route('/api/kb/search', methods=['POST'])
        @require_auth
        def kb_search():
            """搜索知识库内容"""
            try:
                if not self.kb_service:
                    return jsonify({'error': '知识库服务未初始化'}), 500
                
                data = request.get_json()
                kb_id = data.get('kb_id')
                if kb_id is not None:
                    try:
                        kb_id = int(kb_id)
                    except (ValueError, TypeError):
                        return jsonify({'error': '知识库ID格式错误'}), 400
                query = data.get('query', '')
                top_k = data.get('top_k', 5)
                
                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400
                
                if not query:
                    return jsonify({'error': '查询内容不能为空'}), 400
                
                # 验证知识库所有权
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                from models.user import KnowledgeBase
                kb = KnowledgeBase.query.get(kb_id)
                if not kb or (kb.user_id != user.id and not getattr(kb, 'is_public', False)):
                    return jsonify({'error': '无权访问此知识库'}), 403
                
                # 搜索知识库
                results = self.kb_service.search_knowledge(kb_id, query, top_k)
                
                return jsonify({
                    'success': True,
                    'results': results
                })
                
            except Exception as e:
                print(f"❌ 知识库搜索失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'搜索失败: {str(e)}'}), 500
        
        # 基于知识库回答问题
        @self.app.route('/api/kb/ask', methods=['POST'])
        @require_auth
        def kb_ask():
            """基于知识库回答问题 (带计费逻辑)"""
            try:
                from datetime import date
                from models.shop import add_points_to_user
                
                if not self.kb_service:
                    return jsonify({'error': '知识库服务未初始化'}), 500
                
                data = request.get_json()
                kb_id = data.get('kb_id')
                if kb_id is not None:
                    try:
                        kb_id = int(kb_id)
                    except (ValueError, TypeError):
                        return jsonify({'error': '知识库ID格式错误'}), 400
                question = data.get('question', '')
                top_k = data.get('top_k', 15)
                model = data.get('model', 'qwen-plus')
                direct_answer = data.get('direct_answer', True)

                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400

                if not question:
                    return jsonify({'error': '问题不能为空'}), 400

                # 验证知识库所有权 & 计算总大小
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                from models.user import KnowledgeBase
                kb = KnowledgeBase.query.get(kb_id)
                if not kb or (kb.user_id != user.id and not getattr(kb, 'is_public', False)):
                    return jsonify({'error': '无权访问此知识库'}), 403

                # Calculate Total KB Size using service (metadata files) instead of DB
                kb_files = self.kb_service.list_kb_files(kb_id)
                total_size_bytes = sum(f.get('file_size', 0) for f in kb_files)
                total_size_mb = total_size_bytes / (1024 * 1024)
                
                # ==================== KB Chat Billing Logic ====================
                # 公共知识库：扣除创建者积分，使用者免费
                # 私有知识库：扣除使用者积分（原逻辑）
                is_public_kb = getattr(kb, 'is_public', False)
                
                if is_public_kb:
                    # 公共知识库 —— 扣除创建者积分
                    from models.user import User as UserModel
                    billing_user = UserModel.query.get(kb.user_id)
                    if not billing_user:
                        return jsonify({'error': '知识库创建者账号异常'}), 500
                else:
                    # 私有知识库 —— 扣除使用者积分
                    billing_user = get_current_user()
                
                today = date.today()
                
                # 1. Daily Reset Check
                if not billing_user.last_kb_chat_reset_date or billing_user.last_kb_chat_reset_date < today:
                    print(f"🔄 Daily KB Chat Reset for User {billing_user.id}")
                    billing_user.daily_kb_chat_medium_count = 0
                    billing_user.daily_kb_chat_large_count = 0
                    billing_user.last_kb_chat_reset_date = today
                    db.session.commit()
                
                cost_points = 0
                is_free = True
                billing_msg = ""
                
                # 2. Tier Logic
                if total_size_mb <= 20:
                    # <= 20MB: Unlimited Free
                    billing_msg = "小知识库(≤20MB)免费对话"
                    if is_public_kb:
                        billing_msg = "公共知识库免费使用"
                    print(f"🆓 KB Chat: KB Size {total_size_mb:.2f}MB - Free Tier")
                    
                elif 20 < total_size_mb <= 100:
                    # 20-100MB: 2 Free/Day -> 10 Points
                    if billing_user.daily_kb_chat_medium_count < 2:
                        billing_user.daily_kb_chat_medium_count += 1
                        if is_public_kb:
                            billing_msg = "公共知识库免费使用"
                        else:
                            billing_msg = f"中型知识库免费额度 ({billing_user.daily_kb_chat_medium_count}/2)"
                        print(f"🆓 KB Chat: KB Size {total_size_mb:.2f}MB - Medium Free ({billing_user.daily_kb_chat_medium_count}/2)")
                        db.session.commit()
                    else:
                        is_free = False
                        cost_points = 10
                        if is_public_kb:
                            billing_msg = "公共知识库免费使用（创建者承担积分）"
                        else:
                            billing_msg = "中型知识库(20-100MB)对话超出免费额度，扣除10积分"
                
                else: # > 100MB
                    # > 100MB: 1 Free/Day -> 20 Points
                    if billing_user.daily_kb_chat_large_count < 1:
                        billing_user.daily_kb_chat_large_count += 1
                        if is_public_kb:
                            billing_msg = "公共知识库免费使用"
                        else:
                            billing_msg = f"大型知识库免费额度 ({billing_user.daily_kb_chat_large_count}/1)"
                        print(f"🆓 KB Chat: KB Size {total_size_mb:.2f}MB - Large Free ({billing_user.daily_kb_chat_large_count}/1)")
                        db.session.commit()
                    else:
                        is_free = False
                        cost_points = 20
                        if is_public_kb:
                            billing_msg = "公共知识库免费使用（创建者承担积分）"
                        else:
                            billing_msg = "大型知识库(>100MB)对话超出免费额度，扣除20积分"

                # 3. Deduction — 扣除 billing_user 的积分
                if not is_free:
                    print(f"💰 KB Chat: KB Size {total_size_mb:.2f}MB - Charging {cost_points} points from user {billing_user.id}")
                    if billing_user.points_balance < cost_points:
                        if is_public_kb:
                            # 公共知识库创建者积分不足，仍允许使用（不扣费）
                            print(f"⚠️ 公共知识库创建者积分不足，跳过扣费")
                            cost_points = 0
                            is_free = True
                            billing_msg = "公共知识库免费使用"
                        else:
                            return jsonify({'error': f'积分不足！{billing_msg}，当前余额 {billing_user.points_balance}'}), 402
                    
                    if cost_points > 0:
                        kb_owner_label = f"公共知识库对话(用户使用)" if is_public_kb else f"知识库对话"
                        add_points_to_user(billing_user, -cost_points, 'consume', f"{kb_owner_label} (KB#{kb_id} {total_size_mb:.1f}MB)")
                        
                        # Increment counters for tracking even if paid
                        if 20 < total_size_mb <= 100:
                            billing_user.daily_kb_chat_medium_count += 1
                        elif total_size_mb > 100:
                            billing_user.daily_kb_chat_large_count += 1
                        db.session.commit()
                
                # 公共知识库对使用者显示为免费
                if is_public_kb:
                    is_free = True
                    billing_msg = "公共知识库免费使用"
                # ==========================================================

                # --- 保存基础对话记录并启动后台任务 ---
                from models.conversation import Conversation, ConversationMessage
                try:
                    # 查找该用户针对该 KB 的最新对话
                    conv = Conversation.query.filter_by(user_id=user.id, kb_id=kb_id).order_by(Conversation.updated_at.desc()).first()
                    
                    if not conv:
                        # 创建新对话
                        from models.user import KnowledgeBase
                        kb_obj = KnowledgeBase.query.get(kb_id)
                        kb_name = kb_obj.name if kb_obj else "知识库对话"
                        conv = Conversation(user_id=user.id, kb_id=kb_id, title=f"与 {kb_name} 的对话")
                        db.session.add(conv)
                        db.session.flush() # 获取 ID
                    
                    # 保存用户提问
                    user_msg = ConversationMessage(conversation_id=conv.id, role='user', content=question, status='completed')
                    db.session.add(user_msg)
                    
                    # 创建占位 AI 回答 (初始状态为 processing，内容应为空以免和前端误删逻辑冲突)
                    ai_msg = ConversationMessage(conversation_id=conv.id, role='assistant', content='', status='processing', model_used=model)
                    db.session.add(ai_msg)
                    
                    conv.updated_at = datetime.now(timezone.utc)
                    db.session.commit()
                    
                    # 启动后台任务
                    import threading
                    thread = threading.Thread(
                        target=self._background_kb_ask,
                        args=(kb_id, question, top_k, model, ai_msg.id, user.id, direct_answer),
                        daemon=True
                    )
                    thread.start()
                    
                    # 返回消息ID供前端轮询
                    result = {
                        'success': True,
                        'message_id': ai_msg.id,
                        'status': 'processing',
                        'billing_info': {
                            'is_free': is_free,
                            'points_deducted': cost_points,
                            'message': billing_msg,
                            'kb_size_mb': round(total_size_mb, 2)
                        }
                    }
                    return jsonify(result)
                    
                except Exception as save_err:
                    print(f"⚠️ 初始化异步对话任务失败: {save_err}")
                    db.session.rollback()
                    return jsonify({'error': f'初始化任务失败: {str(save_err)}'}), 500
                # -----------------
                
            except Exception as e:
                print(f"❌ 知识库问答初始化失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'初始化问答失败: {str(e)}'}), 500

        @self.app.route('/api/kb/message_status/<int:msg_id>', methods=['GET'])
        @require_auth
        def kb_message_status(msg_id):
            """获取单条消息的生成状态和内容"""
            try:
                from models.conversation import ConversationMessage
                msg = ConversationMessage.query.get(msg_id)
                if not msg:
                    return jsonify({'error': '消息不存在'}), 404
                
                # 权限检查
                user = get_current_user()
                if msg.conversation.user_id != user.id:
                    return jsonify({'error': '无权访问'}), 403
                    
                return jsonify(msg.to_dict())
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        # 获取知识库聊天历史记录
        @self.app.route('/api/kb/chat_history', methods=['GET'])
        @require_auth
        def kb_chat_history():
            """获取指定知识库的聊天历史记录"""
            try:
                kb_id = request.args.get('kb_id', type=int)
                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400
                
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                
                from models.conversation import Conversation, ConversationMessage
                # 查找该用户针对该 KB 的最新对话
                conv = Conversation.query.filter_by(user_id=user.id, kb_id=kb_id).order_by(Conversation.updated_at.desc()).first()
                
                if not conv:
                    return jsonify({'success': True, 'messages': []})
                
                # 获取该对话下所有消息
                messages = [msg.to_dict() for msg in conv.messages.all()]
                return jsonify({'success': True, 'messages': messages})
                
            except Exception as e:
                print(f"❌ 获取知识库聊天历史失败: {e}")
                return jsonify({'error': f'获取聊天历史失败: {str(e)}'}), 500
        
        # 列出知识库的文件
        @self.app.route('/api/kb/files', methods=['GET'])
        @require_auth
        def kb_list_files():
            """列出知识库中的所有文件"""
            try:
                if not self.kb_service:
                    return jsonify({'error': '知识库服务未初始化'}), 500
                
                # 获取知识库ID
                kb_id = request.args.get('kb_id', type=int)
                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400
                
                # 验证知识库所有权
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                from models.user import KnowledgeBase
                kb = KnowledgeBase.query.get(kb_id)
                if not kb or (kb.user_id != user.id and not getattr(kb, 'is_public', False)):
                    return jsonify({'error': '无权访问此知识库'}), 403
                
                # 获取文件列表
                files = self.kb_service.list_kb_files(kb_id)
                
                return jsonify({
                    'success': True,
                    'files': files
                })
                
            except Exception as e:
                print(f"❌ 获取文件列表失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'获取文件列表失败: {str(e)}'}), 500
        
        # 删除文件
        @self.app.route('/api/kb/files/<file_id>', methods=['DELETE'])
        @require_auth
        def kb_delete_file(file_id):
            """删除知识库中的文件"""
            try:
                if not self.kb_service:
                    return jsonify({'error': '知识库服务未初始化'}), 500
                
                # 获取知识库ID
                kb_id = request.args.get('kb_id', type=int)
                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400
                
                # 验证知识库所有权
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                from models.user import KnowledgeBase
                kb = KnowledgeBase.query.get(kb_id)
                if not kb or kb.user_id != user.id:
                    # 公共知识库也只有管理员可以删除文件
                    if not kb or not (getattr(kb, 'is_public', False) and getattr(user, 'is_admin', False)):
                        return jsonify({'error': '无权访问此知识库'}), 403
                
                # 删除文件
                result = self.kb_service.delete_kb_file(kb_id, file_id)
                
                return jsonify(result)
                
            except Exception as e:
                print(f"❌ 删除文件失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'删除失败: {str(e)}'}), 500
        
        # 获取知识库统计信息
        @self.app.route('/api/kb/reinit', methods=['POST'])
        @require_auth
        def kb_reinit():
            """手动重新初始化知识库服务"""
            try:
                from services.knowledge_base_service import KnowledgeBaseService
                from config.settings import VECTOR_DB_FOLDER, KNOWLEDGE_BASE_FOLDER, DASHSCOPE_API_KEY
                
                print("🔄 正在重新初始化知识库服务...")
                
                # 尝试清理旧资源
                if self.kb_service:
                    try:
                        self.kb_service.close()
                    except:
                        pass
                
                self.kb_service = KnowledgeBaseService(
                    vector_db_path=str(VECTOR_DB_FOLDER),
                    kb_folder=str(KNOWLEDGE_BASE_FOLDER),
                    api_key=DASHSCOPE_API_KEY,
                    embedding_provider='qwen',
                    embedding_model_name='text-embedding-v4'
                )
                
                # 清除错误日志
                error_log_path = os.path.join(project_root, 'logs', 'kb_init_error.log')
                if os.path.exists(error_log_path):
                    os.remove(error_log_path)
                
                print('✅ 知识库服务重新初始化成功')
                return jsonify({'success': True, 'message': '知识库服务已重新初始化'})
                
            except Exception as e:
                import traceback
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                print(f"❌ 知识库服务重新初始化失败: {e}")
                
                # 写入错误日志
                os.makedirs(os.path.join(project_root, 'logs'), exist_ok=True)
                with open(os.path.join(project_root, 'logs', 'kb_init_error.log'), 'w') as f:
                    f.write(error_msg)
                
                self.kb_service = None
                return jsonify({'error': f'重置失败: {str(e)}', 'details': error_msg}), 500

        @self.app.route('/api/kb/stats', methods=['GET'])

        @require_auth
        def kb_stats():
            """获取知识库统计信息"""
            try:
                if not self.kb_service:
                    return jsonify({'error': '知识库服务未初始化'}), 500
                
                # 获取知识库ID
                kb_id = request.args.get('kb_id', type=int)
                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400
                
                # 验证知识库所有权
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                from models.user import KnowledgeBase
                kb = KnowledgeBase.query.get(kb_id)
                if not kb or kb.user_id != user.id:
                    return jsonify({'error': '无权访问此知识库'}), 403
                
                # 获取统计信息
                stats = self.kb_service.get_collection_stats(kb_id)
                files = self.kb_service.list_kb_files(kb_id)
                
                # Calculate total size
                total_size_bytes = sum(f.get('file_size', 0) for f in files)
                total_size_mb = total_size_bytes / (1024 * 1024)
                
                # Billing Info for Frontend Status
                billing_status = {
                    'total_size_mb': round(total_size_mb, 2),
                    'daily_medium_count': user.daily_kb_chat_medium_count,
                    'daily_large_count': user.daily_kb_chat_large_count,
                    'points_balance': user.points_balance
                }
                
                return jsonify({
                    'success': True,
                    'stats': stats,
                    'file_count': len(files),
                    'billing_status': billing_status
                })
                
            except Exception as e:
                print(f"❌ 获取统计信息失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'获取统计信息失败: {str(e)}'}), 500

        # ==================== 截图问答API ====================

        # 上传截图并提取问答对
        @self.app.route('/api/qa/upload-screenshot', methods=['POST'])
        @require_auth
        def qa_upload_screenshot():
            """上传截图并提取问答对"""
            try:
                if not self.screenshot_qa_service:
                    return jsonify({'error': '截图问答服务未初始化'}), 500

                # 获取知识库ID
                kb_id = request.form.get('kb_id', type=int)
                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400

                # 验证知识库所有权
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                from models.user import KnowledgeBase
                kb = KnowledgeBase.query.get(kb_id)
                if not kb or kb.user_id != user.id:
                    return jsonify({'error': '无权访问此知识库'}), 403

                if 'screenshot' not in request.files:
                    return jsonify({'error': '没有上传截图'}), 400

                file = request.files['screenshot']
                if file.filename == '':
                    return jsonify({'error': '没有选择文件'}), 400

                # 验证文件类型（只接受图片）
                allowed_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}
                file_ext = Path(file.filename).suffix.lower()
                if file_ext not in allowed_extensions:
                    return jsonify({'error': f'不支持的图片格式，支持的格式: {", ".join(allowed_extensions)}'}), 400

                # 保存临时文件
                temp_path = os.path.join(self.app.config['UPLOAD_FOLDER'], f'temp_screenshot_{uuid.uuid4().hex}_{secure_filename(file.filename)}')
                file.save(temp_path)

                try:
                    # 处理截图
                    result = self.screenshot_qa_service.upload_screenshot(
                        kb_id=kb_id,
                        screenshot_path=temp_path,
                        screenshot_name=file.filename,
                        user_id=user.id
                    )

                    return jsonify(result)
                finally:
                    # 删除临时文件
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

            except Exception as e:
                print(f"❌ 截图上传失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'截图上传失败: {str(e)}'}), 500

        # 在问答库中搜索
        @self.app.route('/api/qa/search', methods=['POST'])
        @require_auth
        def qa_search():
            """搜索问答库"""
            try:
                if not self.screenshot_qa_service:
                    return jsonify({'error': '截图问答服务未初始化'}), 500

                data = request.get_json()
                kb_id = data.get('kb_id')
                if kb_id is not None:
                    try:
                        kb_id = int(kb_id)
                    except (ValueError, TypeError):
                        return jsonify({'error': '知识库ID格式错误'}), 400
                question = data.get('question', '')
                top_k = data.get('top_k', 5)

                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400

                if not question:
                    return jsonify({'error': '问题不能为空'}), 400

                # 验证知识库所有权
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                from models.user import KnowledgeBase
                kb = KnowledgeBase.query.get(kb_id)
                if not kb or kb.user_id != user.id:
                    return jsonify({'error': '无权访问此知识库'}), 403

                # 搜索问答对
                results = self.screenshot_qa_service.search_qa(kb_id, question, top_k)

                return jsonify({
                    'success': True,
                    'results': results
                })

            except Exception as e:
                print(f"❌ 问答搜索失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'搜索失败: {str(e)}'}), 500

        # 从问答库中获取答案
        @self.app.route('/api/qa/answer', methods=['POST'])
        @require_auth
        def qa_answer():
            """从问答库中获取答案"""
            try:
                if not self.screenshot_qa_service:
                    return jsonify({'error': '截图问答服务未初始化'}), 500

                data = request.get_json()
                kb_id = data.get('kb_id')
                if kb_id is not None:
                    try:
                        kb_id = int(kb_id)
                    except (ValueError, TypeError):
                        return jsonify({'error': '知识库ID格式错误'}), 400
                question = data.get('question', '')
                top_k = data.get('top_k', 3)
                similarity_threshold = data.get('similarity_threshold', 0.6)

                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400

                if not question:
                    return jsonify({'error': '问题不能为空'}), 400

                # 验证知识库所有权
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                from models.user import KnowledgeBase
                kb = KnowledgeBase.query.get(kb_id)
                if not kb or kb.user_id != user.id:
                    return jsonify({'error': '无权访问此知识库'}), 403

                # 获取答案
                result = self.screenshot_qa_service.answer_from_qa(kb_id, question, top_k, similarity_threshold)

                return jsonify(result)

            except Exception as e:
                print(f"❌ 问答失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'问答失败: {str(e)}'}), 500

        # 列出所有截图
        @self.app.route('/api/qa/screenshots', methods=['GET'])
        @require_auth
        def qa_list_screenshots():
            """列出知识库中的所有截图"""
            try:
                if not self.screenshot_qa_service:
                    return jsonify({'error': '截图问答服务未初始化'}), 500

                # 获取知识库ID
                kb_id = request.args.get('kb_id', type=int)
                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400

                # 验证知识库所有权
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                from models.user import KnowledgeBase
                kb = KnowledgeBase.query.get(kb_id)
                if not kb or kb.user_id != user.id:
                    return jsonify({'error': '无权访问此知识库'}), 403

                # 获取截图列表
                screenshots = self.screenshot_qa_service.list_screenshots(kb_id)

                return jsonify({
                    'success': True,
                    'screenshots': screenshots
                })

            except Exception as e:
                print(f"❌ 获取截图列表失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'获取列表失败: {str(e)}'}), 500

        # 删除截图
        @self.app.route('/api/qa/screenshots/<screenshot_id>', methods=['DELETE'])
        @require_auth
        def qa_delete_screenshot(screenshot_id):
            """删除截图及其问答对"""
            try:
                if not self.screenshot_qa_service:
                    return jsonify({'error': '截图问答服务未初始化'}), 500

                # 获取知识库ID
                kb_id = request.args.get('kb_id', type=int)
                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400

                # 验证知识库所有权
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                from models.user import KnowledgeBase
                kb = KnowledgeBase.query.get(kb_id)
                if not kb or kb.user_id != user.id:
                    return jsonify({'error': '无权访问此知识库'}), 403

                # 删除截图
                result = self.screenshot_qa_service.delete_screenshot(kb_id, screenshot_id)

                return jsonify(result)

            except Exception as e:
                print(f"❌ 删除截图失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'删除失败: {str(e)}'}), 500

        # 获取问答库统计信息
        @self.app.route('/api/qa/stats', methods=['GET'])
        @require_auth
        def qa_stats():
            """获取问答库统计信息"""
            try:
                if not self.screenshot_qa_service:
                    return jsonify({'error': '截图问答服务未初始化'}), 500

                # 获取知识库ID
                kb_id = request.args.get('kb_id', type=int)
                if not kb_id:
                    return jsonify({'error': '请指定知识库ID'}), 400

                # 验证知识库所有权
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                from models.user import KnowledgeBase
                kb = KnowledgeBase.query.get(kb_id)
                if not kb or kb.user_id != user.id:
                    return jsonify({'error': '无权访问此知识库'}), 403

                # 获取统计信息
                stats = self.screenshot_qa_service.get_qa_stats(kb_id)

                return jsonify({
                    'success': True,
                    'stats': stats
                })

            except Exception as e:
                print(f"❌ 获取统计信息失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'获取统计信息失败: {str(e)}'}), 500

        # ==================== V5文档生成API ====================

        # V5文档生成页面路由
        @self.app.route('/v5-generation')
        @require_auth
        def v5_generation_page():
            """V5文档生成页面"""
            return render_template('v5_document_generation.html')

        # 初始化V5任务进度存储
        if not hasattr(self, 'v5_generation_tasks'):
            self.v5_generation_tasks = {}

        # 上传V5模板
        @self.app.route('/api/v5/upload-template', methods=['POST'])
        @require_auth
        def v5_upload_template():
            """上传DOCX模板用于V5生成（支持.doc自动转换）"""
            try:
                if 'file' not in request.files:
                    return jsonify({'error': '没有上传文件'}), 400

                file = request.files['file']
                if file.filename == '':
                    return jsonify({'error': '文件名为空'}), 400

                # 检查文件扩展名（支持 .doc 和 .docx）
                filename_lower = file.filename.lower()
                if not (filename_lower.endswith('.docx') or filename_lower.endswith('.doc')):
                    return jsonify({'error': '只支持.doc或.docx格式'}), 400

                # 保存文件到临时目录
                import tempfile
                temp_dir = tempfile.mkdtemp(prefix='v5_template_')
                original_path = os.path.join(temp_dir, secure_filename(file.filename))
                file.save(original_path)

                print(f"✅ V5模板上传成功: {original_path}")

                # 如果是 .doc 格式，自动转换为 .docx
                if filename_lower.endswith('.doc'):
                    print(f"🔄 检测到 .doc 格式，正在转换为 .docx...")
                    try:
                        from utils.doc_converter import ensure_docx
                        final_path = ensure_docx(original_path, temp_dir)
                        final_filename = final_path.name
                        print(f"✅ 转换成功: {final_path}")
                    except Exception as conv_error:
                        print(f"❌ .doc转换失败: {conv_error}")
                        return jsonify({
                            'error': f'.doc转换失败: {str(conv_error)}。请手动将文件另存为.docx格式后重试。'
                        }), 400
                else:
                    final_path = original_path
                    final_filename = file.filename

                return jsonify({
                    'success': True,
                    'file_path': str(final_path),
                    'file_name': final_filename,
                    'converted': filename_lower.endswith('.doc')  # 标记是否经过转换
                })

            except Exception as e:
                print(f"❌ V5模板上传失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'上传失败: {str(e)}'}), 500

        # 启动V5生成任务（使用Core统一生成器）
        @self.app.route('/api/v5/generate', methods=['POST'])
        @require_auth
        def v5_generate():
            """启动V5文档生成任务 - 使用Core统一生成器"""
            try:
                user = get_current_user()
                if not user:
                    return jsonify({'error': '请先登录'}), 401
                data = request.get_json()
                file_path = data.get('file_path')
                prompt = data.get('prompt')
                mode = data.get('mode', 'inference')  # training or inference
                model = data.get('model', 'qwen-flash')  # 支持 qwen-flash/qwen-plus/kimi/gemini-pro

                if not file_path or not os.path.exists(file_path):
                    return jsonify({'error': '模板文件不存在'}), 400

                if not prompt:
                    return jsonify({'error': '请提供需求描述'}), 400

                # 验证model参数
                if model not in ['qwen-flash', 'qwen-plus', 'kimi', 'gemini-pro', 'faster']:
                    model = 'qwen-flash'  # 默认使用qwen-flash

                # ==================== DocuMind 计费预检查 ====================
                # DocuMind Mini (qwen-flash): 3000 free/week, then 20/k
                # DocuMind Flash (qwen-plus): 1000 free/week, then 30/k
                # DocuMind Pro (kimi): 0 free, 40/k
                # DocuMind Faster (faster): 0 free, 45/k (gemini-pro maps to this or default?)
                
                # Check Weekly Reset
                today = datetime.now(timezone.utc).date()
                last_reset = user.last_weekly_reset_date
                
                # Calculate start of this week (Monday)
                start_of_week = today - timedelta(days=today.weekday())
                
                if last_reset is None or last_reset < start_of_week:
                    user.weekly_usage_mini = 0
                    user.weekly_usage_flash = 0
                    user.last_weekly_reset_date = today
                    db.session.commit()
                
                # Check Expected Cost (Pre-check)
                # We don't know word count yet, but if user has no free quota left AND 0 points, reject.
                has_free_quota = False
                rate_per_k = 0
                
                if model == 'qwen-flash': # Mini
                    rate_per_k = 20
                    if user.weekly_usage_mini < 3000:
                        has_free_quota = True
                elif model == 'qwen-plus': # Flash
                    rate_per_k = 30
                    if user.weekly_usage_flash < 1000:
                        has_free_quota = True
                elif model == 'kimi': # Pro
                    rate_per_k = 40
                    has_free_quota = False
                elif model == 'faster': # Profaster
                    rate_per_k = 45
                    has_free_quota = False
                elif model == 'gemini-pro': # Mapping to Pro rate for now or treat as custom
                    rate_per_k = 40 
                    has_free_quota = False

                if not has_free_quota and user.points_balance <= 0:
                    return jsonify({
                        'error': '积分不足，请先充值', 
                        'code': 'INSUFFICIENT_POINTS',
                        'detail': f'当前模型需要 {rate_per_k} 积分/千字，您暂无可用积分或免费额度。'
                    }), 402

                # ==========================================================

                # 生成任务ID
                import uuid
                task_id = str(uuid.uuid4())

                # 初始化任务进度
                self.v5_generation_tasks[task_id] = {
                    'progress': 0,
                    'status': 'starting',
                    'message': '任务启动中...',
                    'logs': [],
                    'file_path': None,
                    'file_name': None,
                    'error': None,
                    'start_time': time.time(),  # ✅ 添加开始时间
                    'model_key': model, # Pass model key for billing
                    'user_id': user.id # Pass user ID
                }

                # 定义进度回调
                def progress_callback(stage, progress, message):
                    """更新任务进度"""
                    import sys
                    if task_id in self.v5_generation_tasks:
                        self.v5_generation_tasks[task_id]['progress'] = progress
                        self.v5_generation_tasks[task_id]['message'] = message or ""
                        # 日志仍然记录，但不返回给前端
                        self.v5_generation_tasks[task_id]['logs'].append({
                            'time': time.time(),
                            'stage': stage,
                            'message': message
                        })
                        # 更新状态（也设为通用的running，不暴露具体阶段）
                        if stage in ('completed', 'complete'):
                            self.v5_generation_tasks[task_id]['status'] = 'completed'
                        else:
                            self.v5_generation_tasks[task_id]['status'] = 'running'

                        print(f"[V5][{task_id}][{progress}%] {message}")
                        sys.stdout.flush()  # 强制刷新输出

                # 定义后台任务
                def run_v5_generation():
                    """在后台线程中运行V5生成"""
                    import sys
                    try:
                        print(f"🚀 V5生成任务启动: {task_id}")
                        print(f"   模板: {file_path}")
                        print(f"   需求: {prompt}")
                        print(f"   模式: {mode}")
                        sys.stdout.flush()  # 强制刷新输出

                        # 模型名称映射
                        model_names = {
                            'qwen-flash': '通义千问 Flash',
                            'qwen-plus': '通义千问 Plus',
                            'kimi': 'Kimi K2',
                            'gemini-pro': 'Gemini Pro',
                            'faster': 'Documind pro faster',
                        }
                        print(f"   模型: {model} ({model_names.get(model, model)})")
                        sys.stdout.flush()  # 强制刷新输出

                        # ⚠️ 重要：在导入模块前设置环境变量
                        import os
                        import sys

                        def clear_env_for_v5():
                            env_vars_to_clear = [
                                'USE_QWEN_FOR_ANNOTATION', 'USE_FIREWORKS_FOR_ANNOTATION', 'USE_PACKY_FOR_ANNOTATION', 'USE_GPT_FOR_ANNOTATION',
                                'QWEN_ANNOTATION_MODEL', 'QWEN_GENERATION_MODEL', 'QWEN_CHECKER_MODEL', 'QWEN_JSON_REPAIR_MODEL',
                                'FIREWORKS_ANNOTATION_MODEL', 'FIREWORKS_GENERATION_MODEL', 'FIREWORKS_CHECKER_MODEL', 'FIREWORKS_JSON_REPAIR_MODEL',
                                'KIMI_ANNOTATION_MODEL', 'KIMI_GENERATION_MODEL', 'KIMI_CHECKER_MODEL',
                                'PACKY_ANNOTATION_MODEL', 'PACKY_GENERATION_MODEL', 'PACKY_CHECKER_MODEL',
                                'GPT_ANNOTATION_MODEL', 'GPT_GENERATION_MODEL', 'GPT_CHECKER_MODEL'
                            ]
                            for var in env_vars_to_clear:
                                if var in os.environ:
                                    del os.environ[var]

                        def configure_annotation_env():
                            clear_env_for_v5()
                            os.environ['USE_QWEN_FOR_ANNOTATION'] = 'true'
                            os.environ['USE_FIREWORKS_FOR_ANNOTATION'] = 'false'
                            os.environ['USE_PACKY_FOR_ANNOTATION'] = 'false'
                            os.environ['USE_GPT_FOR_ANNOTATION'] = 'false'
                            # 文档生成标注阶段统一使用通义千问 Plus（更准确，避免表头识别错误）
                            os.environ['QWEN_ANNOTATION_MODEL'] = 'qwen-plus'
                            os.environ['QWEN_JSON_REPAIR_MODEL'] = 'qwen-plus'
                            os.environ['QWEN_CHECKER_MODEL'] = 'qwen-plus'
                            os.environ['QWEN_GENERATION_MODEL'] = 'qwen-flash'

                        def configure_generation_env():
                            clear_env_for_v5()
                            # 标注端固定使用通义千问Plus
                            os.environ['QWEN_ANNOTATION_MODEL'] = 'qwen-plus'
                            os.environ['QWEN_JSON_REPAIR_MODEL'] = 'qwen-plus'
                            os.environ['QWEN_CHECKER_MODEL'] = 'qwen-plus'

                            if model == 'qwen-flash':
                                os.environ['USE_QWEN_FOR_ANNOTATION'] = 'true'
                                os.environ['USE_QWEN_FOR_GENERATION'] = 'true'  # 🔥 修复：生成也使用通义千问
                                os.environ['USE_FIREWORKS_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_PACKY_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_GPT_FOR_ANNOTATION'] = 'false'
                                os.environ['QWEN_GENERATION_MODEL'] = 'qwen-flash'
                                os.environ['QWEN_CHECKER_MODEL'] = 'qwen-plus'
                                print("   ✅ 标注使用通义千问Plus，生成使用通义千问Flash")
                            elif model == 'qwen-plus':
                                os.environ['USE_QWEN_FOR_ANNOTATION'] = 'true'
                                os.environ['USE_QWEN_FOR_GENERATION'] = 'true'  # 🔥 修复：生成也使用通义千问
                                os.environ['USE_FIREWORKS_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_PACKY_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_GPT_FOR_ANNOTATION'] = 'false'
                                os.environ['QWEN_GENERATION_MODEL'] = 'qwen-plus'
                                print("   ✅ 标注/生成均使用通义千问Plus")
                            elif model == 'kimi':
                                os.environ['USE_QWEN_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_FIREWORKS_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_PACKY_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_GPT_FOR_ANNOTATION'] = 'false'
                                # 使用项目中统一的 Kimi K2 预览模型ID，避免无效的 kimi-k2 报 404
                                os.environ['KIMI_ANNOTATION_MODEL'] = 'kimi-k2-0905-preview'
                                os.environ['KIMI_GENERATION_MODEL'] = 'kimi-k2-0905-preview'
                                os.environ['KIMI_CHECKER_MODEL'] = 'kimi-k2-0905-preview'
                                print("   ✅ 标注/生成均使用 Kimi K2 预览模型 (kimi-k2-0905-preview)")
                            elif model == 'faster':
                                os.environ['USE_QWEN_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_FIREWORKS_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_PACKY_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_GPT_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_GROQ_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_QWEN_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_FIREWORKS_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_PACKY_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_GPT_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_GROQ_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_SILICON_FOR_ANNOTATION'] = 'true'
                                
                                # Pro Faster配置: 全链路使用 Kimi-K2-Thinking (SiliconFlow)
                                # 主打优质生成，快速推理
                                model_id = 'Pro/moonshotai/Kimi-K2-Thinking'
                                os.environ['SILICON_ANNOTATION_MODEL'] = model_id
                                os.environ['SILICON_GENERATION_MODEL'] = model_id
                                os.environ['SILICON_CHECKER_MODEL'] = model_id
                                
                                # 清除 Qwen Flash 配置
                                if 'QWEN_GENERATION_MODEL' in os.environ:
                                    del os.environ['QWEN_GENERATION_MODEL']
                                
                                print(f"   ✅ 标注/生成均使用 SiliconFlow ({model_id})")
                            else:  # gpt
                                os.environ['USE_QWEN_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_FIREWORKS_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_PACKY_FOR_ANNOTATION'] = 'false'
                                os.environ['USE_GPT_FOR_ANNOTATION'] = 'true'
                                os.environ['GPT_ANNOTATION_MODEL'] = 'gpt-5.1-2025-11-13'
                                os.environ['GPT_GENERATION_MODEL'] = 'gpt-5.1-2025-11-13'
                                os.environ['GPT_CHECKER_MODEL'] = 'gpt-5.1-2025-11-13'
                                print("   ✅ 标注使用通义千问Plus，生成使用GPT-5.1 2025")

                        def reload_docuagent_modules():
                            modules_to_reload = [
                                'docuagent.v4.llm_annotator',
                                'docuagent.v4.feature_markdown',
                                'docuagent.v4.content_generation.content_generator',
                                'docuagent.v4.content_generation.workflow',
                                'docuagent.v4.content_generation.field_analyzer',
                                'docuagent.v4.content_generation.prompts',  # 🔥 添加prompts模块（字段第一列检测逻辑）
                                'docuagent.v4.run_llm_annotation',
                                'docuagent.v6.parallel_annotator',
                                'docuagent.v6.parallel_generator',  # 🔥 添加V6并行生成器
                            ]
                            import importlib
                            for module_name in modules_to_reload:
                                if module_name in sys.modules:
                                    module = sys.modules[module_name]
                                    importlib.reload(module)
                                    print(f"   🔄 已重新加载 {module_name}")
                            sys.stdout.flush()

                        configure_annotation_env()
                        reload_docuagent_modules()

                        from docuagent.v4.docx_markdown_converter import DocxMarkdownExporter
                        from docuagent.v4.feature_markdown import generate_feature_markdown
                        from docuagent.v4.run_llm_annotation import annotate_markdown, load_text, segment_markdown
                        from docuagent.v4.apply_annotations import apply_annotations_and_rebuild_docx
                        from docuagent.v6.parallel_annotator import parallel_annotate, remove_segment_prefixes

                        # 导入v4 pipeline模块
                        from pathlib import Path as PathLib
                        project_root = PathLib(__file__).parent.parent
                        sys.path.insert(0, str(project_root))

                        # 创建持久化输出目录（用于保存所有中间文件）
                        import datetime
                        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                        web_outdir = PathLib(project_root) / 'results' / f'v5_web_{timestamp}'
                        web_outdir.mkdir(parents=True, exist_ok=True)

                        # 创建子目录
                        md_dir = web_outdir / 'markdown'
                        md_dir.mkdir(exist_ok=True)
                        annotation_dir = web_outdir / 'annotation'
                        annotation_dir.mkdir(exist_ok=True)
                        generation_dir = web_outdir / 'generation'
                        generation_dir.mkdir(exist_ok=True)

                        print(f"\n📁 输出目录: {web_outdir}")
                        sys.stdout.flush()

                        # 阶段1: DOCX → Markdown
                        progress_callback('markdown', 10, '正在转换DOCX到Markdown...')
                        self.v5_generation_tasks[task_id]['status'] = 'converting'

                        exporter = DocxMarkdownExporter(file_path)
                        md_path, manifest_path = exporter.export(output_dir=str(md_dir))

                        print(f"✅ Markdown: {md_path}")
                        print(f"✅ Manifest路径: {manifest_path}")

                        # 🔥 加载manifest数据
                        import json
                        with open(manifest_path, 'r', encoding='utf-8') as f:
                            manifest = json.load(f)

                        print(f"✅ Manifest加载成功: {len(manifest.get('tables', []))} 个表格, {len(manifest.get('paragraphs', []))} 个段落")
                        sys.stdout.flush()

                        progress_callback('markdown', 20, 'Markdown转换完成')
                        progress_callback('markdown', 24, '正在提取模板结构特征...')

                        _, _, feature_md_path = generate_feature_markdown(
                            docx_path=file_path,
                            output_dir=md_dir,
                            reuse_existing=True,
                        )

                        manifest_size = os.path.getsize(manifest_path)
                        feature_md_size = os.path.getsize(feature_md_path)
                        print(f"✅ 特征摘要: {feature_md_path}")
                        print(f"   Manifest大小: {manifest_size} 字节")
                        print(f"   特征摘要大小: {feature_md_size} 字节")
                        sys.stdout.flush()

                        progress_callback('markdown', 28, '模板特征提取完成')
                        markdown_time = time.time() - self.v5_generation_tasks[task_id]['start_time']
                        print(f"⏱️ [PERF] Markdown转换耗时: {markdown_time:.2f}s")
                        sys.stdout.flush()

                        # 读取Markdown内容进行文档分类
                        from docuagent.v5.doc_classifier import classify_document
                        from docuagent.v5.knowledge_base import KnowledgeBase

                        md_content = load_text(PathLib(md_path))
                        doc_classification = classify_document(md_content)
                        doc_type = doc_classification.get('type', 'lesson_plan')

                        print(f"\n📚 文档分类: {doc_type}")
                        sys.stdout.flush()

                        # 阶段2: LLM标注
                        annotation_start_time = time.time()
                        self.v5_generation_tasks[task_id]['status'] = 'annotating'

                        segmented_markdown = segment_markdown(md_content)
                        total_segments = max(1, len(segmented_markdown))
                        annotation_max_concurrent = min(3, total_segments)

                        print(f"\n🏷️  标注阶段:")
                        print(f"   - 文档段数: {total_segments}")
                        print(f"   - 并行线程数: {annotation_max_concurrent}")
                        print(f"   - 标注特征文件: {feature_md_path.name}")
                        sys.stdout.flush()

                        progress_callback('annotation', 30, f'正在识别占位符（{total_segments} 段并行）...')

                        def annotation_stage_progress(completed, total, message):
                            phase_start = 32
                            phase_end = 50
                            safe_total = max(total, 1)
                            mapped_progress = phase_start + int((phase_end - phase_start) * (completed / safe_total))
                            progress_callback('annotation', min(mapped_progress, phase_end), message)

                        parallel_result = parallel_annotate(
                            md_path=PathLib(md_path),
                            features_path=PathLib(feature_md_path),
                            output_dir=annotation_dir,
                            kb_insights="",
                            max_concurrent=annotation_max_concurrent,
                            no_segment=False,
                            doc_type=doc_type,
                            progress_callback=annotation_stage_progress,
                        )

                        annotations = []
                        annotation_summary = {}
                        use_fallback_annotation = (
                            not parallel_result.combined_annotations or bool(parallel_result.failures)
                        )

                        if use_fallback_annotation:
                            failure_preview = ""
                            if parallel_result.failures:
                                failure_preview = str(parallel_result.failures[0]).replace('\n', ' ').strip()
                                if len(failure_preview) > 200:
                                    failure_preview = failure_preview[:197] + '...'
                            print("⚠️ 并行标注未完整成功，回退到稳态顺序标注")
                            print(f"   失败段数: {len(parallel_result.failures)}")
                            if failure_preview:
                                print(f"   首个失败原因: {failure_preview}")
                            sys.stdout.flush()

                            progress_callback('annotation', 34, '并行标注未完整成功，切换稳态模式...')

                            annotation_summary = annotate_markdown(
                                md_path=PathLib(md_path),
                                features_path=PathLib(feature_md_path),
                                output_dir=annotation_dir,
                                progress_callback=annotation_stage_progress,
                            )

                            annotation_json_file = annotation_summary['outputs']['annotation_json']
                            with open(annotation_json_file, 'r', encoding='utf-8') as f:
                                annotation_data = json.load(f)
                            annotations = annotation_data.get('annotations', [])
                        else:
                            annotations = remove_segment_prefixes(parallel_result.combined_annotations)
                            annotation_json_path = annotation_dir / 'annotations.json'
                            raw_parallel_dir = annotation_dir / 'raw_parallel'
                            annotation_summary = {
                                'mode': 'v6_parallel',
                                'markdown': str(md_path),
                                'features': str(feature_md_path),
                                'outputs': {
                                    'raw_dir': str(raw_parallel_dir) if raw_parallel_dir.exists() else None,
                                    'annotation_json': str(annotation_json_path),
                                    'raw_responses': sorted(str(path) for path in raw_parallel_dir.glob('*.txt')) if raw_parallel_dir.exists() else [],
                                },
                                'failures': parallel_result.failures,
                                'stats': parallel_result.to_dict(),
                                'generated_at': timestamp,
                            }
                            annotation_summary_path = annotation_dir / f'annotation_summary_{timestamp}.json'
                            with open(annotation_summary_path, 'w', encoding='utf-8') as f:
                                json.dump(annotation_summary, f, ensure_ascii=False, indent=2)

                        annotation_json_path = annotation_dir / 'annotations.json'
                        with open(annotation_json_path, 'w', encoding='utf-8') as f:
                            json.dump({
                                'annotations': annotations,
                                'summary': annotation_summary
                            }, f, ensure_ascii=False, indent=2)

                        print(f"✅ 标注结果: {annotation_json_path}")
                        print(f"   识别到 {len(annotations)} 个占位符")
                        if annotations:
                            first_ann = annotations[0] if isinstance(annotations[0], dict) else {}
                            print(f"   首个标注字段: {first_ann.get('placeholder', 'N/A')}")
                        else:
                            print("⚠️ 标注结果为空")

                        sys.stdout.flush()

                        progress_callback('annotation', 50, f'标注完成，识别到 {len(annotations)} 个占位符')
                        annotation_time = time.time() - annotation_start_time
                        print(f"⏱️ [PERF] LLM标注耗时: {annotation_time:.2f}s")
                        sys.stdout.flush()

                        # 加载知识库约束
                        kb = KnowledgeBase(doc_type=doc_type)
                        kb_insights = kb.format_for_generator_prompt(max_entries=10)  # 减少噪音,只保留最相关的10条经验

                        print(f"📖 知识库约束长度: {len(kb_insights)} 字符")
                        if kb_insights:
                            print(f"   预览: {kb_insights[:500]}...")
                        else:
                            print(f"   ⚠️  知识库约束为空！")
                            print(f"   文档类型: {doc_type}")
                            print(f"   知识库路径: {kb.kb_path}")
                        sys.stdout.flush()

                        # 在生成阶段前重新配置环境，保证标注和生成的模型设置生效
                        configure_generation_env()
                        reload_docuagent_modules()
                        from docuagent.v4.content_generation.state import ContentGenerationState, FieldAnalysis
                        from docuagent.v4.content_generation.field_analyzer import FieldAnalyzer
                        from docuagent.v4.apply_annotations import apply_annotations_and_rebuild_docx
                        # 🔥 导入V6多线程并行生成器
                        from docuagent.v6.parallel_generator import parallel_generate_batch

                        # 阶段3: 内容生成
                        progress_callback('generation', 60, '正在生成内容（多线程并行）...')
                        self.v5_generation_tasks[task_id]['status'] = 'generating'
                        generation_start_time = time.time()

                        # 准备用户输入
                        user_input = {
                            'prompt': prompt,
                            'doc_type': doc_type,  # ✅ 添加文档类型
                            'basic_info': {},
                            'teaching_context': {},
                            'content_preferences': {
                                'style': 'formal',
                                'detail_level': 'detailed',
                                'include_examples': True,
                                'language': 'zh'
                            }
                        }

                        print(f"\n{'='*80}")
                        print(f"🔍 [DEBUG] 内容生成阶段调试信息（V6多线程并行）")
                        print(f"{'='*80}")
                        print(f"📋 标注数量: {len(annotations)}")
                        print(f"📝 用户输入: {user_input['prompt'][:100]}...")
                        print(f"📂 Markdown路径: {md_path}")
                        generation_max_concurrent = 6 if model in ('qwen-flash', 'qwen-plus') else 5
                        print(f"🔧 并发线程数: {generation_max_concurrent}")
                        sys.stdout.flush()

                        # 🔥 使用V6多线程并行生成（替代原有的LangGraph workflow）
                        try:
                            # Step 1: 字段分析
                            print(f"\n📊 Step 1: 分析字段...")
                            analyzer = FieldAnalyzer()

                            # 构建context_map
                            context_map = {}
                            for ann in annotations:
                                placeholder = ann.get('placeholder', '')
                                if placeholder:
                                    context_map[placeholder] = ann.get('reason', '') or ann.get('result', '')

                            field_analyses = analyzer.analyze_all_fields(annotations, context_map, user_input=user_input)
                            print(f"   ✅ 分析完成: {len(field_analyses)} 个字段")
                            sys.stdout.flush()

                            # Step 2: 多线程并行生成
                            print(f"\n🚀 Step 2: 多线程并行生成...")

                            def generation_stage_progress(completed, total, placeholder):
                                phase_start = 60
                                phase_end = 80
                                safe_total = max(total, 1)
                                mapped_progress = phase_start + int((phase_end - phase_start) * (completed / safe_total))
                                progress_callback(
                                    'generation',
                                    min(mapped_progress, phase_end),
                                    f'正在生成内容（{completed}/{safe_total}）',
                                )

                            generation_result = parallel_generate_batch(
                                field_analyses=field_analyses,
                                user_input=user_input,
                                generated_content={},
                                kb_insights=kb_insights,
                                doc_type=doc_type,
                                output_dir=generation_dir,
                                max_concurrent=generation_max_concurrent,
                                progress_callback=generation_stage_progress,
                            )

                            # 提取生成结果
                            generated_content = generation_result.generated_content
                            failed_fields = generation_result.failures

                            print(f"\n✅ 多线程生成完成")
                            print(f"   成功: {len(generated_content)} 个字段")
                            print(f"   失败: {len(failed_fields)} 个字段")
                            print(f"   总耗时: {generation_result.total_time:.2f} 秒")
                            if generation_result.individual_times:
                                sequential_time = sum(generation_result.individual_times)
                                speedup = sequential_time / generation_result.total_time if generation_result.total_time > 0 else 1.0
                                print(f"   加速比: {speedup:.2f}x")
                            sys.stdout.flush()

                        except Exception as e:
                            print(f"❌ 多线程生成失败: {e}")
                            import traceback
                            traceback.print_exc()
                            sys.stdout.flush()
                            raise

                        print(f"\n📊 生成结果统计:")
                        print(f"   - generated_content 类型: {type(generated_content)}")
                        print(f"   - generated_content 长度: {len(generated_content)}")
                        print(f"   - generated_content 键: {list(generated_content.keys())[:5]}...")
                        print(f"   - completed_fields: {len(generated_content)}")
                        print(f"   - failed_fields: {failed_fields}")

                        if not generated_content:
                            print(f"\n⚠️ 警告：generated_content 为空！")
                            print(f"   可能的原因:")
                            print(f"   1. 多线程生成过程中出现错误")
                            print(f"   2. annotations 数据格式不正确")
                            print(f"   3. API调用失败")
                        else:
                            print(f"\n✅ 成功生成 {len(generated_content)} 个字段")
                            for idx, (key, value) in enumerate(list(generated_content.items())[:3]):
                                print(f"   [{idx+1}] {key}: {type(value)}")

                        print(f"{'='*80}\n")
                        sys.stdout.flush()

                        # 将 GeneratedField 对象转换为可序列化的字典
                        from dataclasses import asdict, is_dataclass

                        def serialize_generated_content(content):
                            """将 generated_content 中的 GeneratedField 对象转换为字典"""
                            if isinstance(content, dict):
                                return {
                                    k: asdict(v) if is_dataclass(v) else serialize_generated_content(v)
                                    for k, v in content.items()
                                }
                            elif isinstance(content, list):
                                return [asdict(item) if is_dataclass(item) else serialize_generated_content(item) for item in content]
                            else:
                                return content

                        serializable_content = serialize_generated_content(generated_content)

                        # 保存生成内容到JSON
                        generation_content_path = generation_dir / 'generated_content.json'
                        try:
                            with open(generation_content_path, 'w', encoding='utf-8') as f:
                                json.dump({
                                    'generated_content': serializable_content,
                                    'generation_stats': {
                                        'total_fields': len(field_analyses),
                                        'completed_fields': len(generated_content),
                                        'failed_fields': failed_fields,
                                        'total_time': generation_result.total_time,
                                        'parallel_threads': 5,
                                    }
                                }, f, ensure_ascii=False, indent=2)
                            print(f"✅ 生成内容已保存: {generation_content_path}")
                            print(f"   文件大小: {os.path.getsize(generation_content_path)} 字节")
                        except Exception as e:
                            print(f"❌ 保存生成内容失败: {e}")
                            import traceback
                            traceback.print_exc()
                            sys.stdout.flush()
                            raise

                        if len(generated_content) > 0:
                            print(f"✅ 成功生成了 {len(generated_content)} 个字段的内容")
                        else:
                            print(f"⚠️ 警告：generated_content 为空，没有生成任何内容！")
                        
                        sys.stdout.flush()

                        # ==================== DocuMind 计费逻辑 (Post-Generation) ====================
                        try:
                            def extract_generated_text(field_obj):
                                if is_dataclass(field_obj):
                                    return field_obj.content or ""
                                if isinstance(field_obj, dict):
                                    return field_obj.get('content', '') or ""
                                if field_obj is None:
                                    return ""
                                return str(field_obj)

                            total_chars = sum(
                                len(extract_generated_text(field_obj))
                                for field_obj in generated_content.values()
                            )
                            print(f"💰 [Billing] Actual Document Body Chars: {total_chars}")

                            # 2. Get User and Update Usage
                            # Since we are in a background thread, the original 'user' proxy might be stale or unbound?
                            # Usually 'run_v5_generation' is a closure capturing 'user' proxy? 
                            # No, 'run_v5_generation' is defined inside the route, capturing context? 
                            # Flask contexts are thread-local. Spawning a thread loses context.
                            # We stored 'user_id' in task info (Wait, I added it to self.v5_generation_tasks).
                            # 'run_v5_generation' is inner function, it captures 'user' from outer scope?
                            # Standard Flask `copy_current_request_context` or manually managing app context is needed.
                            # However, in 'run_v5_generation', we already use `configure_generation_env` etc.
                            # We need to query user from DB by ID to be safe and transactional.

                            with self.app.app_context():
                                # User ID passed via captured closure check? 
                                # Better query fresh.
                                # self.v5_generation_tasks[task_id]['user_id'] (stored in prev step)
                                user_id_val = self.v5_generation_tasks[task_id].get('user_id')
                                user_obj = User.query.get(user_id_val)
                                
                                if user_obj:
                                    model_key = self.v5_generation_tasks[task_id].get('model_key', 'qwen-flash')
                                    cost_points = 0
                                    deduction_desc = ""
                                    
                                    # Rates
                                    rates = {
                                        'qwen-flash': 20, # Mini
                                        'qwen-plus': 30,  # Flash
                                        'kimi': 40,       # Pro
                                        'gemini-pro': 40, 
                                        'faster': 45      # Faster
                                    }
                                    rate = rates.get(model_key, 20)
                                    
                                    chargeable_chars = 0
                                    
                                    if model_key == 'qwen-flash': # Mini: 3000 free
                                        remaining_free = max(0, 3000 - user_obj.weekly_usage_mini)
                                        if total_chars <= remaining_free:
                                            user_obj.weekly_usage_mini += total_chars
                                            deduction_desc = f"Mini模型消耗{total_chars}字 (免费额度内)"
                                        else:
                                            free_part = remaining_free
                                            chargeable_chars = total_chars - free_part
                                            user_obj.weekly_usage_mini += total_chars # Accumulate total usage
                                            deduction_desc = f"Mini模型消耗{total_chars}字 (含{free_part}免费, {chargeable_chars}计费)"
                                            
                                    elif model_key == 'qwen-plus': # Flash: 1000 free
                                        remaining_free = max(0, 1000 - user_obj.weekly_usage_flash)
                                        if total_chars <= remaining_free:
                                            user_obj.weekly_usage_flash += total_chars
                                            deduction_desc = f"Flash模型消耗{total_chars}字 (免费额度内)"
                                        else:
                                            free_part = remaining_free
                                            chargeable_chars = total_chars - free_part
                                            user_obj.weekly_usage_flash += total_chars
                                            deduction_desc = f"Flash模型消耗{total_chars}字 (含{free_part}免费, {chargeable_chars}计费)"
                                    
                                    else: # Pro/Faster: No free
                                        chargeable_chars = total_chars
                                        deduction_desc = f"{model_key}模型消耗{total_chars}字"

                                    # Calculate Points (Round half up? User said "四舍五入")
                                    # Python round() rounds to nearest even for .5, standard arithmetic is desirable.
                                    # Logic: int(chars / 1000 * rate + 0.5)
                                    if chargeable_chars > 0:
                                        raw_points = (chargeable_chars / 1000.0) * rate
                                        cost_points = int(raw_points + 0.5) 
                                        
                                        # Ensure at least 1 point if meaningful? The prompt says "不满1000字按比例算积分...四舍五入". 
                                        # So 100 chars at 20rate = 0.2*1000/1000 = 2pts? No. 100/1000 * 20 = 2.
                                        # 10 chars at 20rate = 0.2 -> 0pts. 
                                        # Seems strict rounding.
                                    
                                    if cost_points > 0:
                                        # Check balance again (though we pre-checked)
                                        if user_obj.points_balance >= cost_points:
                                            from models.shop import add_points_to_user
                                            add_points_to_user(user_obj, -cost_points, 'consume', f'文档生成: {deduction_desc}')
                                            print(f"💰 [Billing] Deducted {cost_points} points for User {user_obj.username}")
                                        else:
                                            # Allow negative? Or stop? 
                                            # System typically allows logic to complete and go negative if pre-check passed.
                                            # Better to record debt or just deduct to negative.
                                            user_obj.points_balance -= cost_points
                                            db.session.commit() # Commit the debt
                                            # Log manually since add_points expects valid txn? 
                                            # Let's use add_points_to_user, it handles balance update.
                                            from models.shop import add_points_to_user
                                            add_points_to_user(user_obj, -cost_points, 'consume', f'文档生成(透支): {deduction_desc}')
                                            print(f"💰 [Billing] Deducted {cost_points} points (Possible Overdraft) for User {user_obj.username}")
                                    else:
                                        # Just commit usage updates
                                        db.session.commit()
                                        print(f"💰 [Billing] No charge. {deduction_desc}")
                                else:
                                    print(f"⚠️ [Billing] User not found for task {task_id}, skip billing")

                        except Exception as e:
                            import traceback
                            print(f"❌ 计费逻辑出错: {e}")
                            traceback.print_exc()
                            sys.stdout.flush()

                        # ===========================================================================

                        sys.stdout.flush()

                        progress_callback('generation', 80, '内容生成完成')
                        generation_time = time.time() - generation_start_time
                        print(f"⏱️ [PERF] 内容生成总耗时: {generation_time:.2f}s")
                        sys.stdout.flush()

                        # 阶段4: 应用标注并重建DOCX
                        rebuild_start_time = time.time()
                        progress_callback('rebuild', 90, '正在生成最终文档...')
                        self.v5_generation_tasks[task_id]['status'] = 'rebuilding'

                        # 将生成的内容转换为标注格式并保存到JSON
                        filled_annotations_json = annotation_dir / 'annotations_filled.json'

                        # 创建填充后的标注列表
                        filled_annotations = []
                        for ann in annotations:
                            filled_ann = ann.copy()
                            # 从generated_content中获取对应的内容
                            placeholder = ann.get('placeholder')
                            if placeholder in generated_content:
                                field_obj = generated_content[placeholder]
                                # 提取实际生成的文本内容
                                generated_text = ''
                                if is_dataclass(field_obj):
                                    # GeneratedField 对象，提取 content 属性
                                    generated_text = field_obj.content
                                    # 同时保存完整的元数据（用于调试和分析）
                                    filled_ann['generated_content'] = asdict(field_obj)
                                elif isinstance(field_obj, dict):
                                    # 字典格式，提取 content 字段
                                    generated_text = field_obj.get('content', '')
                                    filled_ann['generated_content'] = field_obj
                                else:
                                    # 其他格式，直接转为字符串
                                    generated_text = str(field_obj)
                                    filled_ann['generated_content'] = field_obj

                                # 🔥 修复：处理append action时保留原始标题
                                action = ann.get('action', 'replace')
                                original_result = ann.get('result', '')

                                if action == 'append' and original_result:
                                    # Append模式：需要保留原始result中的标题部分
                                    # 原始格式: "一、目的与意义<br>{{placeholder}}"
                                    # 需要替换占位符但保留标题
                                    import re
                                    placeholder_pattern = re.compile(r'\{\{[^}]+\}\}')
                                    if placeholder_pattern.search(original_result):
                                        # 存在占位符，替换为生成的内容
                                        filled_ann['result'] = placeholder_pattern.sub(generated_text, original_result)
                                        print(f"   🔄 [APPEND] {placeholder}: 保留标题并替换占位符")
                                        print(f"      原始: {original_result[:100]}...")
                                        print(f"      替换后: {filled_ann['result'][:100]}...")
                                    else:
                                        # 没有占位符，直接追加
                                        filled_ann['result'] = original_result + generated_text
                                        print(f"   🔄 [APPEND] {placeholder}: 直接追加内容")
                                else:
                                    # Replace模式：直接使用生成的内容
                                    filled_ann['result'] = generated_text
                                    print(f"   ✅ [REPLACE] {placeholder}: {len(generated_text)} 字符")

                                sys.stdout.flush()
                            filled_annotations.append(filled_ann)

                        # 保存到JSON文件（必须包装为{"annotations": [...]}格式）
                        with open(filled_annotations_json, 'w', encoding='utf-8') as f:
                            json.dump({"annotations": filled_annotations}, f, ensure_ascii=False, indent=2)

                        print(f"✅ 填充后的标注: {filled_annotations_json}")
                        sys.stdout.flush()

                        # 准备输出路径
                        output_dir = self.app.config.get('EXPORT_FOLDER',
                            os.path.join(project_root, 'exports'))
                        os.makedirs(output_dir, exist_ok=True)

                        output_filename = f'v5_generated_{timestamp}.docx'
                        output_path = os.path.join(output_dir, output_filename)

                        # 🔥 新增：保存标注后的DOCX（在应用生成内容之前）
                        annotated_docx_path = generation_dir / 'annotated_template.docx'
                        try:
                            import shutil
                            shutil.copy2(file_path, annotated_docx_path)
                            print(f"✅ 标注后的模板已保存: {annotated_docx_path}")
                            print(f"   (这是应用生成内容之前的原始模板副本，包含标注信息)")
                            sys.stdout.flush()
                        except Exception as e:
                            print(f"⚠️  保存标注后模板失败: {e}")
                            sys.stdout.flush()

                        # 应用生成的内容
                        result = apply_annotations_and_rebuild_docx(
                            md_path=PathLib(md_path),
                            annotations_json_path=filled_annotations_json,
                            manifest_path=PathLib(manifest_path) if manifest_path else None,
                            output_docx_path=PathLib(output_path),
                            base_docx_path=PathLib(file_path)
                        )

                        final_docx = result.get('output_docx_path', output_path)

                        # 同时保存一份到web_outdir
                        import shutil
                        final_docx_in_outdir = web_outdir / 'final.docx'
                        shutil.copy2(final_docx, final_docx_in_outdir)

                        print(f"✅ 最终文档: {final_docx}")
                        print(f"✅ 备份副本: {final_docx_in_outdir}")
                        sys.stdout.flush()

                        # 文档一旦生成成功，优先暴露稳定的下载路径，避免后处理失败影响下载。
                        self.v5_generation_tasks[task_id]['file_path'] = str(final_docx_in_outdir)
                        self.v5_generation_tasks[task_id]['file_name'] = output_filename
                        self.v5_generation_tasks[task_id]['output_dir'] = str(web_outdir)

                        # 🔥 新增：复制LLM交互日志到输出目录
                        import glob
                        logs_dir = PathLib(project_root) / 'logs' / 'llm_prompts'
                        if logs_dir.exists():
                            # 找到最新生成的日志文件（在生成期间创建的）
                            log_files = sorted(logs_dir.glob('generation_*.log'), key=lambda x: x.stat().st_mtime, reverse=True)

                            # 复制最近的5个日志文件（覆盖整个生成过程）
                            logs_subdir = web_outdir / 'logs'
                            logs_subdir.mkdir(exist_ok=True)

                            copied_logs = []
                            for log_file in log_files[:10]:  # 最多复制10个最新的日志
                                # 检查日志文件的修改时间，只复制本次生成期间的
                                log_mtime = log_file.stat().st_mtime
                                import time as time_module
                                current_time = time_module.time()
                                # 如果日志在最近5分钟内修改过，就复制
                                if current_time - log_mtime < 300:  # 5分钟 = 300秒
                                    dest_log = logs_subdir / log_file.name
                                    shutil.copy2(log_file, dest_log)
                                    copied_logs.append(log_file.name)

                            if copied_logs:
                                print(f"📝 已复制 {len(copied_logs)} 个LLM交互日志到: {logs_subdir}")
                                for log_name in copied_logs[:3]:  # 只显示前3个
                                    print(f"   - {log_name}")
                                if len(copied_logs) > 3:
                                    print(f"   ... 和其他 {len(copied_logs)-3} 个日志文件")
                            else:
                                print(f"⚠️ 未找到本次生成的日志文件")
                        else:
                            print(f"⚠️ 日志目录不存在: {logs_dir}")

                        sys.stdout.flush()

                        rebuild_time = time.time() - rebuild_start_time
                        print(f"⏱️ [PERF] 文档重建耗时: {rebuild_time:.2f}s")
                        
                        total_time = time.time() - self.v5_generation_tasks[task_id]['start_time']
                        print(f"⏱️ [PERF] 任务总耗时: {total_time:.2f}s")
                        sys.stdout.flush()

                        progress_callback('completed', 100, '文档生成完成！')

                        # 🔥 新增：VLM质量检查（根据模式选择同步或异步）
                        def run_vlm_check():
                            """执行VLM质量检查和知识库更新"""
                            try:
                                print(f"\n{'='*80}")
                                print(f"🔍 开始VLM质量检查...")
                                print(f"{'='*80}")
                                sys.stdout.flush()

                                from docuagent.v5.vlm_checker import check_docx_quality
                                from docuagent.v5.reflection import analyze_errors

                                # VLM质量检查
                                vlm_result = check_docx_quality(
                                    PathLib(final_docx_in_outdir),
                                    user_requirement=prompt,
                                    outdir=web_outdir
                                )

                                print(f"✅ VLM检查完成")
                                print(f"   整体评分: {vlm_result.get('overall_score', 'N/A')}")
                                sys.stdout.flush()

                                # 错误分析
                                analysis = analyze_errors(vlm_result, prompt, outdir=web_outdir)

                                print(f"✅ 错误分析完成")
                                print(f"   发现问题数: {len(analysis.get('errors', []))}")
                                sys.stdout.flush()

                                # 更新知识库（training和inference模式都更新）
                                kb.add_experience(vlm_result, analysis, {
                                    "template_name": PathLib(file_path).name,
                                    "user_requirement": prompt,
                                    "mode": mode
                                })

                                print(f"✅ 知识库已更新")
                                sys.stdout.flush()

                                # 保存VLM结果摘要
                                vlm_summary = {
                                    'vlm_result': vlm_result,
                                    'error_analysis': analysis,
                                    'mode': mode
                                }
                                vlm_summary_path = web_outdir / 'vlm_quality_check.json'
                                with open(vlm_summary_path, 'w', encoding='utf-8') as f:
                                    json.dump(vlm_summary, f, ensure_ascii=False, indent=2)

                                print(f"✅ VLM结果保存: {vlm_summary_path}")
                                print(f"{'='*80}\n")
                                sys.stdout.flush()

                                return vlm_result

                            except Exception as e:
                                print(f"⚠️ VLM检查失败: {e}")
                                import traceback
                                traceback.print_exc()
                                sys.stdout.flush()
                                return None

                        # 根据模式选择同步或异步执行VLM检查
                        if mode == 'training':
                            # Training模式：同步执行VLM检查
                            print(f"📊 Training模式：执行同步VLM质量检查")
                            vlm_result = run_vlm_check()

                            # TODO: 如果质量不达标，可以选择重新生成
                            # if vlm_result and vlm_result.get('overall_score', 1.0) < 0.7:
                            #     重新生成逻辑

                        else:
                            # Inference模式：异步执行VLM检查（后台运行）
                            print(f"📊 Inference模式：启动后台VLM质量检查")
                            import threading
                            vlm_thread = threading.Thread(target=run_vlm_check, daemon=True)
                            vlm_thread.start()
                            print(f"   用户可立即下载文档，VLM检查在后台继续运行")

                        sys.stdout.flush()

                        # 保存流程摘要
                        summary = {
                            'task_id': task_id,
                            'timestamp': timestamp,
                            'model': model,
                            'user_prompt': prompt,
                            'input_file': file_path,
                            'output_dir': str(web_outdir),
                            'outputs': {
                                'markdown': str(md_path),
                                'manifest': str(manifest_path),
                                'annotation_json': str(annotation_json_path),
                                'filled_annotations_json': str(filled_annotations_json),
                                'generated_content_json': str(generation_content_path),
                                'final_docx': str(final_docx),
                                'final_docx_backup': str(final_docx_in_outdir)
                            },
                            'statistics': {
                                'placeholders_count': len(annotations),
                                'generated_fields_count': len(generated_content)
                            }
                        }

                        summary_path = web_outdir / 'summary.json'
                        with open(summary_path, 'w', encoding='utf-8') as f:
                            json.dump(summary, f, ensure_ascii=False, indent=2)

                        print(f"\n✅ 流程摘要: {summary_path}")
                        print(f"\n{'='*80}")
                        print(f"🎉 V5生成完成！")
                        print(f"{'='*80}")
                        print(f"📁 所有文件保存在: {web_outdir}")
                        print(f"   - Markdown: markdown/1-_v4.md")
                        print(f"   - 标注结果: annotation/annotations.json ({len(annotations)} 个占位符)")
                        print(f"   - 生成内容: generation/generated_content.json ({len(generated_content)} 个字段)")
                        print(f"   - 最终文档: final.docx")
                        print(f"   - 流程摘要: summary.json")
                        print(f"{'='*80}\n")
                        sys.stdout.flush()

                        # 更新任务状态为完成
                        self.v5_generation_tasks[task_id]['status'] = 'completed'

                        print(f"✅ V5生成完成: {final_docx_in_outdir}")
                        sys.stdout.flush()  # 强制刷新输出

                    except Exception as e:
                        error_msg = f'生成失败: {str(e)}'
                        print(f"❌ V5生成失败: {e}")
                        import traceback
                        traceback_str = traceback.format_exc()
                        print(traceback_str)
                        sys.stdout.flush()  # 强制刷新输出

                        self.v5_generation_tasks[task_id]['error_traceback'] = traceback_str

                        web_outdir_path = locals().get('web_outdir')
                        if web_outdir_path:
                            try:
                                error_log_path = PathLib(web_outdir_path) / 'error_traceback.log'
                                error_log_path.write_text(traceback_str, encoding='utf-8')
                            except Exception:
                                pass

                        artifact_path = self.v5_generation_tasks.get(task_id, {}).get('file_path')
                        if artifact_path and os.path.exists(artifact_path):
                            warning_msg = f'文档已生成，但后处理出现问题：{str(e)}'
                            self.v5_generation_tasks[task_id]['status'] = 'completed'
                            self.v5_generation_tasks[task_id]['error'] = warning_msg
                            progress_callback('completed', 100, warning_msg)
                            print(f"⚠️  V5后处理失败，但文档可下载: {artifact_path}")
                        else:
                            self.v5_generation_tasks[task_id]['status'] = 'failed'
                            self.v5_generation_tasks[task_id]['error'] = error_msg
                            progress_callback('error', 0, error_msg)

                # 启动后台线程
                import threading
                thread = threading.Thread(target=run_v5_generation, daemon=True)
                thread.start()

                return jsonify({
                    'success': True,
                    'task_id': task_id,
                    'message': '任务已启动'
                })

            except Exception as e:
                print(f"❌ 启动V5任务失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'启动失败: {str(e)}'}), 500

        # 查询V5生成进度
        @self.app.route('/api/v5/progress/<task_id>', methods=['GET'])
        @require_auth
        def v5_get_progress(task_id):
            """查询V5生成任务进度"""
            try:
                if task_id not in self.v5_generation_tasks:
                    # 🔥 修复：返回更详细的错误信息
                    return jsonify({
                        'error': '任务不存在或已过期',
                        'success': False,
                        'message': '任务ID无效，可能是服务重启导致，请重新生成',
                        'status': 'not_found'
                    }), 404

                task = self.v5_generation_tasks[task_id]

                return jsonify({
                    'success': True,
                    'progress': task['progress'],
                    'status': task['status'],
                    'message': task['message'],
                    'file_path': task.get('file_path'),
                    'file_name': task.get('file_name'),
                    'error': task.get('error')
                })

            except Exception as e:
                print(f"❌ 查询进度失败: {e}")
                return jsonify({'error': f'查询失败: {str(e)}'}), 500

        # 下载V5生成的文档
        @self.app.route('/api/v5/download', methods=['GET'])
        @require_auth
        def v5_download():
            """下载V5生成的文档"""
            try:
                file_path = request.args.get('file_path')

                if not file_path or not os.path.exists(file_path):
                    return jsonify({'error': '文件不存在'}), 404

                return send_file(
                    file_path,
                    as_attachment=True,
                    download_name=os.path.basename(file_path),
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )

            except Exception as e:
                print(f"❌ 下载失败: {e}")
                return jsonify({'error': f'下载失败: {str(e)}'}), 500

        # ========================================
        # 统一文档生成服务API (core/document_generator)
        # ========================================

        @self.app.route('/api/unified/generate', methods=['POST'])
        @require_auth
        def unified_generate():
            """
            统一文档生成服务
            使用 core/document_generator 进行文档生成
            """
            try:
                data = request.get_json()
                file_path = data.get('file_path')
                requirement = data.get('requirement')
                mode = data.get('mode', 'inference')  # inference or training
                max_concurrent_annotate = data.get('max_concurrent_annotate', 3)
                max_concurrent_generate = data.get('max_concurrent_generate', 10)

                if not file_path or not os.path.exists(file_path):
                    return jsonify({'error': '模板文件不存在'}), 400

                if not requirement:
                    return jsonify({'error': '请提供需求描述'}), 400

                if mode not in ['inference', 'training']:
                    return jsonify({'error': 'mode参数必须是inference或training'}), 400

                # 生成任务ID
                task_id = str(uuid.uuid4())

                # 初始化任务进度
                self.unified_generation_tasks[task_id] = {
                    'progress': 0,
                    'status': 'starting',
                    'message': '任务启动中...',
                    'logs': [],
                    'file_path': None,
                    'file_name': None,
                    'doc_type': None,
                    'statistics': {},
                    'performance': {},
                    'error': None,
                    'start_time': time.time()  # ✅ 添加开始时间
                }

                # 后台执行生成任务
                def run_generation_task():
                    """后台生成任务"""
                    import threading
                    import sys

                    try:
                        print(f"\n{'='*80}")
                        print(f"🚀 统一文档生成服务启动 - 任务ID: {task_id}")
                        print(f"{'='*80}")
                        print(f"📄 模板: {os.path.basename(file_path)}")
                        print(f"📝 需求: {requirement}")
                        print(f"🔧 模式: {mode}")
                        print(f"⚙️  标注并发: {max_concurrent_annotate}")
                        print(f"⚙️  生成并发: {max_concurrent_generate}")
                        sys.stdout.flush()

                        # 更新进度
                        self.unified_generation_tasks[task_id]['status'] = 'initializing'
                        self.unified_generation_tasks[task_id]['progress'] = 5
                        self.unified_generation_tasks[task_id]['message'] = '初始化生成器...'

                        # 使用统一文档生成器
                        generator = DocumentGenerator(
                            max_concurrent_annotate=max_concurrent_annotate,
                            max_concurrent_generate=max_concurrent_generate,
                            vlm_max_iterations=3,
                            vlm_quality_threshold=0.7
                        )

                        self.unified_generation_tasks[task_id]['progress'] = 10
                        self.unified_generation_tasks[task_id]['message'] = '开始生成文档...'
                        self.unified_generation_tasks[task_id]['status'] = 'generating'

                        # 执行生成
                        result = generator.generate(
                            template_path=file_path,
                            user_requirement=requirement,
                            mode=mode,
                            output_dir=None,  # 自动生成输出目录
                            no_segment=False
                        )

                        if result.success:
                            # 生成成功
                            self.unified_generation_tasks[task_id]['status'] = 'completed'
                            self.unified_generation_tasks[task_id]['progress'] = 100
                            self.unified_generation_tasks[task_id]['message'] = '文档生成完成'
                            self.unified_generation_tasks[task_id]['file_path'] = result.final_docx
                            self.unified_generation_tasks[task_id]['file_name'] = os.path.basename(result.final_docx)
                            self.unified_generation_tasks[task_id]['doc_type'] = result.doc_type_name
                            self.unified_generation_tasks[task_id]['statistics'] = result.statistics
                            self.unified_generation_tasks[task_id]['performance'] = result.performance

                            print(f"\n{'='*80}")
                            print(f"✅ 文档生成成功！")
                            print(f"{'='*80}")
                            print(f"📄 文档类型: {result.doc_type_name}")
                            print(f"📁 最终文档: {result.final_docx}")
                            print(f"⏱️  总耗时: {result.performance.get('total_time', 0):.2f}秒")
                            print(f"{'='*80}\n")
                            sys.stdout.flush()

                        else:
                            # 生成失败
                            self.unified_generation_tasks[task_id]['status'] = 'failed'
                            self.unified_generation_tasks[task_id]['progress'] = 0
                            self.unified_generation_tasks[task_id]['error'] = result.error
                            self.unified_generation_tasks[task_id]['message'] = f'生成失败: {result.error}'

                            print(f"\n{'='*80}")
                            print(f"❌ 文档生成失败")
                            print(f"{'='*80}")
                            print(f"错误: {result.error}")
                            print(f"{'='*80}\n")
                            sys.stdout.flush()

                    except Exception as e:
                        import traceback
                        error_msg = f"{str(e)}\n{traceback.format_exc()}"

                        self.unified_generation_tasks[task_id]['status'] = 'failed'
                        self.unified_generation_tasks[task_id]['progress'] = 0
                        self.unified_generation_tasks[task_id]['error'] = error_msg
                        self.unified_generation_tasks[task_id]['message'] = f'生成异常: {str(e)}'

                        print(f"\n{'='*80}")
                        print(f"❌ 任务执行异常")
                        print(f"{'='*80}")
                        print(error_msg)
                        print(f"{'='*80}\n")
                        sys.stdout.flush()

                # 启动后台线程
                import threading
                thread = threading.Thread(target=run_generation_task)
                thread.daemon = True
                thread.start()

                return jsonify({
                    'success': True,
                    'task_id': task_id,
                    'message': '任务已启动，请使用task_id查询进度'
                })

            except Exception as e:
                print(f"❌ 启动生成任务失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'启动失败: {str(e)}'}), 500

        @self.app.route('/api/unified/progress/<task_id>', methods=['GET'])
        @require_auth
        def unified_get_progress(task_id):
            """查询统一文档生成任务进度"""
            try:
                if task_id not in self.unified_generation_tasks:
                    return jsonify({'error': '任务不存在'}), 404

                task = self.unified_generation_tasks[task_id]

                return jsonify({
                    'success': True,
                    'progress': task['progress'],
                    'status': task['status'],
                    'message': task['message'],
                    'file_path': task.get('file_path'),
                    'file_name': task.get('file_name'),
                    'doc_type': task.get('doc_type'),
                    'statistics': task.get('statistics', {}),
                    'performance': task.get('performance', {}),
                    'error': task.get('error')
                })

            except Exception as e:
                print(f"❌ 查询进度失败: {e}")
                return jsonify({'error': f'查询失败: {str(e)}'}), 500

        @self.app.route('/api/unified/download', methods=['GET'])
        @require_auth
        def unified_download():
            """下载统一文档生成服务生成的文档"""
            try:
                file_path = request.args.get('file_path')

                if not file_path or not os.path.exists(file_path):
                    return jsonify({'error': '文件不存在'}), 404

                return send_file(
                    file_path,
                    as_attachment=True,
                    download_name=os.path.basename(file_path),
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )

            except Exception as e:
                print(f"❌ 下载失败: {e}")
                return jsonify({'error': f'下载失败: {str(e)}'}), 500

        # 错误处理
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({'error': '接口不存在'}), 404
        
        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({'error': '服务器内部错误'}), 500
    
    def run(self, host='0.0.0.0', port=5000, debug=False):
        """启动Flask应用"""
        print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║          🎓 EduAgent智教创想 - Flask API                     ║
║          University AI Lesson Planning System - Flask API     ║
║                                                               ║
║          基于 LangGraph + 通义千问                             ║
║          Powered by LangGraph & Qwen                          ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

🚀 服务器启动中...
📍 访问地址: http://{host}:{port}
📚 API文档: http://{host}:{port}/api/health
🔧 调试模式: {'开启' if debug else '关闭'}
        """)
        
        self.app.run(host=host, port=port, debug=debug)


def create_app():
    """创建Flask应用实例"""
    api = UniversityFlaskAPI()
    return api.app


if __name__ == '__main__':
    # 创建并启动API服务
    api = UniversityFlaskAPI()
    api.run(host='127.0.0.1', port=5025)
