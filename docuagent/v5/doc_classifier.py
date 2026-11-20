"""
文档类型分类器

功能：
1. 使用LLM分析文档内容，判断文档类型
2. 支持的类型：教案、任务书、论文、报告等
3. 返回文档类型和置信度
"""

import os
from pathlib import Path
from typing import Dict, Literal, Optional

try:
    import dashscope
    from dashscope import Generation
    from config.settings import DASHSCOPE_API_KEY
    dashscope.api_key = DASHSCOPE_API_KEY
    HAS_DASHSCOPE = True
except ImportError:
    HAS_DASHSCOPE = False

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


# 支持的文档类型
DocumentType = Literal["lesson_plan", "task_proposal", "thesis", "report", "other"]

# 文档类型中文名称映射
DOC_TYPE_NAMES = {
    "lesson_plan": "教案",
    "task_proposal": "任务书",
    "thesis": "论文",
    "report": "报告",
    "other": "其他"
}


def _call_classifier_llm(prompt: str, model: str = "qwen-plus") -> str:
    """
    调用LLM进行文档分类

    Args:
        prompt: 分类提示词
        model: 使用的模型

    Returns:
        LLM响应文本
    """
    # 优先使用通义千问
    if HAS_DASHSCOPE:
        try:
            response = Generation.call(
                model=model,
                prompt=prompt,
                temperature=0.1,  # 低温度，保证分类稳定
                result_format='message',
                max_tokens=500,
            )

            if response.status_code == 200:
                return response.output.choices[0].message.content or ""
            else:
                raise RuntimeError(f"通义千问API调用失败: {response.message}")
        except Exception as e:
            print(f"⚠️  通义千问调用失败: {e}")
            if not HAS_OPENAI or not os.getenv("KIMI_API_KEY"):
                raise RuntimeError(f"通义千问调用失败且无备选方案: {e}")

    # 备选：使用Kimi
    if HAS_OPENAI:
        kimi_key = os.getenv("KIMI_API_KEY")
        if not kimi_key:
            raise RuntimeError("KIMI_API_KEY未设置")

        client = OpenAI(
            api_key=kimi_key,
            base_url=os.getenv("KIMI_API_BASE", "https://api.moonshot.cn/v1")
        )

        try:
            response = client.chat.completions.create(
                model="kimi-k2-turbo-preview",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的文档分类专家。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=500,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(f"Kimi API调用失败: {e}")

    raise RuntimeError("没有可用的LLM API")


def _build_classification_prompt(content_preview: str, filename: str = "") -> str:
    """
    构建文档分类提示词

    Args:
        content_preview: 文档内容预览（前1000字符）
        filename: 文件名（可选，辅助判断）

    Returns:
        格式化的分类提示词
    """
    prompt = f"""# 文档类型分类任务

请分析以下文档内容，判断它属于哪种类型的文档。

## 文档信息
文件名：{filename if filename else "未知"}

文档内容预览（前1000字符）：
```
{content_preview}
```

## 支持的文档类型

1. **lesson_plan（教案）**
   - 特征：包含教学目标、教学内容、教学活动、教学方法、学生活动等
   - 关键词：课程名称、授课章节、教学目标、教学重难点、教学过程、课后作业
   - 结构：通常有教师活动、学生活动、设计意图等栏目

2. **task_proposal（任务书/课题申请书）**
   - 特征：项目/课题申报类文档
   - 关键词：课题名称、研究目标、研究内容、研究方法、预期成果、任务分工
   - 结构：通常包含课题简介、研究背景、研究方案、时间安排等

3. **thesis（论文/学位论文）**
   - 特征：学术研究论文
   - 关键词：摘要、关键词、引言、文献综述、研究方法、实验结果、结论、参考文献
   - 结构：标准学术论文格式

4. **report（报告/总结）**
   - 特征：工作报告、项目总结、调研报告等
   - 关键词：项目背景、工作内容、完成情况、存在问题、改进建议
   - 结构：总结性文档

5. **other（其他）**
   - 不符合以上任何类型的文档

## 输出格式

请只输出以下JSON格式（不要包含任何额外说明）：

```json
{{
  "type": "lesson_plan|task_proposal|thesis|report|other",
  "confidence": 0.95,
  "reason": "判断理由（1-2句话）"
}}
```

请立即输出分类结果："""

    return prompt


def classify_document(
    content: str,
    filename: str = "",
    content_max_length: int = 1000
) -> Dict[str, any]:
    """
    分类文档类型

    Args:
        content: 文档内容（Markdown格式）
        filename: 文件名（可选）
        content_max_length: 用于分析的最大内容长度

    Returns:
        分类结果:
        {
            "type": "lesson_plan",
            "type_name": "教案",
            "confidence": 0.95,
            "reason": "判断理由"
        }
    """
    # 提取内容预览
    content_preview = content[:content_max_length]

    print(f"📋 开始文档分类...")
    print(f"   文件名: {filename}")
    print(f"   内容长度: {len(content)} 字符")

    # 构建提示词
    prompt = _build_classification_prompt(content_preview, filename)

    # 调用LLM分类
    try:
        response = _call_classifier_llm(prompt)
        print(f"   LLM响应: {response[:200]}...")

        # 解析JSON响应
        import json
        import re

        # 移除markdown代码块标记
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        # 尝试提取JSON
        try:
            result = json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取花括号内容
            match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if match:
                result = json.loads(match.group(0))
            else:
                raise ValueError("无法解析LLM响应")

        doc_type = result.get("type", "other")
        confidence = result.get("confidence", 0.5)
        reason = result.get("reason", "")

        # 验证类型
        if doc_type not in DOC_TYPE_NAMES:
            print(f"   ⚠️  未知类型 '{doc_type}'，归类为 'other'")
            doc_type = "other"

        type_name = DOC_TYPE_NAMES[doc_type]

        print(f"   ✅ 分类结果: {type_name} ({doc_type})")
        print(f"   置信度: {confidence:.2%}")
        print(f"   理由: {reason}")

        return {
            "type": doc_type,
            "type_name": type_name,
            "confidence": confidence,
            "reason": reason
        }

    except Exception as e:
        print(f"   ❌ 文档分类失败: {e}")
        # 返回默认分类
        return {
            "type": "other",
            "type_name": "其他",
            "confidence": 0.0,
            "reason": f"分类失败: {str(e)}"
        }


def classify_from_markdown_file(md_path: Path) -> Dict[str, any]:
    """
    从Markdown文件分类文档类型

    Args:
        md_path: Markdown文件路径

    Returns:
        分类结果
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    return classify_document(
        content=content,
        filename=md_path.name
    )


if __name__ == "__main__":
    # 测试示例
    import sys

    if len(sys.argv) < 2:
        print("用法: python doc_classifier.py <markdown_file>")
        sys.exit(1)

    md_path = Path(sys.argv[1])
    if not md_path.exists():
        print(f"错误: 文件不存在: {md_path}")
        sys.exit(1)

    result = classify_from_markdown_file(md_path)

    print("\n" + "=" * 60)
    print("文档分类结果：")
    print("=" * 60)
    print(f"类型: {result['type_name']} ({result['type']})")
    print(f"置信度: {result['confidence']:.2%}")
    print(f"理由: {result['reason']}")
    print("=" * 60)
