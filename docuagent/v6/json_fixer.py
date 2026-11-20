"""
JSON修复器 - 修复LLM返回的不规范JSON
"""

import json
import re
from typing import Any, Dict, List, Optional


class JSONFixer:
    """修复LLM返回的JSON格式问题"""

    @staticmethod
    def fix_json_string(json_str: str) -> str:
        """
        修复常见的JSON格式问题

        Args:
            json_str: 可能有问题的JSON字符串

        Returns:
            修复后的JSON字符串
        """
        # 去除可能的markdown代码块标记
        json_str = re.sub(r'^```json\s*', '', json_str, flags=re.MULTILINE)
        json_str = re.sub(r'^```\s*$', '', json_str, flags=re.MULTILINE)
        json_str = json_str.strip()

        # 修复常见的引号问题
        # 1. 单引号改为双引号 (但保留字符串内的单引号)
        # 简化处理: 只在键值对的键和简单值中替换
        json_str = re.sub(r"'([^']*)'(\s*:)", r'"\1"\2', json_str)  # 键
        json_str = re.sub(r":\s*'([^']*)'", r': "\1"', json_str)  # 简单字符串值

        # 2. 修复尾部逗号
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

        # 3. 修复缺失的逗号 (在}或]后面应该有逗号的地方)
        json_str = re.sub(r'([}\]])(\s*)([{"\[])', r'\1,\2\3', json_str)

        # 4. 修复未转义的换行符
        json_str = json_str.replace('\n', '\\n')

        return json_str

    @staticmethod
    def parse_json_with_fix(json_str: str, max_attempts: int = 3) -> Optional[Dict]:
        """
        尝试解析JSON,失败时自动修复

        Args:
            json_str: JSON字符串
            max_attempts: 最大尝试次数

        Returns:
            解析后的字典,失败返回None
        """
        # 第一次尝试: 直接解析
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 第二次尝试: 修复后解析
        for attempt in range(max_attempts):
            try:
                fixed_json = JSONFixer.fix_json_string(json_str)
                return json.loads(fixed_json)
            except json.JSONDecodeError as e:
                if attempt == max_attempts - 1:
                    print(f"JSON解析失败 (尝试{attempt+1}次): {e}")
                    print(f"问题位置: {json_str[max(0, e.pos-50):e.pos+50]}")
                    return None
                # 进一步修复
                json_str = fixed_json

        return None

    @staticmethod
    def extract_json_from_text(text: str) -> Optional[str]:
        """
        从文本中提取JSON部分

        Args:
            text: 可能包含JSON的文本

        Returns:
            提取的JSON字符串,失败返回None
        """
        # 尝试找到JSON对象或数组
        # 1. 查找被```json包裹的内容
        match = re.search(r'```json\s*(\{.*?\}|\[.*?\])\s*```', text, re.DOTALL)
        if match:
            return match.group(1)

        # 2. 查找第一个完整的JSON对象
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return match.group(0)

        # 3. 查找第一个完整的JSON数组
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            return match.group(0)

        return None

    @staticmethod
    def parse_llm_response(response: str) -> Optional[Dict]:
        """
        解析LLM返回的响应,自动处理各种格式问题

        Args:
            response: LLM返回的原始响应

        Returns:
            解析后的字典,失败返回None
        """
        # 1. 提取JSON部分
        json_str = JSONFixer.extract_json_from_text(response)
        if not json_str:
            print("未找到JSON内容")
            return None

        # 2. 解析JSON
        result = JSONFixer.parse_json_with_fix(json_str)

        return result

    @staticmethod
    def fix_annotations(annotations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        清洗并去重标注结果，确保后续内容生成阶段输入稳定。
        """
        if not isinstance(annotations, list):
            return []

        cleaned: List[Dict[str, Any]] = []
        seen_keys = set()

        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue

            placeholder = annotation.get("placeholder", "")
            if isinstance(placeholder, str):
                placeholder = placeholder.strip()
            else:
                placeholder = ""

            placeholders = annotation.get("placeholders", [])
            if isinstance(placeholders, list):
                cleaned_placeholders = []
                for ph in placeholders:
                    if isinstance(ph, str):
                        ph = ph.strip()
                        if ph:
                            cleaned_placeholders.append(ph)
                placeholders = cleaned_placeholders
            else:
                placeholders = []

            result_text = annotation.get("result", "")
            if isinstance(result_text, str):
                result_text = result_text.strip()
            else:
                result_text = ""

            key = (
                annotation.get("location_type"),
                annotation.get("block_id"),
                annotation.get("cell_marker"),
                placeholder,
                tuple(placeholders),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)

            cleaned.append({
                **annotation,
                "placeholder": placeholder,
                "placeholders": placeholders,
                "result": result_text,
            })

        return cleaned


# 便捷函数
def fix_and_parse_json(json_str: str) -> Optional[Dict]:
    """快捷方法: 修复并解析JSON"""
    return JSONFixer.parse_json_with_fix(json_str)


def parse_llm_json(response: str) -> Optional[Dict]:
    """快捷方法: 解析LLM响应中的JSON"""
    return JSONFixer.parse_llm_response(response)
