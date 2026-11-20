"""
编辑器API Blueprint (简化版)
Editor API Blueprint (Standalone Version)

注意：此版本移除了DOCX转换功能依赖，仅保留基础编辑功能。
如需完整DOCX转换功能，请安装 python-docx 并添加转换模块。
"""

import os
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename
from functools import wraps

from .session import SessionManager

editor_bp = Blueprint('editor', __name__, url_prefix='/api/editor')

UPLOAD_DIR = Path(__file__).parent.parent / 'uploads' / 'editor_temp'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {'.docx', '.doc'}


def require_auth(f):
    """认证装饰器 - 可根据需要实现认证逻辑"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # 暂时跳过验证，可在此添加认证逻辑
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    """检查文件扩展名"""
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


@editor_bp.route('/new', methods=['POST'])
@require_auth
def create_new_document():
    """创建新的空白文档"""
    try:
        data = request.get_json() or {}
        filename = data.get('filename', '未命名文档.docx')

        session = SessionManager.create_empty_session(filename)

        return jsonify({
            'success': True,
            'session_id': session.session_id,
            'document': session.to_dict()
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@editor_bp.route('/upload', methods=['POST'])
@require_auth
def upload_document():
    """
    上传DOCX文档并创建编辑会话

    注意：简化版暂不支持DOCX解析，仅保存文件。
    如需完整DOCX转换功能，请添加 docuagent.v4 模块依赖。
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有上传文件'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'success': False, 'error': '文件名为空'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': '只支持.docx格式文件'}), 400

    try:
        filename = secure_filename(file.filename)
        if not filename.endswith('.docx'):
            filename = filename.rsplit('.', 1)[0] + '.docx'

        temp_path = UPLOAD_DIR / filename
        file.save(str(temp_path))

        # 尝试使用完整版转换器
        try:
            session = SessionManager.create_session(str(temp_path), filename)
        except ImportError:
            # 如果没有docuagent模块，创建简化会话
            session = SessionManager.create_session_simple(str(temp_path), filename)

        if temp_path.exists():
            temp_path.unlink()

        return jsonify({
            'success': True,
            'session_id': session.session_id,
            'document': session.to_dict()
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@editor_bp.route('/document/<session_id>', methods=['GET'])
@require_auth
def get_document(session_id):
    """获取文档内容"""
    session = SessionManager.get_session(session_id)

    if not session:
        return jsonify({'success': False, 'error': '会话不存在'}), 404

    return jsonify({
        'success': True,
        'document': session.to_dict()
    })


@editor_bp.route('/document/<session_id>', methods=['PUT'])
@require_auth
def update_document(session_id):
    """保存文档变更"""
    session = SessionManager.get_session(session_id)

    if not session:
        return jsonify({'success': False, 'error': '会话不存在'}), 404

    data = request.get_json()
    changes = data.get('changes', [])

    # 允许空的changes列表，因为可能只是触发保存当前状态
    if not changes:
        return jsonify({
            'success': True,
            'saved_at': session.updated_at,
            'message': '无变更内容'
        })

    try:
        for change in changes:
            block_id = change.get('block_id')
            content = change.get('content')
            row = change.get('row')
            col = change.get('col')
            font_meta = change.get('font')
            indent = change.get('indent')

            if block_id and content is not None:
                SessionManager.update_block(
                    session_id, block_id, content, row, col, font_meta, indent
                )

        return jsonify({
            'success': True,
            'saved_at': session.updated_at
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@editor_bp.route('/export/<session_id>', methods=['POST'])
@require_auth
def export_document(session_id):
    """
    导出为DOCX文档

    注意：简化版需要添加 docuagent.v4 模块才能完整导出。
    """
    session = SessionManager.get_session(session_id)

    if not session:
        return jsonify({'success': False, 'error': '会话不存在'}), 404

    try:
        export_filename = f'edited_{session.filename}'
        export_path = Path(session.working_dir) / export_filename

        # 尝试使用完整版导出
        try:
            from docuagent.v4.markdown_to_docx import rebuild_docx_from_markdown
            rebuild_docx_from_markdown(
                markdown_path=session.markdown_path,
                manifest_path=session.manifest_path,
                output_docx_path=str(export_path),
                base_docx_path=session.original_docx_path
            )
        except ImportError:
            # 简化版：直接复制原始文件或创建简单文本
            if session.original_docx_path and os.path.exists(session.original_docx_path):
                import shutil
                shutil.copy2(session.original_docx_path, str(export_path))
            else:
                # 创建简单的文本文件
                text_export = export_path.with_suffix('.txt')
                with open(text_export, 'w', encoding='utf-8') as f:
                    for block in session.blocks:
                        if block.block_type == 'paragraph':
                            f.write(str(block.content) + '\n\n')
                export_path = text_export
                export_filename = text_export.name

        if export_path.exists():
            return jsonify({
                'success': True,
                'download_url': f'/api/editor/download/{session_id}/{export_filename}',
                'filename': export_filename
            })
        else:
            return jsonify({'success': False, 'error': '导出失败'}), 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@editor_bp.route('/download/<session_id>/<filename>', methods=['GET'])
@require_auth
def download_document(session_id, filename):
    """下载导出的文档"""
    session = SessionManager.get_session(session_id)

    if not session:
        return jsonify({'success': False, 'error': '会话不存在'}), 404

    file_path = Path(session.working_dir) / filename

    if not file_path.exists():
        return jsonify({'success': False, 'error': '文件不存在'}), 404

    # 根据文件类型设置MIME类型
    if filename.endswith('.docx'):
        mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    else:
        mimetype = 'text/plain'

    return send_file(
        str(file_path),
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype
    )


@editor_bp.route('/preview/<session_id>', methods=['GET'])
@require_auth
def get_preview(session_id):
    """获取原始DOCX文件用于预览"""
    session = SessionManager.get_session(session_id)

    if not session:
        return jsonify({'success': False, 'error': '会话不存在'}), 404

    if not session.original_docx_path or not os.path.exists(session.original_docx_path):
        return jsonify({'success': False, 'error': '原始文件不存在'}), 404

    return send_file(
        session.original_docx_path,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
