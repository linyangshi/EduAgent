"""
编辑器会话管理 (简化版)
Editor Session Management (Standalone Version)

此版本支持两种模式：
1. 完整模式：使用 docuagent.v4 进行DOCX转换
2. 简化模式：仅支持文本编辑，不依赖外部模块
"""

import os
import json
import uuid
import shutil
from pathlib import Path
from typing import Dict, Optional, Any, List
from datetime import datetime
from dataclasses import dataclass, field, asdict


@dataclass
class EditorBlock:
    """编辑器块数据结构"""
    block_id: str
    block_type: str
    content: Any
    is_editable: bool = True
    has_drawing: bool = False
    style: Optional[Dict] = None
    font: Optional[Dict] = None
    indent: bool = False

    def to_dict(self):
        return asdict(self)


@dataclass
class EditorSession:
    """编辑器会话"""
    session_id: str
    filename: str
    original_docx_path: str
    markdown_path: str
    manifest_path: str
    features_path: str
    working_dir: str
    created_at: str
    updated_at: str
    blocks: List[EditorBlock] = field(default_factory=list)

    def to_dict(self):
        return {
            'session_id': self.session_id,
            'filename': self.filename,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'blocks': [b.to_dict() for b in self.blocks],
            'stats': {
                'total_blocks': len(self.blocks),
                'total_paragraphs': sum(1 for b in self.blocks if b.block_type == 'paragraph'),
                'total_tables': sum(1 for b in self.blocks if b.block_type == 'table'),
            }
        }


class SessionManager:
    """会话管理器"""

    SESSIONS_DIR = Path(__file__).parent.parent / 'editor_sessions'
    _sessions: Dict[str, EditorSession] = {}

    @classmethod
    def create_session(cls, docx_path: str, filename: str) -> EditorSession:
        """
        创建新的编辑会话 (完整模式)

        需要 docuagent.v4 模块支持DOCX转换
        """
        # 尝试导入docuagent模块
        try:
            from docuagent.v4.docx_markdown_converter import DocxMarkdownExporter
        except ImportError:
            # 如果没有docuagent模块，使用简化模式
            return cls.create_session_simple(docx_path, filename)

        session_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 创建工作目录
        working_dir = cls.SESSIONS_DIR / f'{session_id}_{timestamp}'
        working_dir.mkdir(parents=True, exist_ok=True)

        # 复制原始文档
        original_path = working_dir / filename
        shutil.copy2(docx_path, original_path)

        # 使用V4转换器
        exporter = DocxMarkdownExporter(str(original_path))
        md_path_raw, manifest_path_raw = exporter.export(str(working_dir))

        # 确保是字符串
        md_path = str(md_path_raw)
        manifest_path = str(manifest_path_raw)
        features_path = md_path.replace('_v4.md', '_v4_features.md')

        now = datetime.now().isoformat()
        session = EditorSession(
            session_id=session_id,
            filename=filename,
            original_docx_path=str(original_path),
            markdown_path=md_path,
            manifest_path=manifest_path,
            features_path=features_path if os.path.exists(features_path) else '',
            working_dir=str(working_dir),
            created_at=now,
            updated_at=now,
            blocks=[]
        )

        # 解析Markdown为编辑器块
        session.blocks = cls._parse_to_blocks(md_path, manifest_path)

        # 缓存会话
        cls._sessions[session_id] = session
        cls._save_session_meta(session)

        return session

    @classmethod
    def create_session_simple(cls, docx_path: str, filename: str) -> EditorSession:
        """
        创建简化会话 (不依赖docuagent)

        仅保存文件，不解析DOCX内容
        """
        session_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 创建工作目录
        working_dir = cls.SESSIONS_DIR / f'{session_id}_{timestamp}'
        working_dir.mkdir(parents=True, exist_ok=True)

        # 复制原始文档
        original_path = working_dir / filename
        shutil.copy2(docx_path, original_path)

        # 创建空的markdown和manifest文件
        base_name = filename.replace('.docx', '')
        md_path = str(working_dir / f'{base_name}_v4.md')
        manifest_path = str(working_dir / f'{base_name}_v4_manifest.json')

        # 初始化空的markdown
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('')

        # 初始化空的manifest
        empty_manifest = {
            'source_file': filename,
            'block_sequence': [],
            'paragraphs': [],
            'tables': []
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(empty_manifest, f, ensure_ascii=False, indent=2)

        now = datetime.now().isoformat()
        session = EditorSession(
            session_id=session_id,
            filename=filename,
            original_docx_path=str(original_path),
            markdown_path=md_path,
            manifest_path=manifest_path,
            features_path='',
            working_dir=str(working_dir),
            created_at=now,
            updated_at=now,
            blocks=[
                EditorBlock(
                    block_id='simple-block-1',
                    block_type='paragraph',
                    content='[DOCX文件已上传，简化模式下无法解析内容。请使用完整版以获得DOCX解析功能。]',
                    is_editable=True
                )
            ]
        )

        # 缓存会话
        cls._sessions[session_id] = session
        cls._save_session_meta(session)

        return session

    @classmethod
    def create_empty_session(cls, filename: str = '未命名文档.docx') -> EditorSession:
        """创建空白文档会话"""
        session_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 创建工作目录
        working_dir = cls.SESSIONS_DIR / f'{session_id}_{timestamp}'
        working_dir.mkdir(parents=True, exist_ok=True)

        # 创建空的markdown和manifest文件
        base_name = filename.replace('.docx', '')
        md_path = str(working_dir / f'{base_name}_v4.md')
        manifest_path = str(working_dir / f'{base_name}_v4_manifest.json')

        # 初始化空的markdown
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('')

        # 初始化空的manifest
        empty_manifest = {
            'source_file': filename,
            'block_sequence': [],
            'paragraphs': [],
            'tables': []
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(empty_manifest, f, ensure_ascii=False, indent=2)

        now = datetime.now().isoformat()
        session = EditorSession(
            session_id=session_id,
            filename=filename,
            original_docx_path='',  # 新建文档没有原始文件
            markdown_path=md_path,
            manifest_path=manifest_path,
            features_path='',
            working_dir=str(working_dir),
            created_at=now,
            updated_at=now,
            blocks=[]
        )

        # 缓存会话
        cls._sessions[session_id] = session
        cls._save_session_meta(session)

        return session

    @classmethod
    def get_session(cls, session_id: str) -> Optional[EditorSession]:
        """获取会话"""
        if session_id in cls._sessions:
            return cls._sessions[session_id]
        return cls._load_session(session_id)

    @classmethod
    def update_block(cls, session_id: str, block_id: str, content: Any,
                     row: int = None, col: int = None, font: Optional[Dict] = None,
                     indent: Optional[bool] = None) -> bool:
        """更新块内容"""
        session = cls.get_session(session_id)
        if not session:
            return False

        for block in session.blocks:
            if block.block_id == block_id:
                if block.block_type == 'paragraph':
                    block.content = content
                    if font:
                        block.font = font
                    if indent is not None:
                        block.indent = indent
                elif block.block_type == 'table' and row is not None and col is not None:
                    if 'cells' in block.content:
                        for cell_row in block.content['cells']:
                            for cell in cell_row:
                                if cell['row'] == row and cell['col'] == col:
                                    cell['content'] = content
                                    if font:
                                        cell['font'] = font
                                    break
                break

        session.updated_at = datetime.now().isoformat()
        cls._sync_to_markdown(session)
        return True

    @classmethod
    def _parse_to_blocks(cls, md_path: str, manifest_path: str) -> List[EditorBlock]:
        """解析Markdown和Manifest为编辑器块"""
        blocks = []

        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        # 解析markdown文件获取编辑后的内容
        md_content = cls._parse_markdown_content(md_path)

        block_sequence = manifest.get('block_sequence', [])
        paragraphs = {p['block_id']: p for p in manifest.get('paragraphs', [])}
        tables = {t['block_id']: t for t in manifest.get('tables', [])}

        for block_info in block_sequence:
            block_type = block_info['type']
            block_id = block_info['block_id']

            if block_type == 'paragraph':
                para = paragraphs.get(block_id, {})
                has_drawing = para.get('drawing_count', 0) > 0

                # 优先使用markdown中的内容
                content = md_content.get('paragraphs', {}).get(block_id)
                if content is None:
                    content = para.get('text', '')

                block = EditorBlock(
                    block_id=block_id,
                    block_type='paragraph',
                    content=content,
                    is_editable=not has_drawing,
                    has_drawing=has_drawing,
                    style={'name': para.get('style', 'Normal')},
                    font=para.get('font', {}),
                    indent=para.get('indent', False)
                )
                blocks.append(block)

            elif block_type == 'table':
                table = tables.get(block_id, {})
                cells_data = []

                table_updates = md_content.get('tables', {}).get(block_id, {})
                table_rows = table.get('rows', [])

                for row_idx, row_data in enumerate(table_rows):
                    row_cells = []
                    for cell in row_data:
                        marker = cell.get('marker', '')
                        if marker and marker in table_updates:
                            content = table_updates[marker]
                        else:
                            content = cell.get('text', '').replace('<br>', '\n')

                        row_cells.append({
                            'cell_id': marker,
                            'row': row_idx,
                            'col': cell.get('grid_col_index', 0),
                            'content': content,
                            'col_span': cell.get('col_span', 1),
                            'v_merge': cell.get('vmerge'),
                            'is_editable': True,
                            'font': cell.get('font', {})
                        })
                    cells_data.append(row_cells)

                block = EditorBlock(
                    block_id=block_id,
                    block_type='table',
                    content={
                        'rows': len(table_rows),
                        'cols': table.get('max_columns', 0),
                        'cells': cells_data
                    },
                    is_editable=True
                )
                blocks.append(block)

        return blocks

    @classmethod
    def _parse_markdown_content(cls, md_path: str) -> Dict[str, Dict]:
        """解析Markdown文件，提取段落和表格的内容"""
        import re

        BLOCK_PATTERN = re.compile(r'\[\[DOCX-BLOCK\s+([^\]]+)\]\]')
        CELL_PATTERN = re.compile(r'\[\[DOCX-CELL\s+([^\]]+)\]\]')

        with open(md_path, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()

        idx = 0
        paragraph_updates = {}
        table_updates = {}

        while idx < len(lines):
            line = lines[idx]
            block_match = BLOCK_PATTERN.match(line.strip())
            if not block_match:
                idx += 1
                continue

            attrs = cls._parse_block_attrs(block_match.group(1))
            block_type = attrs.get('type')
            block_id = attrs.get('id')
            idx += 1

            if block_type == 'paragraph':
                content_lines = []
                while idx < len(lines):
                    peek = lines[idx]
                    if BLOCK_PATTERN.match(peek.strip()):
                        break
                    if peek.strip() == '' and (idx + 1 < len(lines) and BLOCK_PATTERN.match(lines[idx + 1].strip())):
                        idx += 1
                        break
                    content_lines.append(peek)
                    idx += 1
                paragraph_updates[block_id] = '\n'.join(content_lines).strip()

            elif block_type == 'table':
                while idx < len(lines) and lines[idx].strip() == '':
                    idx += 1

                cell_map = {}
                while idx < len(lines):
                    table_line = lines[idx].strip()
                    if not table_line.startswith('|'):
                        break
                    parts = [part.strip() for part in table_line.split('|')[1:-1]]
                    for part in parts:
                        cell_match = CELL_PATTERN.match(part)
                        if not cell_match:
                            continue
                        marker = cell_match.group(0)
                        text_content = part[cell_match.end():].strip()
                        text_content = text_content.replace('<br>', '\n')
                        cell_map[marker] = text_content
                    idx += 1
                table_updates[block_id] = cell_map

        return {'paragraphs': paragraph_updates, 'tables': table_updates}

    @staticmethod
    def _parse_block_attrs(attr_string: str) -> Dict[str, str]:
        """解析块属性字符串"""
        import shlex
        result = {}
        try:
            for token in shlex.split(attr_string):
                if '=' not in token:
                    continue
                key, value = token.split('=', 1)
                result[key] = value
        except ValueError:
            pass
        return result

    @classmethod
    def _sync_to_markdown(cls, session: EditorSession):
        """将编辑器内容同步回Markdown文件"""
        lines = []

        for block in session.blocks:
            if block.block_type == 'paragraph':
                lines.append(f'[[DOCX-BLOCK type=paragraph id={block.block_id}]]')
                lines.append(str(block.content))
                lines.append('')
            elif block.block_type == 'table':
                lines.append(f'[[DOCX-BLOCK type=table id={block.block_id}]]')
                lines.append('')
                table_data = block.content
                for row_cells in table_data.get('cells', []):
                    row_parts = []
                    for cell in row_cells:
                        cell_marker = cell.get('cell_id', '')
                        content = str(cell.get('content', ''))
                        content = content.replace('\n', '<br>')
                        if cell_marker:
                            row_parts.append(f'{cell_marker} {content}')
                        else:
                            row_parts.append(content)
                    lines.append('| ' + ' | '.join(row_parts) + ' |')
                lines.append('')

        with open(session.markdown_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        cls._update_manifest(session)

    @classmethod
    def _update_manifest(cls, session: EditorSession):
        """更新manifest - 仅同步字体等格式信息"""
        if not os.path.exists(session.manifest_path):
            return

        try:
            with open(session.manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            return

        paragraph_map = {p['block_id']: p for p in manifest.get('paragraphs', [])}
        table_map = {t['block_id']: t for t in manifest.get('tables', [])}
        updated = False

        for block in session.blocks:
            if block.block_type == 'paragraph':
                if block.block_id in paragraph_map:
                    para = paragraph_map[block.block_id]
                    updated_para = False
                    
                    if block.font and para.get('font') != block.font:
                        para['font'] = block.font
                        updated_para = True
                    
                    if block.indent != para.get('indent', False):
                        para['indent'] = block.indent
                        updated_para = True
                        
                    if updated_para:
                        updated = True
            elif block.block_type == 'table':
                table_manifest = table_map.get(block.block_id)
                if not table_manifest:
                    continue
                for row_cells in block.content.get('cells', []):
                    for cell in row_cells:
                        marker = cell.get('cell_id')
                        font_meta = cell.get('font')
                        if not marker or not font_meta:
                            continue
                        target_cell = cls._find_manifest_cell(table_manifest, marker)
                        if target_cell and target_cell.get('font') != font_meta:
                            target_cell['font'] = font_meta
                            updated = True

        if updated:
            with open(session.manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _find_manifest_cell(table_manifest: Dict, marker: str) -> Optional[Dict]:
        for row in table_manifest.get('rows', []):
            for cell in row:
                if cell.get('marker') == marker:
                    return cell
        return None

    @classmethod
    def _save_session_meta(cls, session: EditorSession):
        """保存会话元数据"""
        meta_path = Path(session.working_dir) / 'session.json'
        meta = {
            'session_id': session.session_id,
            'filename': session.filename,
            'original_docx_path': session.original_docx_path,
            'markdown_path': session.markdown_path,
            'manifest_path': session.manifest_path,
            'features_path': session.features_path,
            'working_dir': session.working_dir,
            'created_at': session.created_at,
            'updated_at': session.updated_at,
        }
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    @classmethod
    def _load_session(cls, session_id: str) -> Optional[EditorSession]:
        """从磁盘加载会话"""
        if not cls.SESSIONS_DIR.exists():
            return None

        for dir_path in cls.SESSIONS_DIR.iterdir():
            if dir_path.is_dir() and dir_path.name.startswith(session_id):
                meta_path = dir_path / 'session.json'
                if meta_path.exists():
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)

                    session = EditorSession(
                        session_id=meta['session_id'],
                        filename=meta['filename'],
                        original_docx_path=meta['original_docx_path'],
                        markdown_path=meta['markdown_path'],
                        manifest_path=meta['manifest_path'],
                        features_path=meta.get('features_path', ''),
                        working_dir=meta['working_dir'],
                        created_at=meta['created_at'],
                        updated_at=meta['updated_at'],
                        blocks=[]
                    )

                    if os.path.exists(session.markdown_path) and os.path.exists(session.manifest_path):
                        session.blocks = cls._parse_to_blocks(
                            session.markdown_path,
                            session.manifest_path
                        )

                    cls._sessions[session_id] = session
                    return session

        return None
