"""
知识库服务
Knowledge Base Service

提供文档上传、解析、嵌入、存储和检索功能
"""

import os
import re
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import chromadb
from chromadb.config import Settings
import pypdf
from docx import Document
import markdown
from config.settings import (
    DASHSCOPE_API_KEY,
    KIMI_API_KEY,
    FIREWORKS_API_KEY,
    SHENMA_API_KEY,
    OPENAI_PROXY_BASE,
    GEMINI_THINKING_MODEL,
    XINGHU_API_KEY,
)


# Date extraction patterns for Chinese documents
DATE_PATTERNS = [
    # ISO format: 2024-05-01, 2024/05/01
    (r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"),
    # Chinese format: 2024年5月1日
    (r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"),
    # Labeled dates: 发布日期：2024年5月1日, 生效日期：2024-05-01
    (r'(?:发布|生效|印发|制定|修订|颁布)(?:日期|时间)?[：:\s]*(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?', 
     lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"),
]

# Version extraction patterns
VERSION_PATTERNS = [
    r'[Vv](\d+(?:\.\d+)*)',  # V1.0, v2.3.1
    r'版本[：:\s]*(\d+(?:\.\d+)*)',  # 版本：1.0
    r'第(\d+)版',  # 第2版
    r'(\d{4})版',  # 2024版
]


class KnowledgeBaseService:
    """知识库服务类"""
    
    # 支持的文件类型
    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md'}
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出，清理资源"""
        self.close()
        return False
    
    def close(self):
        """关闭并清理资源"""
        try:
            # ChromaDB客户端没有显式close方法，但可以删除引用
            if hasattr(self, 'chroma_client'):
                del self.chroma_client
            # 如果加载了本地模型，释放内存
            if hasattr(self, 'embedding_model'):
                del self.embedding_model
            print("✅ 知识库服务资源已清理")
        except Exception as e:
            print(f"⚠️ 资源清理警告: {e}")
    
    def __del__(self):
        """析构函数，确保资源被释放"""
        try:
            self.close()
        except:
            pass
    
    def __init__(self, vector_db_path: str, kb_folder: str, api_key: Optional[str] = None, embedding_provider: str = 'qwen', embedding_model_name: Optional[str] = 'text-embedding-v4'):
        """
        初始化知识库服务
        
        Args:
            vector_db_path: 向量数据库存储路径
            kb_folder: 知识库文件存储路径
            api_key: 通义千问API密钥（用于问答生成）
        """
        self.vector_db_path = Path(vector_db_path)
        self.kb_folder = Path(kb_folder)
        self.api_key = api_key
        self.embedding_provider = embedding_provider
        self.embedding_model_name = embedding_model_name
        
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.vector_db_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        if self.embedding_provider == 'local':
            # 懒加载：仅在使用local模式时才导入和加载模型
            try:
                from sentence_transformers import SentenceTransformer
                print("🔄 正在加载本地嵌入模型...")
                self.embedding_model = SentenceTransformer(self.embedding_model_name or 'paraphrase-multilingual-MiniLM-L12-v2')
                print("✅ 本地嵌入模型加载完成")
            except ImportError:
                print("❌ 本地模式需要安装 sentence-transformers: pip install sentence-transformers")
                raise RuntimeError("sentence-transformers 未安装")
        elif self.embedding_provider == 'qwen':
            print("🤖 使用Qwen嵌入模型")
        elif self.embedding_provider == 'fireworks':
            print("🤖 使用Fireworks嵌入模型")
        else:
            print("⚠️ 未知嵌入提供者，回退到Qwen嵌入模型")
            self.embedding_provider = 'qwen'
        
        # 确保目录存在
        self.kb_folder.mkdir(parents=True, exist_ok=True)
        
        # 文件元数据存储（简单文件系统存储）
        self.metadata_folder = self.kb_folder / 'metadata'
        self.metadata_folder.mkdir(parents=True, exist_ok=True)

    import functools
    
    @functools.lru_cache(maxsize=200)
    def _embed_text(self, text: str) -> List[float]:
        if self.embedding_provider == 'local':
            return self.embedding_model.encode(text, show_progress_bar=False).tolist()
        if self.embedding_provider == 'qwen':
            try:
                import dashscope
                dashscope.api_key = DASHSCOPE_API_KEY or self.api_key
                resp = dashscope.TextEmbedding.call(model=self.embedding_model_name or 'text-embedding-v4', input=text)
                if getattr(resp, 'status_code', None) == 200:
                    out = getattr(resp, 'output', {})
                    data = out.get('embeddings') or out.get('data')
                    if data:
                        item = data[0]
                        vec = item.get('embedding') if isinstance(item, dict) else None
                        if vec:
                            return vec
                else:
                    print(f"❌ DashScope Error: {getattr(resp, 'status_code')}, {getattr(resp, 'message')}")
            except Exception as e:
                print(f"❌ DashScope Exception: {str(e)}")
            raise RuntimeError('Qwen嵌入生成失败')
        if self.embedding_provider == 'fireworks':
            try:
                import urllib.request, json as _json
                url = "https://api.fireworks.ai/inference/v1/embeddings"
                payload = _json.dumps({"model": self.embedding_model_name or "nomic-embed-text-v1.5", "input": text}).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {FIREWORKS_API_KEY}"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    body = r.read().decode("utf-8")
                    data = _json.loads(body)
                    arr = data.get("data") or []
                    if arr:
                        emb = arr[0].get("embedding")
                        if emb:
                            return emb
            except Exception:
                pass
            raise RuntimeError('Fireworks嵌入生成失败')
        raise RuntimeError('未知嵌入提供者')
    
    def _extract_publish_date(self, text: str, file_name: str) -> Optional[str]:
        """
        从文档内容中提取发布日期
        
        Args:
            text: 文档文本内容（取前2000字符进行搜索）
            file_name: 文件名（可能包含日期信息）
        
        Returns:
            标准化的日期字符串 (YYYY-MM-DD) 或 None
        """
        # 优先从文件名中提取
        for pattern, formatter in DATE_PATTERNS:
            match = re.search(pattern, file_name)
            if match:
                try:
                    date_str = formatter(match)
                    # 验证日期有效性
                    datetime.strptime(date_str, "%Y-%m-%d")
                    print(f"📅 从文件名提取日期: {date_str}")
                    return date_str
                except:
                    continue
        
        # 从文档内容的开头部分提取（优先级较高的位置）
        search_text = text[:2000] if len(text) > 2000 else text
        
        # 先尝试匹配带标签的日期（发布日期、生效日期等）- 优先级最高
        labeled_pattern = DATE_PATTERNS[2]  # The labeled pattern
        match = re.search(labeled_pattern[0], search_text)
        if match:
            try:
                date_str = labeled_pattern[1](match)
                datetime.strptime(date_str, "%Y-%m-%d")
                print(f"📅 从文档标签提取日期: {date_str}")
                return date_str
            except:
                pass
        
        # 然后尝试其他模式
        for pattern, formatter in DATE_PATTERNS[:2]:
            matches = re.findall(pattern, search_text)
            if matches:
                # 取第一个匹配（通常文档开头的日期最重要）
                try:
                    # 创建一个临时match对象
                    match = re.search(pattern, search_text)
                    if match:
                        date_str = formatter(match)
                        datetime.strptime(date_str, "%Y-%m-%d")
                        print(f"📅 从文档内容提取日期: {date_str}")
                        return date_str
                except:
                    continue
        
        print("📅 未能提取日期，将使用上传时间")
        return None
    
    def _extract_version(self, text: str, file_name: str) -> Optional[str]:
        """
        从文档内容中提取版本号
        
        Args:
            text: 文档文本内容
            file_name: 文件名
        
        Returns:
            版本号字符串或 None
        """
        # 优先从文件名提取
        for pattern in VERSION_PATTERNS:
            match = re.search(pattern, file_name)
            if match:
                version = match.group(1)
                print(f"📌 从文件名提取版本: {version}")
                return version
        
        # 从文档开头提取
        search_text = text[:1000] if len(text) > 1000 else text
        for pattern in VERSION_PATTERNS:
            match = re.search(pattern, search_text)
            if match:
                version = match.group(1)
                print(f"📌 从文档内容提取版本: {version}")
                return version
        
        return None
    
    
    def _get_kb_collection(self, kb_id: int):
        """获取知识库的向量集合"""
        collection_name = f"kb_{kb_id}"
        
        try:
            collection = self.chroma_client.get_collection(name=collection_name)
        except:
            # 如果集合不存在，创建一个新的
            collection = self.chroma_client.create_collection(
                name=collection_name,
                metadata={"kb_id": kb_id, "created_at": datetime.now().isoformat()}
            )
        
        return collection
    
    def parse_file(self, file_path: str, file_type: str) -> str:
        """
        解析文件内容
        
        Args:
            file_path: 文件路径
            file_type: 文件类型（扩展名，如 .pdf）
        
        Returns:
            解析后的文本内容
        """
        if file_type == '.pdf':
            return self._parse_pdf(file_path)
        elif file_type == '.docx':
            return self._parse_docx(file_path)
        elif file_type == '.txt':
            return self._read_text_file(file_path)
        elif file_type == '.md':
            return self._read_text_file(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {file_type}")
    
    def _parse_pdf(self, file_path: str) -> str:
        """
        解析PDF文件（增强版：支持PyMuPDF + 智能OCR回退）
        
        工作流程：
        1. 优先使用PyMuPDF提取文本（速度快）
        2. 智能检测内容密度 - 如果每页内容太少，自动触发OCR
        3. 对无法提取的页面使用OCR识别
        """
        text_content = []
        ocr_pages = []  # 记录需要OCR的页面
        page_char_counts = []  # 记录每页字符数，用于计算平均密度
        
        # 每页最少需要的字符数（正常A4页面应有500+字符）
        MIN_CHARS_PER_PAGE = 100
        
        try:
            # 优先使用 PyMuPDF (fitz)
            import fitz  # PyMuPDF
            
            doc = fitz.open(file_path)
            total_pages = len(doc)
            print(f"📄 使用PyMuPDF解析PDF，共 {total_pages} 页")
            
            for page_num, page in enumerate(doc, 1):
                # 使用多种方法提取文本
                text = page.get_text("text")
                
                # 如果普通提取失败，尝试blocks模式
                if not text.strip():
                    blocks = page.get_text("blocks")
                    text = "\n".join([b[4] for b in blocks if len(b) > 4 and b[6] == 0])
                
                char_count = len(text.strip()) if text else 0
                page_char_counts.append(char_count)
                
                # 判断是否需要OCR：字符数太少说明可能是扫描页
                if char_count >= MIN_CHARS_PER_PAGE:
                    text_content.append(f"[第{page_num}页]\n{text}")
                    print(f"  📄 第{page_num}页: 提取 {char_count} 字符 ✓")
                else:
                    ocr_pages.append(page_num)
                    if char_count > 0:
                        print(f"  ⚠️ 第{page_num}页: 仅 {char_count} 字符（太少），将使用OCR")
                    else:
                        print(f"  ⚠️ 第{page_num}页: 无文本，将使用OCR")
            
            doc.close()
            
            # 计算平均内容密度
            avg_chars = sum(page_char_counts) / total_pages if total_pages > 0 else 0
            print(f"📊 平均每页字符数: {avg_chars:.0f}")
            
            # 如果平均内容太少（每页少于50字符），强制OCR所有页面
            if avg_chars < 50 and total_pages > 1:
                print(f"⚠️ 内容密度太低，强制对所有 {total_pages} 页进行OCR")
                ocr_pages = list(range(1, total_pages + 1))
                text_content = []  # 清空之前的稀疏内容
            
            # 如果有需要OCR的页面，使用pytesseract处理
            if ocr_pages:
                print(f"🔍 开始OCR识别 {len(ocr_pages)} 页...")
                ocr_text = self._ocr_pdf_pages(file_path, ocr_pages)
                if ocr_text:
                    text_content.extend(ocr_text)
            
            # 如果仍然没有内容，提示用户
            if not text_content:
                print("⚠️ PDF无法提取任何文本内容")
                return "[警告] 此PDF无法提取文字内容。可能原因：1）文件损坏 2）加密保护 3）纯图片格式。建议转换为Word文档后重新上传。"
            
        except ImportError as ie:
            print(f"⚠️ PyMuPDF导入失败: {ie}，使用pypdf回退")
            # 回退到 pypdf
            with open(file_path, 'rb') as f:
                pdf_reader = pypdf.PdfReader(f)
                for page_num, page in enumerate(pdf_reader.pages, 1):
                    text = page.extract_text()
                    if text.strip():
                        text_content.append(f"[第{page_num}页]\n{text}")
        
        except Exception as e:
            print(f"❌ PDF解析错误: {e}")
            import traceback
            traceback.print_exc()
            # 回退到 pypdf
            try:
                with open(file_path, 'rb') as f:
                    pdf_reader = pypdf.PdfReader(f)
                    for page_num, page in enumerate(pdf_reader.pages, 1):
                        text = page.extract_text()
                        if text.strip():
                            text_content.append(f"[第{page_num}页]\n{text}")
            except Exception as e2:
                print(f"❌ 回退解析也失败: {e2}")
                return ""
        
        result = "\n\n".join(text_content)
        print(f"✅ PDF解析完成，共提取 {len(result)} 字符")
        return result
    
    def _ocr_pdf_pages(self, file_path: str, page_numbers: List[int]) -> List[str]:
        """
        使用OCR识别PDF中的指定页面
        
        Args:
            file_path: PDF文件路径
            page_numbers: 需要OCR的页码列表（1-indexed）
        
        Returns:
            提取的文本列表
        """
        ocr_results = []
        
        try:
            from pdf2image import convert_from_path
            import pytesseract
            
            print(f"📷 正在将PDF页面转换为图片...")
            # 只转换需要OCR的页面
            for page_num in page_numbers:
                try:
                    # 转换单页
                    images = convert_from_path(
                        file_path, 
                        first_page=page_num, 
                        last_page=page_num,
                        dpi=200  # 200 DPI 足够OCR识别
                    )
                    
                    if images:
                        print(f"🔍 OCR识别第{page_num}页...")
                        # 使用中文+英文语言包
                        text = pytesseract.image_to_string(
                            images[0], 
                            lang='chi_sim+eng',  # 简体中文+英文
                            config='--psm 6'  # 假设为统一的文本块
                        )
                        
                        if text.strip():
                            ocr_results.append(f"[第{page_num}页 - OCR识别]\n{text}")
                            print(f"✅ 第{page_num}页OCR成功，提取 {len(text)} 字符")
                        else:
                            print(f"⚠️ 第{page_num}页OCR未识别到文本")
                            
                except Exception as e:
                    print(f"⚠️ 第{page_num}页OCR失败: {e}")
                    continue
            
        except ImportError as e:
            print(f"⚠️ OCR依赖未安装: {e}")
            print("提示：请安装 pytesseract 和 pdf2image，并确保系统已安装 Tesseract")
        except Exception as e:
            print(f"❌ OCR处理错误: {e}")
            import traceback
            traceback.print_exc()
        
        return ocr_results
    
    def _parse_docx(self, file_path: str) -> str:
        """
        解析DOCX文件，提取段落和表格内容
        
        支持：
        - 段落文本（包括带下划线、加粗等格式的文本）
        - 表格内容（格式化为可读文本）
        - 保持文档原始顺序
        """
        doc = Document(file_path)
        text_content = []
        
        # 使用element.body来按照文档顺序遍历段落和表格
        try:
            from docx.oxml.text.paragraph import CT_P
            from docx.oxml.table import CT_Tbl
            from docx.table import Table
            from docx.text.paragraph import Paragraph
            
            # 获取文档主体元素
            body = doc.element.body
            
            # 按照文档顺序遍历所有元素
            for element in body:
                # 处理段落
                if isinstance(element, CT_P):
                    try:
                        para = Paragraph(element, doc)
                        text = para.text.strip()
                        if text:
                            text_content.append(text)
                    except Exception as e:
                        # 如果段落解析失败，尝试直接提取文本
                        print(f"⚠️ 段落解析警告: {e}")
                        continue
                
                # 处理表格
                elif isinstance(element, CT_Tbl):
                    try:
                        table = Table(element, doc)
                        table_text = self._extract_table_text(table)
                        if table_text:
                            text_content.append(table_text)
                    except Exception as e:
                        print(f"⚠️ 表格解析警告: {e}")
                        continue
        except Exception as e:
            # 如果按顺序解析失败，回退到简单方法
            print(f"⚠️ 使用备用解析方法: {e}")
            # 提取所有段落
            for para in doc.paragraphs:
                text = para.text.strip()
                if text:
                    text_content.append(text)
            
            # 提取所有表格
            for table in doc.tables:
                table_text = self._extract_table_text(table)
                if table_text:
                    text_content.append(table_text)
        
        return "\n\n".join(text_content)
    
    def _extract_table_text(self, table) -> str:
        """
        提取表格内容并格式化为可读文本
        
        Args:
            table: python-docx的Table对象
        
        Returns:
            格式化的表格文本
        """
        if not table.rows:
            return ""
        
        table_lines = []
        table_lines.append("[表格开始]")
        
        # 提取每行数据
        for row_idx, row in enumerate(table.rows):
            row_cells = []
            for cell in row.cells:
                # 提取单元格中的所有文本（包括段落）
                # cell.text会自动提取单元格内所有段落的文本
                cell_text = cell.text.strip()
                
                # 处理换行：将单元格内的换行替换为空格，保持可读性
                cell_text = cell_text.replace('\n', ' ').replace('\r', ' ')
                # 压缩多个空格为单个空格
                while '  ' in cell_text:
                    cell_text = cell_text.replace('  ', ' ')
                
                # 如果单元格为空，用占位符
                if not cell_text:
                    cell_text = "[空]"
                
                row_cells.append(cell_text)
            
            # 用分隔符连接单元格，形成表格行
            if row_cells:
                # 使用 " | " 作为列分隔符，更清晰
                table_lines.append(" | ".join(row_cells))
        
        table_lines.append("[表格结束]")
        return "\n".join(table_lines)
    
    def _read_text_file(self, file_path: str) -> str:
        """读取文本文件（TXT或MD）"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def chunk_text(self, text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> List[str]:
        """
        将文本分块（改进版：更大的块大小，更好的语义完整性）
        
        Args:
            text: 原始文本
            chunk_size: 每个块的字符数（默认800，适合中文）
            chunk_overlap: 块之间的重叠字符数（默认100）
        
        Returns:
            分块后的文本列表
        """
        # 按段落分割（保留双换行作为段落分隔符）
        paragraphs = text.split('\n\n')
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            para_length = len(para)
            
            # 如果段落太短，累加到当前块
            if current_length + para_length <= chunk_size:
                current_chunk.append(para)
                current_length += para_length + 2  # +2 for \n\n
            else:
                # 保存当前块
                if current_chunk:
                    chunk_text = "\n\n".join(current_chunk)
                    chunks.append(chunk_text)
                    
                    # 添加重叠：保留当前块的最后部分
                    if chunk_overlap > 0 and len(chunk_text) > chunk_overlap:
                        overlap_text = chunk_text[-chunk_overlap:]
                        current_chunk = [overlap_text]
                        current_length = chunk_overlap
                    else:
                        current_chunk = []
                        current_length = 0
                
                # 如果单个段落超过块大小，按句子分割（中文句号、问号、感叹号）
                if para_length > chunk_size:
                    # 尝试按中文标点符号分割
                    import re
                    sentences = re.split(r'([。！？；\n])', para)
                    temp_chunk = []
                    temp_length = 0
                    
                    i = 0
                    while i < len(sentences):
                        sentence = sentences[i]
                        if i + 1 < len(sentences):
                            sentence += sentences[i + 1]  # 包含标点符号
                            i += 2
                        else:
                            i += 1
                        
                        sentence = sentence.strip()
                        if not sentence:
                            continue
                            
                        sentence_length = len(sentence)
                        
                        if temp_length + sentence_length <= chunk_size:
                            temp_chunk.append(sentence)
                            temp_length += sentence_length
                        else:
                            if temp_chunk:
                                chunks.append("".join(temp_chunk))
                                # 添加重叠
                                if chunk_overlap > 0 and temp_length > chunk_overlap:
                                    overlap_text = "".join(temp_chunk)[-chunk_overlap:]
                                    temp_chunk = [overlap_text]
                                    temp_length = chunk_overlap
                                else:
                                    temp_chunk = []
                                    temp_length = 0
                            
                            temp_chunk.append(sentence)
                            temp_length = sentence_length
                    
                    if temp_chunk:
                        if current_chunk:
                            current_chunk.extend(temp_chunk)
                            current_length += temp_length
                        else:
                            current_chunk = temp_chunk
                            current_length = temp_length
                else:
                    current_chunk = [para]
                    current_length = para_length
        
        # 保存最后一个块
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
        
        # 过滤掉太短的块（少于50字符的块可能信息不足）
        chunks = [chunk for chunk in chunks if len(chunk.strip()) >= 50]
        
        return chunks
    
    def upload_file(self, kb_id: int, file_path: str, file_name: str, user_id: int = None) -> Dict:
        """
        上传并处理文件
        
        Args:
            kb_id: 知识库ID
            file_path: 上传文件的临时路径
            file_name: 原文件名
            user_id: 用户ID（用于记录，可选）
        
        Returns:
            包含文件信息和处理结果的字典
        """
        # 验证文件类型
        file_ext = Path(file_name).suffix.lower()
        if file_ext not in self.SUPPORTED_EXTENSIONS:
            return {
                'success': False,
                'error': f'不支持的文件类型: {file_ext}，支持的类型: {", ".join(self.SUPPORTED_EXTENSIONS)}'
            }
        
        try:
            # 生成唯一文件ID
            file_id = str(uuid.uuid4())
            
            # 保存文件到知识库目录
            kb_folder = self.kb_folder / f"kb_{kb_id}"
            kb_folder.mkdir(parents=True, exist_ok=True)
            
            saved_file_path = kb_folder / f"{file_id}{file_ext}"
            import shutil
            shutil.copy2(file_path, saved_file_path)
            
            # 解析文件内容
            print(f"📄 正在解析文件: {file_name}")
            text_content = self.parse_file(str(saved_file_path), file_ext)
            
            if not text_content.strip():
                return {
                    'success': False,
                    'error': '文件内容为空或无法解析'
                }
            
            # 提取文档日期和版本信息
            print(f"📅 正在提取文档元数据...")
            publish_date = self._extract_publish_date(text_content, file_name)
            version = self._extract_version(text_content, file_name)
            
            # 如果未能提取日期，使用上传时间
            upload_time = datetime.now()
            if not publish_date:
                publish_date = upload_time.strftime("%Y-%m-%d")
            
            # 分块
            print(f"📝 正在分块处理...")
            chunks = self.chunk_text(text_content)
            print(f"✅ 分成 {len(chunks)} 个块")
            
            # 获取知识库的向量集合
            collection = self._get_kb_collection(kb_id)
            
            print(f"🔄 正在生成嵌入向量...")
            chunk_ids = []
            chunk_embeddings = []
            chunk_documents = []
            chunk_metadatas = []
            
            for idx, chunk in enumerate(chunks):
                chunk_id = f"{file_id}_chunk_{idx}"
                chunk_ids.append(chunk_id)
                chunk_documents.append(chunk)
                
                embedding = self._embed_text(chunk)
                chunk_embeddings.append(embedding)
                
                # 元数据 - 包含发布日期和版本信息
                chunk_metadatas.append({
                    'file_id': file_id,
                    'file_name': file_name,
                    'file_path': str(saved_file_path),
                    'chunk_index': idx,
                    'chunk_count': len(chunks),
                    'uploaded_at': upload_time.isoformat(),
                    'publish_date': publish_date,  # 新增：发布日期
                    'version': version or '',      # 新增：版本号
                })
            
            # 添加到向量数据库
            collection.add(
                ids=chunk_ids,
                embeddings=chunk_embeddings,
                documents=chunk_documents,
                metadatas=chunk_metadatas
            )
            print(f"✅ 向量存储完成")
            
            # 保存文件元数据
            metadata = {
                'file_id': file_id,
                'file_name': file_name,
                'file_path': str(saved_file_path),
                'file_type': file_ext,
                'chunk_count': len(chunks),
                'file_size': os.path.getsize(saved_file_path),
                'uploaded_at': upload_time.isoformat(),
                'publish_date': publish_date,  # 新增
                'version': version or '',       # 新增
                'kb_id': kb_id,
                'user_id': user_id
            }
            
            metadata_file = self.metadata_folder / f"{file_id}.json"
            import json
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            return {
                'success': True,
                'file_id': file_id,
                'file_name': file_name,
                'chunk_count': len(chunks),
                'message': f'文件上传成功，共处理 {len(chunks)} 个块'
            }
            
        except Exception as e:
            print(f"❌ 文件处理失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': f'文件处理失败: {str(e)}'
            }
    
    def search_knowledge(self, kb_id: int, query: str, top_k: int = 5) -> List[Dict]:
        """
        在知识库中搜索相关内容
        
        Args:
            kb_id: 知识库ID
            query: 查询文本
            top_k: 返回前k个最相关的结果
        
        Returns:
            包含相关内容和元数据的列表
        """
        try:
            # 获取知识库的向量集合
            collection = self._get_kb_collection(kb_id)
            
            # 检查集合中是否有数据
            collection_count = collection.count()
            if collection_count == 0:
                print(f"⚠️ 知识库 {kb_id} 中没有数据")
                return []
            
            print(f"🔍 搜索查询: {query}")
            print(f"📊 知识库中共有 {collection_count} 个文档块")
            
            query_embedding = self._embed_text(query)
            
            # 搜索相似内容（增加返回数量，让Agent有更多文档块可以搜索）
            # 对于小知识库，返回更多结果；对于大知识库，限制数量
            n_results = min(max(top_k * 3, 15), collection_count)  # 至少返回15个，最多返回所有文档块
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )
            
            # 组织结果
            search_results = []
            if results['documents'] and len(results['documents'][0]) > 0:
                for idx, doc in enumerate(results['documents'][0]):
                    distance = results['distances'][0][idx] if results['distances'] else None
                    metadata = results['metadatas'][0][idx] if results['metadatas'] else {}
                    
                    # ChromaDB默认使用L2距离（欧氏距离），值越小越相似
                    # 将距离转换为相似度分数：使用 1/(1+distance) 归一化到0-1之间
                    # 距离为0时相似度为1，距离越大相似度越接近0
                    if distance is not None and distance >= 0:
                        similarity = 1 / (1 + distance)
                    else:
                        similarity = 0
                    
                    # 打印调试信息（前3个结果）
                    if idx < 3:
                        print(f"  📄 结果 {idx + 1}: 相似度={similarity:.4f}, 距离={distance:.4f}")
                        print(f"     内容预览: {doc[:100]}...")
                    
                    search_results.append({
                        'content': doc,
                        'metadata': metadata,
                        'distance': distance,
                        'similarity': similarity
                    })
                
                # 按相似度排序（从高到低）
                search_results.sort(key=lambda x: x['similarity'], reverse=True)
                
                # 不过滤结果，返回所有搜索结果让Agent自己判断
                # Agent会在文档块中智能搜索，即使相似度较低也可能包含相关信息
                print(f"✅ 找到 {len(search_results)} 个文档块供Agent搜索")
                return search_results
            else:
                print(f"⚠️ 未找到任何搜索结果")
                return []
            
        except Exception as e:
            print(f"❌ 知识库搜索失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def answer_question(self, kb_id: int, question: str, top_k: int = 5, model: str = "qwen-plus", user_id: int = None, direct_answer: bool = True) -> Dict:
        """
        基于知识库回答用户问题

        Args:
            kb_id: 知识库ID
            question: 用户问题
            top_k: 检索前k个相关文档
            model: 使用的AI模型 (qwen-plus, kimi, super, super2, super3)
            user_id: 用户ID
            direct_answer: 是否直接回答（跳过思考链）
        
        Returns:
            包含答案和相关文档的结果字典
        """
        # 如果没有配置API Key，只返回检索结果
        if not self.api_key:
            search_results = self.search_knowledge(kb_id, question, top_k)
            return {
                'success': True,
                'answer': '未配置API密钥，仅显示检索结果',
                'raw_results': search_results
            }
        
        # 搜索相关知识（使用更大的top_k，让Agent有更多文档块可以搜索）
        print(f"🔍 开始搜索问题: {question}")
        # 对于小知识库，返回更多文档块；对于大知识库，至少返回20个
        raw_results = self.search_knowledge(kb_id, question, top_k=max(top_k, 20))
        
        if not raw_results:
            print(f"⚠️ 未找到相关搜索结果")
            return {
                'success': True,
                'answer': '未找到相关的知识内容，请检查您的知识库中是否有相关内容。'
            }
        
        # --- Recency Re-ranking (时间重排序) ---
        print(f"⏱️ 正在进行时间重排序...")
        scored_results = []
        now = datetime.now()
        
        for res in raw_results:
            metadata = res.get('metadata', {})
            similarity = res.get('similarity', 0)
            publish_date_str = metadata.get('publish_date')
            
            # 计算时间得分 (Time Decay Score)
            time_score = 0.5  # 默认中间值
            if publish_date_str:
                try:
                    pub_date = datetime.strptime(publish_date_str, "%Y-%m-%d")
                    days_diff = (now - pub_date).days
                    # 半衰期衰减：假设1年(365天)衰减一半
                    # score = 1 / (1 + days_diff / 365)
                    if days_diff < 0: days_diff = 0 # 未来时间处理
                    time_score = 1.0 / (1.0 + days_diff / 365.0)
                except:
                    pass
            
            # 综合得分：语义相似度 70% + 时间时效性 30%
            # 注意：如果语义相似度很低，时间再新也没用，所以可以考虑乘法或加权
            final_score = (similarity * 0.7) + (time_score * 0.3)
            
            res['final_score'] = final_score
            res['time_score'] = time_score
            scored_results.append(res)
            
        # 按综合得分重新排序
        scored_results.sort(key=lambda x: x['final_score'], reverse=True)
        search_results = scored_results[:5]  # 取前5个最相关的片段构建Context (优化：从10减到5)
        
        print(f"✅ 找到 {len(search_results)} 个文档片段供Agent搜索 (已按 时效+相关性 重排序)")
        
        # --- 构建结构化上下文 ---
        context_parts = ["<documents>"]
        for idx, result in enumerate(search_results, 1):
            meta = result['metadata']
            source = meta.get('file_name', 'Unknown')
            pub_date = meta.get('publish_date', 'Unknown')
            version = meta.get('version', '')
            content = result['content']
            
            doc_xml = f"""    <doc id="{idx}">
        <metadata>
            <source>{source}</source>
            <publish_date>{pub_date}</publish_date>
            <version>{version}</version>
        </metadata>
        <content>
{content[:500]} 
        </content>
    </doc>"""
            context_parts.append(doc_xml)
        context_parts.append("</documents>")
        
        context = "\n".join(context_parts)
        
        # 使用通义千问生成答案
        try:
            import dashscope
            dashscope.api_key = self.api_key
            
            # 使用LangChain的ChatTongyi进行更智能的搜索和回答
            try:
                from langchain_core.messages import SystemMessage, HumanMessage
                import os

                # 根据模型参数选择不同的LLM
                # ... (Model selection logic remains same, condensed for brevity in edit if unchanged, but included full here for safety) ...
                if model == "kimi":
                    from langchain_openai import ChatOpenAI
                    if not KIMI_API_KEY: raise Exception("Kimi API密钥未配置")
                    llm = ChatOpenAI(model="moonshot-v1-8k", openai_api_key=KIMI_API_KEY, openai_api_base="https://api.moonshot.cn/v1", temperature=0.1)
                    print(f"🤖 使用Kimi模型")
                elif model == "super":
                    from langchain_openai import ChatOpenAI
                    xinghu_key = XINGHU_API_KEY or os.environ.get("XINGHU_API_KEY", "")
                    if not xinghu_key: raise Exception("星湖 OpenAI 代理 API 密钥未配置")
                    llm = ChatOpenAI(model="gpt-5-chat-latest", openai_api_key=xinghu_key, openai_api_base="https://xinghuapi.com/v1", temperature=0.1)
                    print(f"🤖 使用超级模型 (gpt-5-chat-latest@星湖)")
                elif model == "super2":
                    from langchain_openai import ChatOpenAI
                    if not SHENMA_API_KEY: raise Exception("OpenAI 代理 API 密钥未配置")
                    llm = ChatOpenAI(model="gpt-5.1-2025-11-13", openai_api_key=SHENMA_API_KEY, openai_api_base=OPENAI_PROXY_BASE, temperature=0.1)
                    print(f"🤖 使用超级模型2 (GPT-5.1 2025)")
                elif model == "super3":
                    from langchain_openai import ChatOpenAI
                    if not SHENMA_API_KEY: raise Exception("OpenAI 代理 API 密钥未配置")
                    llm = ChatOpenAI(model="claude-sonnet-4-5-20250929", openai_api_key=SHENMA_API_KEY, openai_api_base=OPENAI_PROXY_BASE, temperature=0.1)
                    print(f"🤖 使用超级模型3 (Claude Sonnet 4.5)")
                else:
                    from langchain_community.chat_models import ChatTongyi
                    llm = ChatTongyi(dashscope_api_key=DASHSCOPE_API_KEY or self.api_key, model_name="qwen-plus", temperature=0.1)
                    print(f"🤖 使用通义千问模型")
                
                if direct_answer:
                    system_prompt = """你是一个专业的分析助手。你的任务是根据提供的文档回答用户问题。

核心原则：
1. **时效性优先**：你必须检查每个文档片段的 <publish_date>。如果不同文档存在冲突，必须采纳日期更新的文档内容。
2. **事实导向**：严禁使用自己的知识或编造信息，只能基于提供的 <documents> 回答。
3. **直接回答**：不要输出任何思考过程，直接给出最终的专业回答。
"""
                    user_message_prompt = f"""请阅读以下包含元数据的文档片段，并直接回答我的问题。

{context}

用户问题：{question}
"""
                else:
                    system_prompt = """你是一个专业的分析助手。你的任务是根据提供的文档回答用户问题。

核心原则：
1. **时效性优先**：你必须检查每个文档片段的 <publish_date>。
2. **冲突解决**：如果不同文档中的信息存在冲突（例如旧文件说A，新文件说B），你必须采纳**日期更新**的文档内容，并忽略旧文档。
3. **事实导向**：严禁使用你自己的知识或编造信息，只能基于提供的 <documents> 回答。

思考过程要求：
在回答之前，请先进行分析思考：
1. **文档分析**：列出检索到的所有相关文档及其日期、版本。
2. **冲突检测**：识别文档之间是否存在事实冲突。
3. **决策逻辑**：如果存在冲突，明确指出哪个文档更新，应该采纳哪个。

【重要】输出格式要求（必须严格遵守）：
你的输出格式必须严格按照以下模板：

-thinking-
1. 文档分析：
   - [在这里列出文档来源、日期、版本等信息]
2. 冲突检测：
   - [在这里说明是否存在冲突]
3. 决策逻辑：
   - [在这里说明采纳哪个文档的内容]

✅ 回答
[在这里输出正式的回答内容，使用清晰的标题和列表格式]

注意：
- 第一行必须是 -thinking-（减号加thinking加减号）
- 思考部分和回答部分中间必须有双空行和 ✅ 回答
- 回答部分使用清晰的层次结构，重点内容加粗
"""
                    user_message_prompt = f"""请阅读以下包含元数据的文档片段，并回答我的问题。

{context}

用户问题：{question}

请开始分析："""
                
                # 构建用户消息
                user_message = user_message_prompt
                
                # 调用LLM
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message)
                ]
                
                print(f"🤖 使用Agent进行智能分析(CoT)...")
                response = llm.invoke(messages)
                answer = response.content.strip()
                
                # Log LLM usage
                try:
                    from utils.llm_logger import log_llm_call_async
                    # Try to get user_id from context or pass None
                    log_llm_call_async(
                        user_id=user_id,
                        feature='kb',
                        model_name=model,
                        api_provider='qwen' if 'qwen' in (model or '') else 'openai'
                    )
                except Exception:
                    pass
                
                print(f"✅ Agent生成答案成功，长度: {len(answer)} 字符")
                
            except Exception as e:
                print(f"⚠️ 使用LangChain失败，回退到直接API调用: {e}")
                import traceback
                traceback.print_exc()
                
                # 回退 prompt (simplified)
                prompt = f"""你是一个智能助手。请基于以下文档回答问题。如果文档有冲突，请以日期较新的为准。
                
{context}

问题：{question}
"""
                # ... (Simple invoke fallback if needed, or just return error)
                return {
                    'success': False, 
                    'error': f"LLM调用失败: {e}"
                }

        except Exception as e:
             # Outer try-except
             print(f"❌ 回答生成失败: {e}")
             return {'success': False, 'error': str(e)}

        return {
            'success': True,
            'answer': answer,
            'results': search_results # Return structured results
        }

    def answer_question_stream(self, kb_id: int, question: str, top_k: int = 15, model: str = "qwen-plus", user_id: int = None, direct_answer: bool = True, update_callback=None):
        """
        流式回答知识库问题
        """
        if not self.api_key:
            yield "未配置API密钥，无法生成回答。"
            return
            
        # 1. 搜索
        raw_results = self.search_knowledge(kb_id, question, top_k=max(top_k, 20))
        if not raw_results:
            yield "未找到相关的知识内容，请检查您的知识库中是否有相关内容。"
            return
            
        # 2. 重排序
        now = datetime.now()
        scored_results = []
        for res in raw_results:
            metadata = res.get('metadata', {})
            similarity = res.get('similarity', 0)
            publish_date_str = metadata.get('publish_date')
            time_score = 0.5
            if publish_date_str:
                try:
                    pub_date = datetime.strptime(publish_date_str, "%Y-%m-%d")
                    days_diff = max(0, (now - pub_date).days)
                    time_score = 1.0 / (1.0 + days_diff / 365.0)
                except:
                    pass
            res['final_score'] = (similarity * 0.7) + (time_score * 0.3)
            scored_results.append(res)
            
        scored_results.sort(key=lambda x: x['final_score'], reverse=True)
        search_results = scored_results[:15]  # 进一步增加到15个块以应对复杂课表（多页/多块）
        
        # 3. 构建上下文
        context_parts = ["<documents>"]
        for idx, result in enumerate(search_results, 1):
            meta = result['metadata']
            doc_xml = f'''    <doc id="{idx}">
        <metadata>
            <source>{meta.get('file_name', 'Unknown')}</source>
            <publish_date>{meta.get('publish_date', 'Unknown')}</publish_date>
            <version>{meta.get('version', '')}</version>
        </metadata>
        <content>\n{result['content'][:1000]}\n        </content>
    </doc>'''
            context_parts.append(doc_xml)
        context_parts.append("</documents>")
        context = "\n".join(context_parts)
        
        # 4. 构建Prompt (专门针对课表/文档分析优化)
        if direct_answer:
            system_prompt = """你是一个极速且专业的知识库分析助手。你的任务是根据提供的 <documents> 准确回答用户问题。
核心原则：
1. **表格与课表解析**：文档可能包含复杂的课程表或名单，请仔细核对“星期”、“节次/时间”以及对应的“课程名称”和“教师”。
2. **时效性优先**：严格参考 <publish_date>，如果信息冲突，以最新的文档为准。
3. **精准提取**：如果文档中没有明确答案，请如实告知，不要有任何编造。
4. **简洁直接**：直接输出最终答案，不需要输出任何开场白或分析过程。"""
            user_message = f"请阅读以下包含元数据的文档片段，并直接回答我的问题。\n\n{context}\n\n用户问题：{question}"
        else:
            system_prompt = """你是一个专业的分析助手。你的任务是根据提供的文档回答用户问题。
核心原则：
1. **时效性优先**：必须检查 <publish_date>。
2. **冲突解决**：采纳日期最新的文档内容。
3. **事实导向**：基于 <documents> 回答。

输出格式必须严格按照以下模板：
-thinking-
[分析过程]
✅ 回答
[正式回答]"""
            user_message = f"请阅读文档片段并回答：\n\n{context}\n\n用户问题：{question}\n\n请开始分析："
            
        # 5. 调用LLM流式生成
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            import os
            
            # 初始化LLM
            if model == "kimi":
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(model="moonshot-v1-8k", openai_api_key=KIMI_API_KEY, openai_api_base="https://api.moonshot.cn/v1", temperature=0.1)
            elif model == "super":
                from langchain_openai import ChatOpenAI
                xinghu_key = XINGHU_API_KEY or os.environ.get("XINGHU_API_KEY", "")
                llm = ChatOpenAI(model="gpt-5-chat-latest", openai_api_key=xinghu_key, openai_api_base="https://xinghuapi.com/v1", temperature=0.1)
            elif model == "super2":
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(model="gpt-5.1-2025-11-13", openai_api_key=SHENMA_API_KEY, openai_api_base=OPENAI_PROXY_BASE, temperature=0.1)
            elif model == "super3":
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(model="claude-sonnet-4-5-20250929", openai_api_key=SHENMA_API_KEY, openai_api_base=OPENAI_PROXY_BASE, temperature=0.1)
            else:
                from langchain_community.chat_models import ChatTongyi
                import dashscope
                dashscope.api_key = self.api_key
                llm = ChatTongyi(dashscope_api_key=DASHSCOPE_API_KEY or self.api_key, model_name="qwen-plus", temperature=0.1)
                
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
            
            full_response = ""
            chunk_char_count = 0
            
            for chunk in llm.stream(messages):
                content = chunk.content
                if content:
                    full_response += content
                    chunk_char_count += len(content)
                    
                    # 每累积15个字符更新一次数据库，让前端流式打字效果更平滑
                    if update_callback and chunk_char_count >= 15:
                        update_callback(full_response)
                        chunk_char_count = 0
                        
                    yield content
                    
            # 确保最后更新一次
            if update_callback and chunk_char_count > 0:
                update_callback(full_response)
                
            # 记录LLM调用
            try:
                from utils.llm_logger import log_llm_call_async
                log_llm_call_async(user_id=user_id, feature='kb_stream', model_name=model, api_provider='qwen' if 'qwen' in (model or '') else 'openai')
            except Exception:
                pass
                
        except Exception as e:
            print(f"流式生成失败: {e}")
            yield f"\n[生成出错: {str(e)}]"
            if update_callback:
                update_callback(full_response + f"\n[生成出错: {str(e)}]")

    
    def list_kb_files(self, kb_id: int) -> List[Dict]:
        """列出知识库中的所有文件"""
        try:
            metadata_files = list(self.metadata_folder.glob('*.json'))
            kb_files = []
            
            for metadata_file in metadata_files:
                import json
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    
                if metadata.get('kb_id') == kb_id:
                    kb_files.append(metadata)
            
            # 按上传时间排序
            kb_files.sort(key=lambda x: x.get('uploaded_at', ''), reverse=True)
            
            return kb_files
            
        except Exception as e:
            print(f"❌ 获取文件列表失败: {e}")
            return []
    
    def delete_kb_file(self, kb_id: int, file_id: str) -> Dict:
        """删除知识库文件及其相关数据"""
        try:
            # 读取文件元数据
            metadata_file = self.metadata_folder / f"{file_id}.json"
            if not metadata_file.exists():
                return {'success': False, 'error': '文件不存在'}
            
            import json
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # 验证文件所有权
            if metadata.get('kb_id') != kb_id:
                return {'success': False, 'error': '无权删除此文件'}
            
            # 从向量数据库中删除相关块
            collection = self._get_kb_collection(kb_id)
            
            # 获取所有相关的块ID
            results = collection.get(where={'file_id': file_id})
            if results['ids']:
                collection.delete(ids=results['ids'])
            
            # 删除文件
            file_path = metadata.get('file_path')
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            
            # 删除元数据文件
            metadata_file.unlink()
            
            return {'success': True, 'message': '文件删除成功'}
            
        except Exception as e:
            print(f"❌ 删除文件失败: {e}")
            return {'success': False, 'error': f'删除失败: {str(e)}'}
    
    def get_collection_stats(self, kb_id: int) -> Dict:
        """获取知识库统计信息"""
        try:
            collection = self._get_kb_collection(kb_id)
            count = collection.count()
            return {'total_chunks': count, 'kb_id': kb_id}
        except Exception as e:
            print(f"❌ 获取统计信息失败: {e}")
            return {'total_chunks': 0, 'kb_id': kb_id}
    
    def delete_kb(self, kb_id: int) -> Dict:
        """删除整个知识库及其所有数据"""
        try:
            # 删除向量集合
            collection_name = f"kb_{kb_id}"
            try:
                self.chroma_client.delete_collection(name=collection_name)
            except:
                pass  # 集合可能不存在
            
            # 删除知识库文件夹
            kb_folder = self.kb_folder / f"kb_{kb_id}"
            if kb_folder.exists():
                import shutil
                shutil.rmtree(kb_folder)
            
            # 删除相关的元数据文件
            metadata_files = list(self.metadata_folder.glob('*.json'))
            for metadata_file in metadata_files:
                import json
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                if metadata.get('kb_id') == kb_id:
                    metadata_file.unlink()
            
            return {'success': True, 'message': '知识库删除成功'}
            
        except Exception as e:
            print(f"❌ 删除知识库失败: {e}")
            return {'success': False, 'error': f'删除失败: {str(e)}'}
