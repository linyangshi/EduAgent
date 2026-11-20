"""JSON parsing utilities"""

import json
import re
from typing import Dict, Any, Union, List
from config import DEFAULT_TEMPLATE_STRUCTURE


def fix_json_string(json_str: str) -> str:
    """
    修复JSON字符串中的常见问题：
    1. 未终止的字符串
    2. 未转义的特殊字符
    3. 控制字符
    """
    try:
        # 方法1: 修复字符串中的换行符和特殊字符
        result = []
        in_string = False
        escape_next = False
        i = 0
        
        while i < len(json_str):
            char = json_str[i]
            
            if escape_next:
                # 已经遇到了反斜杠，现在处理转义字符
                if char in ['n', 'r', 't', '\\', '"', '/', 'u']:
                    # 标准转义序列，保留
                    result.append('\\' + char)
                elif char == '\n':
                    # 实际换行符，转换为\n
                    result.append('\\n')
                elif char == '\r':
                    result.append('\\r')
                elif char == '\t':
                    result.append('\\t')
                else:
                    # 其他字符，可能需要转义
                    result.append('\\' + char)
                escape_next = False
                i += 1
                continue
            
            if char == '\\':
                # 遇到反斜杠，标记下一个字符需要转义
                result.append(char)
                escape_next = True
                i += 1
                continue
            
            if char == '"':
                in_string = not in_string
                result.append(char)
                i += 1
                continue
            
            if in_string:
                # 在字符串内，需要转义特殊字符
                if char == '\n':
                    result.append('\\n')
                elif char == '\r':
                    result.append('\\r')
                elif char == '\t':
                    result.append('\\t')
                elif ord(char) < 32:  # 控制字符
                    result.append(f'\\u{ord(char):04x}')
                elif char in ['\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',
                             '\x08', '\x0b', '\x0c', '\x0e', '\x0f']:
                    result.append(f'\\u{ord(char):04x}')
                else:
                    result.append(char)
            else:
                result.append(char)
            
            i += 1
        
        return ''.join(result)
    except Exception as e:
        print(f"⚠️ JSON修复过程出错: {e}")
        return json_str


def fix_missing_commas(json_str: str) -> str:
    """
    修复缺失的逗号分隔符
    使用更精确的规则：只在明确的缺失位置添加逗号
    """
    # 使用正则表达式模式修复常见的缺失逗号情况
    patterns_fixes = [
        # 模式1: }"key": -> }, "key":
        (r'}\s*"([a-zA-Z_][a-zA-Z0-9_]*)":', r'}, "\1":'),
        # 模式2: ]"key": -> ], "key":
        (r']\s*"([a-zA-Z_][a-zA-Z0-9_]*)":', r'], "\1":'),
        # 模式3: true"key": -> true, "key":
        (r'(true|false|null)\s*"([a-zA-Z_][a-zA-Z0-9_]*)":', r'\1, "\2":'),
        # 模式4: "value" "key": -> "value", "key":
        (r'"([^"]+)"\s*"([a-zA-Z_][a-zA-Z0-9_]*)":', r'"\1", "\2":'),
        # 模式5: 数字后跟引号开头（可能是键或值）
        (r'(\d+)\s*"([a-zA-Z_][a-zA-Z0-9_]*)":', r'\1, "\2":'),
        # 模式6: }后面直接跟引号（可能是新属性）
        (r'}\s+"([^"]+)":', r'}, "\1":'),
        # 模式7: ]后面直接跟引号
        (r']\s+"([^"]+)":', r'], "\1":'),
    ]
    
    fixed = json_str
    for pattern, replacement in patterns_fixes:
        try:
            # 确保不会在字符串内部替换
            def replace_outside_strings(match):
                text = match.group(0)
                # 简单检查：如果匹配位置前后有奇数的引号，可能在字符串内
                start = match.start()
                before = fixed[:start]
                # 计算前面未转义的引号数量
                quote_count = 0
                i = 0
                while i < len(before):
                    if before[i] == '"' and (i == 0 or before[i-1] != '\\'):
                        quote_count += 1
                    i += 1
                
                # 如果前面有奇数个引号，说明在字符串内，不替换
                if quote_count % 2 == 1:
                    return text
                
                # 执行替换
                if match.lastindex >= 2:
                    return replacement.replace(r'\1', match.group(1)).replace(r'\2', match.group(2))
                elif match.lastindex >= 1:
                    return replacement.replace(r'\1', match.group(1))
                else:
                    return replacement
            
            # 应用替换
            fixed = re.sub(pattern, replace_outside_strings, fixed)
        except Exception as e:
            # 如果复杂替换失败，尝试简单替换
            try:
                fixed = re.sub(pattern, replacement, fixed)
            except:
                pass
    
    return fixed


def fix_json_syntax_errors(json_str: str, error_msg: str = None) -> str:
    """
    根据错误信息修复JSON语法错误
    """
    fixed = json_str
    
    # 总是尝试修复缺失逗号（这是最常见的错误）
    fixed = fix_missing_commas(fixed)
    
    # 如果错误信息包含 "Expecting ',' delimiter" 或其他期望错误，进行额外修复
    if error_msg and ("Expecting" in str(error_msg)):
        # 模式1: "value1" "key2" -> "value1", "key2" (在两个字符串值之间)
        # 但要小心，不要破坏已有的结构
        fixed = re.sub(r'"([^"]+)"\s+"([a-zA-Z_][a-zA-Z0-9_]*)":', r'"\1", "\2":', fixed)
        
        # 模式2: 在值后面直接跟引号（但不在键值对中）
        # 这个需要更谨慎，只在明确的位置修复
    
    return fixed


def try_fix_and_parse(json_str: str, max_attempts: int = 3) -> Dict:
    """
    尝试修复并解析JSON，多种策略
    """
    last_error = None
    
    # 尝试1: 直接解析
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        last_error = e
    
    # 尝试2: 修复字符串转义后解析
    try:
        fixed = fix_json_string(json_str)
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        last_error = e
    
    # 尝试2.5: 根据错误信息修复语法错误
    if last_error:
        try:
            fixed = fix_json_syntax_errors(json_str, str(last_error))
            fixed = fix_json_string(fixed)
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
    
    # 尝试3: 查找第一个完整的JSON对象（使用括号计数）
    try:
        start_idx = json_str.find('{')
        if start_idx != -1:
            brace_count = 0
            in_string = False
            escape_next = False
            
            for i in range(start_idx, len(json_str)):
                char = json_str[i]
                
                if escape_next:
                    escape_next = False
                    continue
                
                if char == '\\':
                    escape_next = True
                    continue
                
                if char == '"':
                    in_string = not in_string
                    continue
                
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            # 找到完整的JSON对象
                            json_obj_str = json_str[start_idx:i+1]
                            # 先尝试语法修复
                            try:
                                fixed = fix_json_syntax_errors(json_obj_str, str(last_error) if last_error else None)
                                fixed = fix_json_string(fixed)
                                return json.loads(fixed)
                            except:
                                # 如果语法修复失败，尝试只修复字符串转义
                                fixed = fix_json_string(json_obj_str)
                                return json.loads(fixed)
    except Exception as e:
        print(f"⚠️ 尝试3失败: {e}")
        pass
    
    # 尝试4: 尝试修复未终止的字符串（在末尾添加引号）
    try:
        # 统计引号数量，如果奇数则可能未终止
        quote_count = json_str.count('"') - json_str.count('\\"')
        if quote_count % 2 == 1:
            # 查找最后一个未转义的引号
            last_quote_pos = -1
            for i in range(len(json_str) - 1, -1, -1):
                if json_str[i] == '"' and (i == 0 or json_str[i-1] != '\\'):
                    last_quote_pos = i
                    break
            
            if last_quote_pos != -1:
                # 在字符串末尾尝试添加引号和闭合括号
                test_str = json_str[:last_quote_pos + 1]
                # 尝试补齐括号
                open_braces = test_str.count('{') - test_str.count('}')
                test_str += '}' * open_braces
                fixed = fix_json_string(test_str)
                return json.loads(fixed)
    except Exception as e:
        print(f"⚠️ 尝试4失败: {e}")
        pass
    
    # 尝试5: 尝试从最后一个完整可解析的部分开始修复
    # 适用于被截断的JSON（如"学 Palestin"这种乱码结尾）
    try:
        # 尝试找到最后一个可能的字符串末尾
        # 从末尾向前查找，寻找可能合理的截断点
        for end_pos in range(len(json_str) - 1, max(len(json_str) - 500, 0), -1):
            test_str = json_str[:end_pos]
            
            # 补齐可能的未闭合括号
            open_braces = test_str.count('{') - test_str.count('}')
            open_brackets = test_str.count('[') - test_str.count(']')
            
            # 检查是否在字符串中间
            quote_count = test_str.count('"') - test_str.count('\\"')
            if quote_count % 2 == 1:
                # 仍在字符串中，尝试添加引号
                test_str += '"'
            
            # 补齐括号
            test_str += '}' * open_braces
            test_str += ']' * open_brackets
            
            # 尝试解析
            fixed = fix_json_string(test_str)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                continue
        
    except Exception as e:
        print(f"⚠️ 尝试5失败: {e}")
        pass
    
    raise json.JSONDecodeError("无法修复JSON", json_str, 0)


def extract_json_from_response(response_content: Union[str, List, Dict]) -> Dict:
    """Extract JSON from LLM response content"""
    try:
        # Handle different response formats
        if isinstance(response_content, list):
            text_content = ""
            for item in response_content:
                if isinstance(item, dict) and 'text' in item:
                    text_content += item['text']
                elif isinstance(item, str):
                    text_content += item
        elif isinstance(response_content, str):
            text_content = response_content
        else:
            print(f"Unknown response format: {type(response_content)}")
            return DEFAULT_TEMPLATE_STRUCTURE
        
        # Method 1: Extract JSON from markdown code blocks (multiple patterns)
        # 使用贪婪匹配来获取完整的JSON（包括可能的未终止部分）
        json_patterns = [
            r'```json\s*\n(.*?)\n```',  # ```json ... ```
            r'```\s*\n(.*?)\n```',      # ``` ... ```
            r'```json\s*(.*?)\s*```',    # ```json ... ``` (允许首尾空白)
            r'```json(.*?)```',          # ```json...``` (no newlines)
            r'```(.*?)```',              # ```...``` (no newlines)
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text_content, re.DOTALL | re.IGNORECASE)
            if matches:
                for match in matches:
                    try:
                        cleaned = match.strip()
                        # 尝试使用修复函数解析
                        return try_fix_and_parse(cleaned)
                    except json.JSONDecodeError as e:
                        print(f"⚠️ JSON decode failed for pattern {pattern}: {e}")
                        continue
        
        # Method 1.5: Try to extract incomplete JSON from truncated markdown blocks
        # 处理被截断的JSON代码块（没有完整的```结束标记）
        incomplete_patterns = [
            r'```json\s*\n(.*)',         # ```json ... (incomplete)
            r'```\s*\n(.*)',             # ``` ... (incomplete)
            r'```json\s*(.*)',           # ```json... (incomplete)
            r'```(.*)',                  # ```... (incomplete)
        ]
        
        for pattern in incomplete_patterns:
            match = re.search(pattern, text_content, re.DOTALL | re.IGNORECASE)
            if match:
                extracted = match.group(1).strip()
                try:
                    return try_fix_and_parse(extracted)
                except json.JSONDecodeError as e:
                    print(f"⚠️ Incomplete JSON decode failed for pattern {pattern}: {e}")
                    continue
        
        # Method 2: Find complete JSON objects (supports nesting, respects strings)
        start_idx = text_content.find('{')
        if start_idx != -1:
            brace_count = 0
            in_string = False
            escape_next = False
            
            for i in range(start_idx, len(text_content)):
                char = text_content[i]
                
                if escape_next:
                    escape_next = False
                    continue
                
                if char == '\\':
                    escape_next = True
                    continue
                
                if char == '"':
                    in_string = not in_string
                    continue
                
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            try:
                                json_str = text_content[start_idx:i+1]
                                return try_fix_and_parse(json_str)
                            except json.JSONDecodeError as e:
                                print(f"⚠️ Method 2 failed: {e}")
                                break
        
        # Method 3: Clean and try direct parsing with fixes
        try:
            # Remove common prefixes and suffixes
            cleaned_content = text_content.strip()
            
            # Remove common markdown artifacts
            if cleaned_content.lower().startswith('json'):
                cleaned_content = cleaned_content[4:].strip()
            if cleaned_content.startswith('```'):
                # 移除开头的 ```json 或 ```
                cleaned_content = re.sub(r'^```\s*json\s*\n?', '', cleaned_content, flags=re.IGNORECASE)
                cleaned_content = re.sub(r'^```\s*\n?', '', cleaned_content)
            if cleaned_content.endswith('```'):
                cleaned_content = cleaned_content[:-3].strip()
            
            # Try parsing with fixes
            return try_fix_and_parse(cleaned_content)
        except json.JSONDecodeError as e:
            print(f"⚠️ Direct JSON parsing failed: {e}")
            pass
        
        # Method 4: Try to find JSON array (respects strings)
        array_start = text_content.find('[')
        if array_start != -1:
            bracket_count = 0
            in_string = False
            escape_next = False
            
            for i in range(array_start, len(text_content)):
                char = text_content[i]
                
                if escape_next:
                    escape_next = False
                    continue
                
                if char == '\\':
                    escape_next = True
                    continue
                
                if char == '"':
                    in_string = not in_string
                    continue
                
                if not in_string:
                    if char == '[':
                        bracket_count += 1
                    elif char == ']':
                        bracket_count -= 1
                        if bracket_count == 0:
                            try:
                                json_str = text_content[array_start:i+1]
                                result = try_fix_and_parse(json_str)
                                # Wrap array in object if needed
                                if isinstance(result, list):
                                    return {"data": result}
                                return result
                            except json.JSONDecodeError as e:
                                print(f"⚠️ Method 4 failed: {e}")
                                break
        
        # If all methods fail, return default template
        print("=" * 80)
        print(f"❌ Cannot extract valid JSON from response, using default template")
        print(f"📝 Response type: {type(text_content)}")
        print(f"📏 Response length: {len(text_content)}")
        print(f"🔍 First 1000 characters of response:")
        print(text_content[:1000])
        print("=" * 80)
        
        # 保存完整响应用于调试
        try:
            with open("failed_json_response.txt", "w", encoding="utf-8") as f:
                f.write(text_content)
            print("💾 完整响应已保存到 failed_json_response.txt")
        except:
            pass
            
        return DEFAULT_TEMPLATE_STRUCTURE
        
    except Exception as e:
        print(f"JSON extraction error: {e}")
        return DEFAULT_TEMPLATE_STRUCTURE

def fix_and_extract_json(content_text):
    """
    修复并提取JSON - 处理LaTeX公式和代码块中的特殊字符
    """
    pattern = r'```json\s*(.*?)\s*```'
    matches = re.findall(pattern, content_text, re.DOTALL)
    
    valid_jsons = []
    
    for i, match in enumerate(matches):
        json_text = match.strip()
        
        try:
            # 关键修复步骤
            
            # 1. 修复LaTeX公式中的反斜杠（在双引号内的反斜杠需要转义）
            # 将 $ ... \command ... $ 中的单反斜杠改为双反斜杠
            def fix_latex(m):
                content = m.group(0)
                # 替换公式内的 \ 为 \\
                return content.replace('\\', '\\\\')
            
            json_text = re.sub(r'\$[^$]+\$', fix_latex, json_text)
            
            # 2. 修复代码块中的实际换行符
            # 找到包含代码的字符串值，将真实换行替换为 \n
            def fix_code_newlines(text):
                # 在字符串值内部查找并替换换行符
                in_string = False
                escape_next = False
                result = []
                
                for char in text:
                    if escape_next:
                        result.append(char)
                        escape_next = False
                        continue
                    
                    if char == '\\':
                        escape_next = True
                        result.append(char)
                        continue
                    
                    if char == '"':
                        in_string = not in_string
                        result.append(char)
                        continue
                    
                    if in_string:
                        if char == '\n':
                            result.append('\\n')
                        elif char == '\r':
                            result.append('\\r')
                        elif char == '\t':
                            result.append('\\t')
                        elif ord(char) < 32:  # 其他控制字符
                            result.append(f'\\u{ord(char):04x}')
                        else:
                            result.append(char)
                    else:
                        result.append(char)
                
                return ''.join(result)
            
            json_text = fix_code_newlines(json_text)
            
            # 3. 尝试解析
            json_obj = json.loads(json_text)
            valid_jsons.append(json_obj)
            print(f"JSON {i+1} 提取成功")
            
        except json.JSONDecodeError as e:
            print(f"JSON {i+1} 解析失败: {e}")
            print(f"错误位置: {json_text[max(0, e.pos-100):e.pos+100]}")
    
    return valid_jsons

