"""
AI文档编辑器 - 独立Flask应用
可直接集成到其他项目中使用

使用方法:
    1. 直接运行: python app.py
    2. 集成到其他Flask应用:
        from ai_editor_standalone import create_app, editor_bp, ai_api_bp
        app.register_blueprint(editor_bp)
        app.register_blueprint(ai_api_bp)
"""

import secrets
import os
import re
from pathlib import Path
from flask import Flask, render_template, request, jsonify

# 使用相对导入，不修改sys.path以避免影响主项目
from .editor.api import editor_bp
from .utils.llm_call import call_llm


def clean_ai_response(content):
    """清理AI生成的内容"""
    if not content:
        return content
    # 移除星号（Markdown加粗标记）
    content = content.replace('*', '')
    # 移除空白行（将连续的换行符替换为单个换行符）
    content = re.sub(r'\n\s*\n', '\n', content)
    return content.strip()


def create_app(config=None):
    """创建Flask应用实例"""
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static'
    )

    # 默认配置
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

    # 应用自定义配置
    if config:
        app.config.update(config)

    # 注册编辑器API蓝图
    app.register_blueprint(editor_bp)

    # 注册路由
    register_routes(app)

    return app


def register_routes(app):
    """注册所有路由"""

    @app.route('/')
    @app.route('/ai-editor')
    def ai_editor_page():
        """AI编辑器主页面"""
        return render_template('ai_editor.html')

    # ===== AI 功能 API =====

    @app.route('/api/ai/chat', methods=['POST'])
    def ai_editor_chat():
        """AI编辑器聊天接口 - 支持内容生成"""
        try:
            data = request.get_json()
            message = data.get('message', '')
            context = data.get('context', {})

            if not message:
                return jsonify({'success': False, 'error': '消息不能为空'}), 400

            selected_text = context.get('selected_text', '')
            doc_content = context.get('document_content', '')

            # 检测用户意图：是否需要生成内容
            generate_keywords = ['写', '生成', '帮我写', '创建', '添加', '补充', '扩展', '续写', '草拟', '起草']
            is_generate_request = any(kw in message for kw in generate_keywords)

            if is_generate_request:
                # 内容生成模式
                system_prompt = """你是一个专业的文档写作助手。用户需要你帮忙生成文档内容。

请根据用户的要求生成专业、规范的内容。

重要规则：
1. 直接生成用户需要的内容，不要有任何解释性文字
2. 内容要专业、正式、符合文档规范
3. 适当分段，结构清晰
4. 如果是续写，要与上下文风格保持一致"""

                user_prompt = f"用户请求：{message}"
                if doc_content:
                    user_prompt = f"当前文档内容：\n{doc_content[:800]}\n\n{user_prompt}"
                if selected_text:
                    user_prompt = f"用户选中的文本（可能需要基于此扩展）：\n{selected_text}\n\n{user_prompt}"

                generated = call_llm(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.7
                )

                return jsonify({
                    'success': True,
                    'response': '已为您生成以下内容，点击"插入到文档"可添加到文档中：',
                    'generated_content': clean_ai_response(generated)
                })
            else:
                # 普通对话模式
                system_prompt = """你是一个专业的文档编辑助手。用户正在编辑一个Word文档，你需要帮助他们：
1. 回答关于文档内容的问题
2. 提供写作建议
3. 帮助改进文档质量

请用简洁专业的中文回答。如果用户的问题涉及生成具体内容，你可以提示他们使用"帮我写..."这样的指令。"""

                user_prompt = message
                if selected_text:
                    user_prompt = f"用户选中的文本：\n{selected_text}\n\n用户问题：{message}"
                if doc_content:
                    user_prompt = f"文档内容摘要：\n{doc_content[:500]}...\n\n{user_prompt}"

                response = call_llm(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.7
                )

                return jsonify({
                    'success': True,
                    'response': response
                })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/ai/complete', methods=['POST'])
    def ai_editor_complete():
        """AI编辑器自动补全接口 - Tab键触发"""
        try:
            data = request.get_json()
            text_before = data.get('text_before', '')
            full_context = data.get('full_context', '')

            if not text_before.strip():
                return jsonify({'success': False, 'error': '没有可补全的内容'}), 400

            system_prompt = """你是一个文档续写助手。用户在编辑文档时按下Tab键，你需要智能续写接下来的内容。

规则：
1. 只输出续写的内容，不要有任何解释
2. 续写长度适中（1-3句话），不要太长
3. 保持与前文风格一致
4. 内容要自然流畅，像是原作者写的
5. 如果前文是列表项，可以续写下一项
6. 如果是句子中间，补全当前句子"""

            user_prompt = f"前文内容：\n{text_before[-500:]}\n\n请续写："

            if full_context and full_context != text_before:
                user_prompt = f"文档整体上下文：\n{full_context[:500]}...\n\n{user_prompt}"

            completion = call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=150
            )

            return jsonify({
                'success': True,
                'completion': clean_ai_response(completion)
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/ai/generate-placeholder', methods=['POST'])
    def ai_editor_generate_placeholder():
        """AI编辑器@@@占位符生成接口 - 根据指令和上下文生成内容"""
        try:
            data = request.get_json()
            instruction = data.get('instruction', '')
            context_before = data.get('context_before', '')
            document_context = data.get('document_context', '')

            if not instruction:
                return jsonify({'success': False, 'error': '缺少生成指令'}), 400

            system_prompt = """你是一个专业的文档内容生成助手。用户在文档中使用@@@标记需要你生成的内容。

你需要根据：
1. 用户的指令（如"教学目标"、"课程简介"、"实验步骤"等）
2. 文档的上下文（前面的内容）
3. 整个文档的主题和风格

生成符合要求的专业内容。

重要规则：
1. 直接输出生成的内容，不要有任何解释或前缀
2. 内容要专业、规范，符合文档整体风格
3. 根据上下文推断具体主题（如前文提到"卷积神经网络"，则生成相关内容）
4. 长度适中，通常2-5句话，除非指令明确要求更长"""

            user_prompt = f"生成指令：{instruction}\n\n"

            if context_before.strip():
                user_prompt += f"当前段落前文：\n{context_before[-300:]}\n\n"

            if document_context.strip():
                user_prompt += f"文档整体内容：\n{document_context[:800]}\n\n"

            user_prompt += f'请生成"{instruction}"的内容：'

            content = call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7
            )

            return jsonify({
                'success': True,
                'content': clean_ai_response(content)
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/ai/rewrite', methods=['POST'])
    def ai_editor_rewrite():
        """AI编辑器重写接口"""
        try:
            data = request.get_json()
            selected_text = data.get('selected_text', '')
            instruction = data.get('instruction', '')

            if not selected_text:
                return jsonify({'success': False, 'error': '请选择要重写的文本'}), 400
            if not instruction:
                return jsonify({'success': False, 'error': '请输入重写指令'}), 400

            system_prompt = """你是一个专业的文档改写助手。用户会给你一段文本和改写要求，你需要按照要求重写这段文本。

规则：
1. 只输出重写后的文本，不要有任何解释
2. 保持原文的核心含义
3. 按用户要求调整风格、长度、专业度等"""

            user_prompt = f"""原文：
{selected_text}

改写要求：{instruction}

请直接输出改写后的文本："""

            rewritten = call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7
            )

            return jsonify({
                'success': True,
                'rewritten': clean_ai_response(rewritten)
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500

    # 错误处理
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': '接口不存在'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': '服务器内部错误'}), 500


# 创建应用实例
app = create_app()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5030))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'

    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║          🧠 AI文档编辑器 - 独立版                              ║
║          AI Document Editor - Standalone                       ║
║                                                               ║
║          访问地址: http://localhost:{port}                      ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """)

    app.run(host=os.getenv('HOST', '127.0.0.1'), port=port, debug=debug)
