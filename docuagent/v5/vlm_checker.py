"""
VLM 文档质量检查器

功能：
1. 将 DOCX 转换为图片
2. 使用 VLM 检查文档质量
3. 返回问题列表和严重程度
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from pdf2image import convert_from_path
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

try:
    import aspose.words as aw
    HAS_ASPOSE = True
except ImportError:
    HAS_ASPOSE = False

try:
    from docx2pdf import convert as docx2pdf_convert
    HAS_DOCX2PDF = True
except ImportError:
    HAS_DOCX2PDF = False

# VLM API（使用 DashScope Qwen-VL）
try:
    from dashscope import MultiModalConversation
    import dashscope
    from config.settings import DASHSCOPE_API_KEY
    dashscope.api_key = DASHSCOPE_API_KEY
    HAS_DASHSCOPE = True
except ImportError:
    HAS_DASHSCOPE = False


VLM_MODEL = os.getenv("VLM_MODEL", "qwen-vl-max")
DOCX2PDF_WAIT_SECONDS = float(os.getenv("DOCX2PDF_WAIT_SECONDS", 10))


def _render_docx_to_images(docx_path: Path) -> List[Path]:
    """
    将 DOCX 渲染为图片列表

    步骤：
    1. DOCX → PDF (使用 LibreOffice 或 docx2pdf)
    2. PDF → Images (使用 pdf2image)

    Returns:
        图片路径列表，每页一张
    """
    if not HAS_PDF2IMAGE:
        raise RuntimeError(
            "pdf2image 未安装。请运行：pip install pdf2image\n"
            "macOS 还需要：brew install poppler"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        pdf_path = tmp_path / f"{docx_path.stem}.pdf"

        _convert_docx_to_pdf(docx_path, pdf_path)

        # PDF → Images
        try:
            # 🔧 FIX: 确保传递字符串路径而非Path对象
            images = convert_from_path(str(pdf_path), dpi=150)
        except Exception as e:
            raise RuntimeError(f"PDF 转图片失败: {e}")

        # 保存图片到临时目录
        image_paths = []
        output_dir = Path("results/v5_vlm_temp")
        output_dir.mkdir(parents=True, exist_ok=True)

        for i, img in enumerate(images, start=1):
            img_path = output_dir / f"{docx_path.stem}_page_{i}.png"
            img.save(img_path, "PNG")
            image_paths.append(img_path)

        return image_paths


def _call_vlm_api(
    image_paths: List[Path],
    user_requirement: str = "",
    doc_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    调用 VLM API 检查文档质量

    Args:
        image_paths: 文档图片路径列表
        user_requirement: 用户需求（用于判断内容是否符合要求）

    Returns:
        {
            "issues": [
                {
                    "kind": "placeholder_not_filled",  # 问题类型
                    "location": "第2页，表格第3行",
                    "detail": "{{course_name}} 占位符未替换",
                    "severity": "high"  # low/medium/high
                },
                ...
            ],
            "summary": {
                "severity": "medium",  # 整体严重程度
                "notes": "部分占位符未填充，但整体结构完整"
            }
        }
    """
    if not HAS_DASHSCOPE:
        raise RuntimeError("DashScope SDK 未安装。请运行：pip install dashscope")

    # 加载知识库示例
    kb_example = ""
    if doc_type:
        kb_path = Path("knowledge") / doc_type / "experiences.jsonl"
        if kb_path.exists():
            try:
                with open(kb_path, encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        kb_entry = json.loads(first_line)
                        generator_prompts = kb_entry.get("generator_prompts", [])
                        if generator_prompts:
                            kb_example = "\n\n📚 **字段要求参考**（请严格遵守）：\n"
                            for prompt_obj in generator_prompts[:5]:  # 最多取前5条
                                kb_example += f"- {prompt_obj.get('prompt', '')}\n"
            except Exception as e:
                print(f"   ⚠️ 加载知识库失败: {e}")

    # 构建检查提示词
    instruction = f"""
你是一个文档质量检查专家。请基于提供的整页图片，**只检查以下3个核心问题**：

⚠️ 重要：请忽略以下内容（这些不是问题）：
- "Evaluation Only. Created with Aspose.Words" 水印文字
- "Created with an evaluation copy of Aspose.Words" 水印文字
- 任何包含 "Aspose" 的水印信息
这些是文档处理库自动添加的水印，不是文档质量问题，不要报告。

📋 **检查范围（仅限以下3项）**：

1️⃣ **文本长度不对**

   A) **基础信息字段不应过长**：
   - 姓名/教师/授课教师：应≤5字
   - 工作单位/学校/单位：应≤15字
   - 地区/地市/区县：应≤10字
   - 年级/班级：应≤10字
   - 学科/科目：应≤10字（如：计算机、数学、英语。不要写成"深度学习与卷积神经网络"）
   - 教材/教材版本：应≤15字
   - 表格第一列标题：应≤30字（推荐4-10字，如"导入新课"）
   - 任务书题目：应≤20字

   B) **内容字段不应过短**（应该详细但太简短）：
   - 教学目标：应≥100字（太短如"了解CNN"是错误的）
   - 教学内容/教学内容分析：应≥150字
   - 教学重点与难点/教学重难点：应≥100字
   - 教学过程：应≥200字
   - 教学反思/教学小结：应≥80字
   - 任务书目的与意义：应≥800字
   - 任务书构思与内容：应≥800字
   - 任务书进度计划：应≥300字
   - 如果这些字段只有几个字或一句话，说明内容太少

2️⃣ **本应该有内容的地方却为空**
   - 空白的表格单元格（应该填充内容的位置）
   - 空白的段落区域（标题后缺少正文）
   - 未替换的占位符（{{{{...}}}}、[xxx]、____等）

3️⃣ **文本和标题不匹配**
   - 表格列标题被正文内容覆盖
   - 段落标题与内容主题不符
   - 标题文字出现在错误的位置

🚫 **不要检查以下问题**（超出范围）：
- 排版格式（文字重叠、边距、对齐等）
- 内容质量（是否专业、是否合理等）
- 教学设计（是否符合教学要求等）
- 内容是否符合用户需求（只检查格式和字段要求）
{kb_example}
⚠️ **修复建议格式要求**：
- 只针对格式和字段长度问题给建议
- 不要建议修改内容质量或教学设计
- 建议要具体可操作（如："缩短'学科'字段至10字以内"）
- 不要使用模糊建议（如："优化内容质量"、"改进教学设计"）

输出格式（必须合法 JSON，只输出 JSON）：
{{
  "issues": [
    {{
      "kind": "length_exceeded | content_missing | title_mismatch",
      "location": "第X页/第X行/表格第X行第X列",
      "detail": "具体问题描述（简短明确，只描述格式问题）",
      "severity": "low | medium | high"
    }}
  ],
  "summary": {{
    "severity": "low | medium | high",
    "notes": "整体评价（1-2句话，只评价格式和字段完整性）"
  }},
  "recommendations": {{
    "overall": ["全局修复建议（1-2条，只针对格式和字段长度）"],
    "by_issue": [
      {{
        "issue_index": 1,
        "suggestion": "具体修复建议（如：缩短'姓名'字段至5字以内，补充'教学目标'至100字以上）"
      }}
    ]
  }}
}}
"""

    # 构建消息内容（多模态）
    content = [{"text": instruction}]
    for img_path in image_paths:
        content.append({"image": f"file://{img_path.resolve()}"})

    messages = [{"role": "user", "content": content}]

    # 调用 VLM
    try:
        response = MultiModalConversation.call(
            model=VLM_MODEL,
            messages=messages,
            result_format="message",
        )

        if response.status_code != 200:
            raise RuntimeError(f"VLM API 调用失败: {response.message}")

        # 解析响应
        output_text = response.output.choices[0].message.content[0]["text"]

        # 尝试提取 JSON（移除可能的 markdown 代码块标记）
        output_text = output_text.strip()
        if output_text.startswith("```json"):
            output_text = output_text[7:]
        if output_text.startswith("```"):
            output_text = output_text[3:]
        if output_text.endswith("```"):
            output_text = output_text[:-3]
        output_text = output_text.strip()

        result = json.loads(output_text)

        # 验证格式
        if "issues" not in result or "summary" not in result:
            raise ValueError(f"VLM 返回格式错误: {result}")

        return result

    except Exception as e:
        raise RuntimeError(f"VLM 检查失败: {e}")


def _wait_for_file(path: Path, timeout: float) -> bool:
    """等待文件创建完成"""
    deadline = time.time() + timeout
    while time.time() <= deadline:
        if path.exists() and path.stat().st_size > 0:
            return True
        time.sleep(0.5)
    return path.exists() and path.stat().st_size > 0


def _convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> Path:
    """
    将 DOCX 转换为 PDF，优先 Aspose.Words，其次 docx2pdf，最后 LibreOffice
    """
    errors: List[str] = []
    disable_docx2pdf = os.getenv("DOCX2PDF_DISABLED", "0") == "1"
    disable_aspose = os.getenv("ASPOSE_DISABLED", "0") == "1"

    if HAS_ASPOSE and not disable_aspose:
        try:
            doc = aw.Document(str(docx_path))
            save_options = aw.saving.PdfSaveOptions()
            save_options.compliance = aw.saving.PdfCompliance.PDF17
            doc.save(str(pdf_path), save_options)
            if _wait_for_file(pdf_path, 2):
                return pdf_path
            errors.append("Aspose 保存后未检测到 PDF")
        except Exception as e:
            errors.append(f"Aspose 转换失败: {e}")

    if HAS_DOCX2PDF and not disable_docx2pdf:
        try:
            docx2pdf_convert(str(docx_path), str(pdf_path))
            if not _wait_for_file(pdf_path, DOCX2PDF_WAIT_SECONDS):
                # 某些 macOS 环境会在原目录生成 PDF（忽略输出路径）
                fallback_pdf = docx_path.with_suffix(".pdf")
                if fallback_pdf.exists():
                    shutil.copy2(fallback_pdf, pdf_path)
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                return pdf_path
            errors.append(f"docx2pdf 未生成 PDF（期望路径: {pdf_path}）")
        except Exception as e:
            errors.append(f"docx2pdf 失败: {e}")

    soffice_bin = os.getenv("SOFFICE_BIN") or shutil.which("soffice")
    if soffice_bin:
        try:
            cmd = [
                soffice_bin,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", str(pdf_path.parent),
                str(docx_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 0:
                return pdf_path
            errors.append(
                f"LibreOffice 转换失败（code={result.returncode}）：{result.stderr.strip()}"
            )
        except FileNotFoundError:
            errors.append("未找到 LibreOffice (soffice)")
        except Exception as e:
            errors.append(f"LibreOffice 异常: {e}")
    else:
        errors.append("系统未安装 LibreOffice（缺少 soffice）")

    raise RuntimeError("DOCX 转 PDF 失败: " + " | ".join(errors))


def check_docx_quality(
    docx_path: Path,
    user_requirement: str = "",
    outdir: Optional[Path] = None,
    doc_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    检查 DOCX 文档质量（主入口）

    Args:
        docx_path: DOCX 文件路径
        user_requirement: 用户需求描述
        outdir: 输出目录（保存图片和结果）
        doc_type: 文档类型（如 lesson_plan, task_proposal）

    Returns:
        VLM 检查结果（包含 issues 和 summary）
    """
    print(f"🔍 VLM 质量检查开始: {docx_path.name}")

    # 1. 渲染 DOCX → 图片
    print("   📸 正在将 DOCX 渲染为图片...")
    image_paths = _render_docx_to_images(docx_path)
    print(f"   ✅ 已生成 {len(image_paths)} 页图片")

    # 2. 调用 VLM 检查
    print(f"   🤖 正在调用 VLM ({VLM_MODEL}) 检查文档...")
    vlm_result = _call_vlm_api(image_paths, user_requirement, doc_type)

    issues_count = len(vlm_result.get("issues", []))
    severity = vlm_result.get("summary", {}).get("severity", "unknown")
    print(f"   ✅ VLM 检查完成: 发现 {issues_count} 个问题，严重程度 {severity}")

    # 3. 保存结果
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)
        result_path = outdir / "vlm_review.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(vlm_result, f, ensure_ascii=False, indent=2)
        print(f"   💾 检查结果已保存到: {result_path}")

        # 移动图片到输出目录
        for img_path in image_paths:
            new_path = outdir / img_path.name
            img_path.rename(new_path)
        print(f"   📁 文档图片已保存到: {outdir}")

    return vlm_result


if __name__ == "__main__":
    # 测试
    import sys
    if len(sys.argv) < 2:
        print("用法: python vlm_checker.py <docx_path> [user_requirement]")
        sys.exit(1)

    docx_path = Path(sys.argv[1])
    user_req = sys.argv[2] if len(sys.argv) > 2 else ""

    result = check_docx_quality(docx_path, user_req, outdir=Path("results/v5_vlm_test"))

    print("\n" + "=" * 60)
    print("VLM 检查结果：")
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))
