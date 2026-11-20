"""
截图问答服务
Screenshot QA Service

处理截图上传、问答提取、存储和检索功能
"""

import os
import re
import uuid
import json
import base64
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime
from PIL import Image
import chromadb
from chromadb.config import Settings
from config.settings import DASHSCOPE_API_KEY, FIREWORKS_API_KEY


class ScreenshotQAService:
    """截图问答服务类"""
    
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
            # 清理ChromaDB客户端
            if hasattr(self, 'chroma_client'):
                del self.chroma_client
            # 清理本地嵌入模型
            if hasattr(self, 'embedding_model'):
                del self.embedding_model
            print("✅ 截图问答服务资源已清理")
        except Exception as e:
            print(f"⚠️ 资源清理警告: {e}")
    
    def __del__(self):
        """析构函数，确保资源被释放"""
        try:
            self.close()
        except:
            pass

    # 长截图判断标准
    MIN_HEIGHT_FOR_LONG = 2000  # 最小高度（像素）
    MIN_HEIGHT_WIDTH_RATIO = 2.0  # 最小高宽比
    SPLIT_HEIGHT = 1500  # 基础分割高度
    OVERLAP_HEIGHT = 300  # 重叠区域高度
    MIN_SEGMENT_HEIGHT = 650  # 避免切得太小
    ADAPTIVE_SEARCH_RANGE = 260  # 在目标切割点附近寻找空白带
    BLANK_ROW_DARK_RATIO = 0.012  # 被视为空白行的黑色像素占比
    BLANK_ROW_THRESHOLD = 235  # 像素值阈值（越大越接近白色）
    BLANK_MIN_STREAK = 18  # 连续多少行满足条件才认为是空白区域

    # 细粒度重试切片参数
    RETRY_SPLIT_HEIGHT = 620
    RETRY_OVERLAP = 150
    MAX_RETRY_SEGMENTS = 4

    QUESTION_NUMBER_REGEX = re.compile(r'^(?:\s*\(?\s*(?:第)?)(\d{1,4})(?:\s*[题\.、\)])')

    def __init__(self, vector_db_path: str, kb_folder: str, api_key: Optional[str] = None, embedding_provider: str = 'qwen', embedding_model_name: Optional[str] = 'text-embedding-v4'):
        """
        初始化截图问答服务

        Args:
            vector_db_path: 向量数据库存储路径
            kb_folder: 知识库文件存储路径
            api_key: DashScope API密钥（用于VLM）
        """
        self.vector_db_path = Path(vector_db_path)
        self.kb_folder = Path(kb_folder)
        self.api_key = api_key
        self.embedding_provider = embedding_provider
        self.embedding_model_name = embedding_model_name

        # 初始化向量数据库客户端
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
        self.screenshots_folder = self.kb_folder / 'screenshots'
        self.screenshots_folder.mkdir(parents=True, exist_ok=True)

        # 元数据存储
        self.metadata_folder = self.kb_folder / 'metadata_qa'
        self.metadata_folder.mkdir(parents=True, exist_ok=True)

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
            except Exception:
                pass
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

    def is_long_screenshot(self, image_path: str) -> bool:
        """
        判断是否为长截图（组合条件）

        Args:
            image_path: 图片路径

        Returns:
            是否为长截图
        """
        try:
            with Image.open(image_path) as img:
                width, height = img.size

                # 条件1: 高度超过阈值
                height_check = height > self.MIN_HEIGHT_FOR_LONG

                # 条件2: 高宽比超过阈值
                ratio_check = (height / width) > self.MIN_HEIGHT_WIDTH_RATIO if width > 0 else False

                # 组合判断
                is_long = height_check and ratio_check

                print(f"📏 图片尺寸: {width}x{height}, 高宽比: {height/width:.2f}, 长截图: {is_long}")
                return is_long

        except Exception as e:
            print(f"❌ 图片检查失败: {e}")
            return False

    def split_long_screenshot(self, image_path: str, output_dir: str) -> List[Dict]:
        """
        分割长截图（重叠分割）

        Args:
            image_path: 图片路径
            output_dir: 输出目录

        Returns:
            分割后的图片信息列表 [{'path': str, 'start_y': int, 'end_y': int, 'height': int, 'part_index': int}]
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            with Image.open(image_path) as img:
                width, height = img.size
                is_long = self.is_long_screenshot(image_path)

                # 准备空白区域索引，用于自适应切割
                blank_regions = self._detect_horizontal_blanks(img) if is_long else []

                segments: List[Dict] = []
                start_y = 0
                part_num = 0

                # 非长截图也统一进入切片流程，便于统一处理
                while start_y < height:
                    # 目标切割位置
                    target_end = min(start_y + self.SPLIT_HEIGHT, height)

                    if not is_long:
                        # 普通截图只切一次
                        target_end = height

                    adaptive_end = self._find_adaptive_split_point(
                        blank_regions, start_y, target_end, height
                    )
                    end_y = adaptive_end if adaptive_end else target_end

                    if end_y - start_y < self.MIN_SEGMENT_HEIGHT and end_y != height:
                        end_y = min(start_y + self.MIN_SEGMENT_HEIGHT, height)

                    cropped = img.crop((0, start_y, width, end_y))
                    prepared = self._prepare_image_for_vlm(cropped)

                    part_filename = f"{Path(image_path).stem}_part_{part_num}{Path(image_path).suffix}"
                    part_path = output_path / part_filename
                    prepared.save(part_path)

                    segments.append({
                        'path': str(part_path),
                        'start_y': start_y,
                        'end_y': end_y,
                        'height': end_y - start_y,
                        'part_index': part_num
                    })

                    print(f"✂️  分割片段 {part_num}: y={start_y}-{end_y} (自适应: {bool(adaptive_end)})")

                    if end_y >= height or not is_long:
                        break

                    start_y = max(end_y - self.OVERLAP_HEIGHT, 0)
                    part_num += 1

                print(f"✅ 截图切片完成，共 {len(segments)} 个片段")
                return segments

        except Exception as e:
            print(f"❌ 图片分割失败: {e}")
            import traceback
            traceback.print_exc()
            return [{
                'path': image_path,
                'start_y': 0,
                'end_y': 0,
                'height': 0,
                'part_index': 0
            }]

    def _image_to_base64(self, image_path: str) -> str:
        """将图片转换为base64编码"""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def _prepare_image_for_vlm(self, image: Image.Image) -> Image.Image:
        """将图片按需放大，保证最短边足够清晰"""
        width, height = image.size
        min_side = min(width, height)
        target_min = 1536

        if min_side >= target_min:
            return image

        scale = target_min / max(min_side, 1)
        new_size = (int(width * scale), int(height * scale))
        print(f"🔍 放大切片: {width}x{height} → {new_size}")
        return image.resize(new_size, Image.LANCZOS)

    def _detect_horizontal_blanks(self, image: Image.Image) -> List[Dict]:
        """扫描图像的水平空白区域，便于自适应切割"""
        grayscale = image.convert('L')
        width, height = grayscale.size
        pixels = grayscale.load()

        blank_regions = []
        streak = 0
        streak_start = 0
        sample_step = max(1, width // 800)
        sample_count = (width + sample_step - 1) // sample_step

        for y in range(height):
            dark_pixels = 0
            for x in range(0, width, sample_step):
                if pixels[x, y] < self.BLANK_ROW_THRESHOLD:
                    dark_pixels += 1

            dark_ratio = dark_pixels / max(sample_count, 1)
            if dark_ratio <= self.BLANK_ROW_DARK_RATIO:
                if streak == 0:
                    streak_start = y
                streak += 1
            else:
                if streak >= self.BLANK_MIN_STREAK:
                    blank_regions.append({
                        'start': streak_start,
                        'end': y,
                        'height': streak
                    })
                streak = 0

        if streak >= self.BLANK_MIN_STREAK:
            blank_regions.append({'start': streak_start, 'end': height, 'height': streak})

        print(f"🧮 检测到 {len(blank_regions)} 个潜在空白区域用于切割")
        return blank_regions

    def _find_adaptive_split_point(
        self,
        blank_regions: List[Dict],
        start_y: int,
        target_end: int,
        image_height: int
    ) -> Optional[int]:
        """在目标附近寻找空白带，返回更平滑的切割点"""
        if not blank_regions:
            return None

        candidates = []
        for region in blank_regions:
            center = (region['start'] + region['end']) // 2
            if center <= start_y + self.MIN_SEGMENT_HEIGHT:
                continue
            if abs(center - target_end) <= self.ADAPTIVE_SEARCH_RANGE:
                candidates.append(center)

        if not candidates:
            return None

        best_point = min(candidates, key=lambda p: abs(p - target_end))
        return min(best_point, image_height)

    def extract_qa_pairs_from_image(self, image_path: str) -> List[Dict]:
        """
        使用VLM从图片中提取问答对

        Args:
            image_path: 图片路径

        Returns:
            问答对列表，格式: [{"question": "...", "answer": "..."}, ...]
        """
        if not self.api_key:
            raise ValueError("未配置DashScope API密钥，无法使用VLM功能")

        try:
            import dashscope
            from dashscope import MultiModalConversation

            dashscope.api_key = self.api_key

            # 读取图片并转换为base64
            print(f"🖼️  正在分析图片: {Path(image_path).name}")

            # 构建提示词
            prompt = """请仔细分析这张截图，提取其中所有的问答对（问题和答案）。

**要求**：
1. 识别截图中所有的问题和对应的答案
2. 问题可能以各种形式出现：
   - 标准问句（带问号）
   - 陈述式问题
   - 题目序号后的问题
   - 练习题、测试题等
3. 答案可能在问题下方、右侧或其他位置
4. 保持问题和答案的原始表述，不要修改或简化

**⚠️ 选择题特别要求（极其重要）**：
如果是选择题（单选或多选），你**必须**：
1. **仔细识别正确答案**：
   - 查找答案标记：✓、√、对号、勾选、高亮、加粗、下划线
   - 查找答案说明：如"答案："、"正确答案："、"参考答案："后面的内容
   - 查找答案解析：通常在选项后有"正确"、"对"、"√"等标识
2. **只提取正确答案，不要提取错误选项**
3. **答案格式要求**：
   - 同时包含选项字母和完整内容
   - 格式：`A. 选项内容` 或 `A. 选项内容（如果有解释也要包含）`
   - 多选题：`A. 内容 B. 内容` 或分行列出
4. **如果无法确定正确答案**：
   - 不要猜测或列出所有选项
   - 在answer字段中说明："[无法确定正确答案，请人工审核]"

**示例**：
- ✅ 正确：
  ```json
  {
    "question": "以下哪个是Python的特点？\nA. 编译型语言\nB. 解释型语言\nC. 汇编语言",
    "answer": "B. 解释型语言"
  }
  ```
- ❌ 错误：不要输出 "A. 编译型语言 B. 解释型语言 C. 汇编语言"

**输出格式**（严格的JSON数组）：
```json
[
  {
    "question": "完整的问题内容（包括所有选项，如果是选择题）",
    "answer": "正确答案（仅限正确答案，不要包含错误选项）"
  },
  ...
]
```

**注意**：
- 只输出JSON数组，不要包含任何其他文字说明
- 如果截图中没有明确的问答对，返回空数组 []
- 确保JSON格式正确，可以被解析
- 务必识别正确答案，不要提取错误选项！
"""

            # 调用VLM API
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"image": f"file://{os.path.abspath(image_path)}"},
                        {"text": prompt}
                    ]
                }
            ]

            response = MultiModalConversation.call(
                model=os.getenv('VLM_MODEL', 'qwen-vl-max'),
                messages=messages,
                result_format="message",
                max_output_tokens=4096
            )

            if response.status_code != 200:
                raise Exception(f"VLM API调用失败: {response.message}")

            # 解析响应
            result_text = response.output.choices[0].message.content[0]['text']
            print(f"📝 VLM响应: {result_text[:200]}...")

            # 提取JSON内容
            # 清理可能的markdown代码块标记
            result_text = result_text.strip()
            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.startswith('```'):
                result_text = result_text[3:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]
            result_text = result_text.strip()

            # 解析JSON
            qa_pairs = json.loads(result_text)

            if not isinstance(qa_pairs, list):
                raise ValueError("VLM返回���不是数组格式")

            # 验证格式
            valid_qa_pairs = []
            for qa in qa_pairs:
                if isinstance(qa, dict) and 'question' in qa and 'answer' in qa:
                    valid_qa_pairs.append({
                        'question': str(qa['question']).strip(),
                        'answer': str(qa['answer']).strip()
                    })

            print(f"✅ 成功提取 {len(valid_qa_pairs)} 个问答对")
            return valid_qa_pairs

        except json.JSONDecodeError as e:
            print(f"❌ JSON解析失败: {e}")
            print(f"原始响应: {result_text}")
            return []
        except Exception as e:
            print(f"❌ VLM提取问答对失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _extract_question_number(self, text: str) -> Optional[int]:
        """从题干中提取题号"""
        if not text:
            return None

        normalized = text.strip()
        match = self.QUESTION_NUMBER_REGEX.match(normalized)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def _find_missing_numbers(self, qa_pairs: List[Dict]) -> List[int]:
        """根据题号检测缺失的题目"""
        numbers = [self._extract_question_number(qa.get('question', '')) for qa in qa_pairs]
        numbers = sorted(set(filter(None, numbers)))

        if len(numbers) < 3:
            return []

        missing = []
        for n in range(numbers[0], numbers[-1] + 1):
            if n not in numbers:
                missing.append(n)

        if missing:
            print(f"⚠️ 检测到题号缺失: {missing[:10]}{'...' if len(missing) > 10 else ''}")
        return missing

    def _map_missing_numbers_to_segments(
        self,
        missing_numbers: List[int],
        segment_stats: Dict[int, Dict],
        total_segments: int
    ) -> Set[int]:
        """根据题号缺失情况，推测需要重试的片段"""
        if not missing_numbers:
            return set()

        segments_to_retry: Set[int] = set()
        sorted_segments = sorted(segment_stats.items(), key=lambda kv: kv[0])

        for missing in missing_numbers:
            fallback_segment = None
            chosen_segment = None

            for idx, stats in sorted_segments:
                numbers = sorted(stats.get('numbers', []))
                if numbers:
                    if numbers[0] <= missing <= numbers[-1]:
                        chosen_segment = idx
                        break
                    if numbers[-1] < missing:
                        fallback_segment = idx
                else:
                    # 记录最近的空题片段，作为退路
                    fallback_segment = idx if fallback_segment is None else fallback_segment

            if chosen_segment is None:
                chosen_segment = fallback_segment if fallback_segment is not None else 0

            segments_to_retry.add(max(0, min(chosen_segment, total_segments - 1)))

        return segments_to_retry

    def _retry_segments_for_coverage(
        self,
        split_segments: List[Dict],
        existing_pairs: List[Dict]
    ) -> List[Dict]:
        """检测缺题并对疑似片段进行细粒度重试"""
        if not split_segments:
            return existing_pairs

        segment_stats: Dict[int, Dict] = {}
        for idx, segment in enumerate(split_segments):
            segment_stats[idx] = {
                'numbers': [],
                'count': 0,
                'part_index': segment.get('part_index', idx)
            }

        for qa in existing_pairs:
            part_index = qa.get('part_index', 0)
            stat = segment_stats.setdefault(part_index, {'numbers': [], 'count': 0})
            stat['count'] += 1
            number = self._extract_question_number(qa.get('question', ''))
            if number:
                stat.setdefault('numbers', []).append(number)

        missing_numbers = self._find_missing_numbers(existing_pairs)
        segments_to_retry = self._map_missing_numbers_to_segments(
            missing_numbers,
            segment_stats,
            len(split_segments)
        )

        zero_segments = {idx for idx, stat in segment_stats.items() if stat.get('count', 0) == 0}
        segments_to_retry.update(zero_segments)

        if not segments_to_retry:
            return existing_pairs

        ordered_segments = sorted(list(segments_to_retry))[:self.MAX_RETRY_SEGMENTS]
        print(f"🔁 触发细粒度重试片段: {ordered_segments}")

        retry_pairs: List[Dict] = []
        for idx in ordered_segments:
            segment_info = split_segments[idx]
            retry_pairs.extend(self._extract_with_fine_windows(segment_info))

        if not retry_pairs:
            return existing_pairs

        merged = self._merge_qa_pairs(existing_pairs, retry_pairs)
        print(f"✅ 重试后问答对数量: {len(existing_pairs)} → {len(merged)}")
        return merged

    def _extract_with_fine_windows(self, segment_info: Dict) -> List[Dict]:
        """对指定片段进行更小窗口的重新提取"""
        retry_pairs: List[Dict] = []
        segment_path = segment_info.get('path')

        try:
            with Image.open(segment_path) as segment_image:
                width, height = segment_image.size
                start_y = 0
                window_idx = 0

                while start_y < height:
                    end_y = min(start_y + self.RETRY_SPLIT_HEIGHT, height)
                    sub_image = segment_image.crop((0, start_y, width, end_y))

                    # ✅ 使用上下文管理器确保临时文件被清理
                    temp_path = None
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(segment_path).suffix) as temp:
                            sub_image.save(temp.name)
                            temp_path = temp.name

                        qa_pairs = self.extract_qa_pairs_from_image(temp_path)
                        
                        for qa in qa_pairs:
                            qa['source_image'] = segment_path
                            qa['part_index'] = segment_info.get('part_index', 0)
                            segment_base = segment_info.get('start_y', 0)
                            qa['segment_start'] = segment_base + start_y
                            qa['segment_end'] = segment_base + end_y
                            qa['retry'] = True
                        retry_pairs.extend(qa_pairs)
                    finally:
                        # ✅ 确保临时文件被删除，即使出现异常
                        if temp_path and os.path.exists(temp_path):
                            try:
                                os.remove(temp_path)
                            except Exception as e:
                                print(f"⚠️ 删除临时文件失败: {temp_path}, 错误: {e}")

                    if end_y >= height:
                        break

                    start_y = end_y - self.RETRY_OVERLAP
                    window_idx += 1

        except Exception as e:
            print(f"❌ 片段重试失败: {e}")

        return retry_pairs

    def _merge_qa_pairs(self, original: List[Dict], new_pairs: List[Dict]) -> List[Dict]:
        """合并问答对，基于 question+answer 去重"""
        merged: List[Dict] = []
        seen: Set[Tuple[str, str]] = set()

        for qa in original + new_pairs:
            key = (qa.get('question', '').strip(), qa.get('answer', '').strip())
            if key in seen or not key[0]:
                continue
            seen.add(key)
            merged.append(qa)

        return merged

    def _export_kb_snapshot(self, kb_id: int) -> None:
        """生成知识库快照文件，便于后台快速查看"""
        try:
            metadata_files = list(self.metadata_folder.glob('*.json'))
            screenshots = []
            total_qa = 0

            for metadata_file in metadata_files:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                if metadata.get('kb_id') != kb_id:
                    continue

                qa_pairs = metadata.get('qa_pairs', [])
                sample_questions = [qa.get('question', '') for qa in qa_pairs[:5]]
                screenshots.append({
                    'screenshot_id': metadata.get('screenshot_id'),
                    'screenshot_name': metadata.get('screenshot_name'),
                    'qa_count': metadata.get('qa_count', 0),
                    'split_count': metadata.get('split_count', 0),
                    'sample_questions': sample_questions
                })
                total_qa += metadata.get('qa_count', 0)

            snapshot = {
                'kb_id': kb_id,
                'generated_at': datetime.now().isoformat(),
                'total_screenshots': len(screenshots),
                'total_qa_pairs': total_qa,
                'screenshots': screenshots
            }

            snapshot_path = self.metadata_folder / f"kb_{kb_id}_snapshot.json"
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)

            print(f"🗂️ 已生成知识库快照: {snapshot_path}")

        except Exception as e:
            print(f"⚠️ 生成知识库快照失败: {e}")

    def _get_qa_collection(self, kb_id: int):
        """获取知识库的问答向量集合"""
        collection_name = f"kb_{kb_id}_qa"

        try:
            collection = self.chroma_client.get_collection(name=collection_name)
        except:
            # 如果集合不存在，创建一个新的
            collection = self.chroma_client.create_collection(
                name=collection_name,
                metadata={
                    "kb_id": kb_id,
                    "type": "qa_pairs",
                    "created_at": datetime.now().isoformat()
                }
            )

        return collection

    def upload_screenshot(self, kb_id: int, screenshot_path: str, screenshot_name: str, user_id: int = None) -> Dict:
        """
        上传并处理截图，提取问答对并存储

        Args:
            kb_id: 知识库ID
            screenshot_path: 截图文件路径
            screenshot_name: 原始文件名
            user_id: 用户ID（可选）

        Returns:
            处理结果字典
        """
        try:
            # 生成唯一ID
            screenshot_id = str(uuid.uuid4())

            # 保存原始截图
            kb_screenshot_folder = self.screenshots_folder / f"kb_{kb_id}"
            kb_screenshot_folder.mkdir(parents=True, exist_ok=True)

            saved_screenshot_path = kb_screenshot_folder / f"{screenshot_id}{Path(screenshot_name).suffix}"
            import shutil
            shutil.copy2(screenshot_path, saved_screenshot_path)

            print(f"📸 处理截图: {screenshot_name}")

            # 检测并分割长截图
            split_dir = kb_screenshot_folder / f"{screenshot_id}_parts"
            split_images = self.split_long_screenshot(str(saved_screenshot_path), str(split_dir))

            # 从每个图片片段提取问答对
            all_qa_pairs = []
            for idx, segment in enumerate(split_images):
                image_path = segment['path']
                print(f"🔍 分析图片片段 {idx + 1}/{len(split_images)}")
                qa_pairs = self.extract_qa_pairs_from_image(image_path)

                # 为每个问答对添加来源信息
                for qa in qa_pairs:
                    qa['source_image'] = image_path
                    qa['part_index'] = segment.get('part_index', idx)
                    qa['segment_start'] = segment.get('start_y', 0)
                    qa['segment_end'] = segment.get('end_y', 0)
                    all_qa_pairs.append(qa)

            # 缺题检测与重试
            all_qa_pairs = self._retry_segments_for_coverage(
                split_segments=split_images,
                existing_pairs=all_qa_pairs
            )

            if not all_qa_pairs:
                return {
                    'success': False,
                    'error': '未能从截图中提取到问答对，请确保截图包含明确的问题和答案'
                }

            print(f"📊 总共提取到 {len(all_qa_pairs)} 个问答对")

            # 获取问答集合
            collection = self._get_qa_collection(kb_id)

            # 生成嵌入并存储
            print(f"🔄 正在生成嵌入向量...")
            qa_ids = []
            qa_embeddings = []
            qa_documents = []
            qa_metadatas = []

            for idx, qa_pair in enumerate(all_qa_pairs):
                qa_id = f"{screenshot_id}_qa_{idx}"
                qa_ids.append(qa_id)

                # 将问题和答案拼接作为文档内容
                qa_text = f"问题: {qa_pair['question']}\n答案: {qa_pair['answer']}"
                qa_documents.append(qa_text)

                embedding = self._embed_text(qa_text)
                qa_embeddings.append(embedding)

                # 元数据
                qa_metadatas.append({
                    'screenshot_id': screenshot_id,
                    'screenshot_name': screenshot_name,
                    'screenshot_path': str(saved_screenshot_path),
                    'qa_index': idx,
                    'question': qa_pair['question'],
                    'answer': qa_pair['answer'],
                    'source_image': qa_pair.get('source_image', ''),
                    'part_index': qa_pair.get('part_index', 0),
                    'uploaded_at': datetime.now().isoformat()
                })

            # 添加到向量数据库
            collection.add(
                ids=qa_ids,
                embeddings=qa_embeddings,
                documents=qa_documents,
                metadatas=qa_metadatas
            )
            print(f"✅ 问答对存储完成")

            # 保存截图元数据
            metadata = {
                'screenshot_id': screenshot_id,
                'screenshot_name': screenshot_name,
                'screenshot_path': str(saved_screenshot_path),
                'split_count': len(split_images),
                'qa_count': len(all_qa_pairs),
                'file_size': os.path.getsize(saved_screenshot_path),
                'uploaded_at': datetime.now().isoformat(),
                'kb_id': kb_id,
                'user_id': user_id,
                'qa_pairs': all_qa_pairs  # 保存完整的问答对
            }

            metadata_file = self.metadata_folder / f"{screenshot_id}.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            # 输出知识库快照，便于后台查看
            self._export_kb_snapshot(kb_id)

            return {
                'success': True,
                'screenshot_id': screenshot_id,
                'screenshot_name': screenshot_name,
                'split_count': len(split_images),
                'qa_count': len(all_qa_pairs),
                'qa_pairs': all_qa_pairs,
                'message': f'截图处理成功，提取到 {len(all_qa_pairs)} 个问答对'
            }

        except Exception as e:
            print(f"❌ 截图处理失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': f'截图处理失败: {str(e)}'
            }

    def _calculate_keyword_score(self, query: str, text: str) -> float:
        """
        计算关键字匹配分数（支持中文分词）

        Args:
            query: 查询文本
            text: 待匹配文本

        Returns:
            关键字匹配分数 (0-1)
        """
        # 简单的中文分词（按字符和词组）
        query_lower = query.lower()
        text_lower = text.lower()

        # 完全匹配
        if query_lower in text_lower:
            return 1.0

        # 计算关键词重叠
        # 提取2-4字的词组
        query_words = set()
        for length in range(2, min(5, len(query) + 1)):
            for i in range(len(query) - length + 1):
                query_words.add(query[i:i+length])

        # 单字也加入
        query_words.update(query)

        # 计算匹配的词数
        matched = sum(1 for word in query_words if word in text_lower and len(word) > 1)

        if not query_words:
            return 0.0

        return matched / len(query_words)

    def search_qa(self, kb_id: int, question: str, top_k: int = 5, use_hybrid: bool = True) -> List[Dict]:
        """
        在问答库中搜索相似问题（支持混合检索：向量相似度 + 关键字匹配）

        Args:
            kb_id: 知识库ID
            question: 用户问题
            top_k: 返回前k个最相关的结果
            use_hybrid: 是否使用混合检索（向量+关键字）

        Returns:
            相关问答对列表
        """
        try:
            # 获取问答集合
            collection = self._get_qa_collection(kb_id)

            # 检查集合中是否有数据
            collection_count = collection.count()
            if collection_count == 0:
                print(f"⚠️ 问答库 {kb_id} 中没有数据")
                return []

            print(f"🔍 搜索问题: {question}")
            print(f"📊 问答库中共有 {collection_count} 个问答对")
            print(f"🔧 检索模式: {'混合检索（向量+关键字）' if use_hybrid else '纯向量检索'}")

            query_embedding = self._embed_text(question)

            # 搜索相似问题（获取更多候选，用于关键字重排）
            n_results = min(top_k * 3 if use_hybrid else top_k, collection_count)
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

                    # 计算向量相似度
                    if distance is not None and distance >= 0:
                        vector_similarity = 1 / (1 + distance)
                    else:
                        vector_similarity = 0

                    # 计算关键字匹配分数
                    keyword_score = 0.0
                    if use_hybrid:
                        question_text = metadata.get('question', '')
                        answer_text = metadata.get('answer', '')
                        # 关键字在问题中的匹配权重更高
                        keyword_score = (
                            self._calculate_keyword_score(question, question_text) * 0.7 +
                            self._calculate_keyword_score(question, answer_text) * 0.3
                        )

                    # 混合得分：向量相似度60% + 关键字匹配40%
                    if use_hybrid:
                        final_similarity = vector_similarity * 0.6 + keyword_score * 0.4
                    else:
                        final_similarity = vector_similarity

                    print(f"  📄 结果 {idx + 1}: 向量={vector_similarity:.4f}, 关键字={keyword_score:.4f}, 综合={final_similarity:.4f}")
                    print(f"     问题: {metadata.get('question', '')[:60]}...")

                    search_results.append({
                        'question': metadata.get('question', ''),
                        'answer': metadata.get('answer', ''),
                        'metadata': metadata,
                        'distance': distance,
                        'vector_similarity': vector_similarity,
                        'keyword_score': keyword_score,
                        'similarity': final_similarity  # 最终综合相似度
                    })

                # 按综合相似度排序
                search_results.sort(key=lambda x: x['similarity'], reverse=True)

                # 只返回top_k个结果
                search_results = search_results[:top_k]

                print(f"✅ 找到 {len(search_results)} 个相关问答对")
                return search_results
            else:
                print(f"⚠️ 未找到任何搜索结果")
                return []

        except Exception as e:
            print(f"❌ 问答搜索失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    def answer_from_qa(self, kb_id: int, question: str, top_k: int = 3, similarity_threshold: float = 0.5) -> Dict:
        """
        从问答库中查找答案（返回前3个候选答案）

        Args:
            kb_id: 知识库ID
            question: 用户问题
            top_k: 返回前k个候选答案（默认3个）
            similarity_threshold: 相似度阈值（低于此值认为不相关）

        Returns:
            答案结果字典，包含前3个候选答案
        """
        # 搜索相关问答（使用混合检索）
        search_results = self.search_qa(kb_id, question, top_k=top_k, use_hybrid=True)

        if not search_results:
            return {
                'success': True,
                'found': False,
                'answer': '未找到相关问答，请检查您的问答库中是否有类似问题。',
                'candidates': []
            }

        # 获取最相似的问答对
        best_match = search_results[0]

        # 准备候选答案列表（前3个）
        candidates = []
        for idx, result in enumerate(search_results):
            candidates.append({
                'rank': idx + 1,
                'question': result['question'],
                'answer': result['answer'],
                'similarity': result['similarity'],
                'vector_similarity': result.get('vector_similarity', 0),
                'keyword_score': result.get('keyword_score', 0)
            })

        # 判断最佳匹配的相似度是否足够高
        if best_match['similarity'] < similarity_threshold:
            # 相似度不够，但仍然返回候选答案供用户参考
            return {
                'success': True,
                'found': False,
                'answer': f'未找到足够相似的问题（最高相似度: {best_match["similarity"]:.1%}）。\n\n以下是可能相关的问题供您参考：',
                'candidates': candidates,
                'best_similarity': best_match['similarity']
            }

        # 相似度足够，返回最佳答案 + 其他候选
        return {
            'success': True,
            'found': True,
            'answer': best_match['answer'],
            'matched_question': best_match['question'],
            'similarity': best_match['similarity'],
            'candidates': candidates  # 包含所有候选（含最佳答案）
        }

    def list_screenshots(self, kb_id: int) -> List[Dict]:
        """列出知识库中的所有截图"""
        try:
            metadata_files = list(self.metadata_folder.glob('*.json'))
            screenshots = []

            for metadata_file in metadata_files:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                if metadata.get('kb_id') == kb_id:
                    screenshots.append(metadata)

            # 按上传时间排序
            screenshots.sort(key=lambda x: x.get('uploaded_at', ''), reverse=True)

            return screenshots

        except Exception as e:
            print(f"❌ 获取截图列表失败: {e}")
            return []

    def delete_screenshot(self, kb_id: int, screenshot_id: str) -> Dict:
        """删除截图及其相关问答对"""
        try:
            # 读取截图元数据
            metadata_file = self.metadata_folder / f"{screenshot_id}.json"
            if not metadata_file.exists():
                return {'success': False, 'error': '截图不存在'}

            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            # 验证所有权
            if metadata.get('kb_id') != kb_id:
                return {'success': False, 'error': '无权删除此截图'}

            # 从向量数据库中删除相关问答对
            collection = self._get_qa_collection(kb_id)

            # 获取所有相关的问答ID
            results = collection.get(where={'screenshot_id': screenshot_id})
            if results['ids']:
                collection.delete(ids=results['ids'])

            # 删除截图文件
            screenshot_path = metadata.get('screenshot_path')
            if screenshot_path and os.path.exists(screenshot_path):
                os.remove(screenshot_path)

            # 删除分割图片目录
            split_dir = Path(screenshot_path).parent / f"{screenshot_id}_parts"
            if split_dir.exists():
                import shutil
                shutil.rmtree(split_dir)

            # 删除元数据文件
            metadata_file.unlink()

            return {'success': True, 'message': '截图删除成功'}

        except Exception as e:
            print(f"❌ 删除截图失败: {e}")
            return {'success': False, 'error': f'删除失败: {str(e)}'}

    def get_qa_stats(self, kb_id: int) -> Dict:
        """获取问答库统计信息"""
        try:
            collection = self._get_qa_collection(kb_id)
            count = collection.count()

            # 统计截图数量
            screenshots = self.list_screenshots(kb_id)

            return {
                'total_qa_pairs': count,
                'total_screenshots': len(screenshots),
                'kb_id': kb_id
            }
        except Exception as e:
            print(f"❌ 获取统计信息失败: {e}")
            return {
                'total_qa_pairs': 0,
                'total_screenshots': 0,
                'kb_id': kb_id
            }
