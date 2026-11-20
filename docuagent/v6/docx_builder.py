"""
V6 DOCX构建器 - 基于占位符和生成内容直接构建Word文档

核心思路:
1. 读取原始DOCX模板
2. 遍历所有段落和表格单元格
3. 查找并替换占位符 {{placeholder_name}}
4. 保留原始格式（字体、样式、表格结构等）

简化版本:
- 不需要Markdown中间层
- 直接在DOCX中查找替换占位符
- 保留所有原始格式
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.oxml.text.paragraph import CT_P
    from docx.oxml.table import CT_Tbl
    from docx.table import Table, _Cell
    from docx.text.paragraph import Paragraph
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


class DocxBuilder:
    """DOCX构建器 - 基于占位符替换"""

    def __init__(self, template_docx_path: str | Path):
        """
        初始化DOCX构建器

        Args:
            template_docx_path: 模板DOCX路径
        """
        if not HAS_DOCX:
            raise RuntimeError("python-docx未安装，请运行: pip install python-docx")

        self.template_path = Path(template_docx_path)
        if not self.template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {self.template_path}")

        self.doc = Document(str(self.template_path))
        self.replacements_made = 0

    def find_placeholders(self) -> List[str]:
        """
        查找文档中所有的占位符

        Returns:
            占位符列表（去重）
        """
        placeholders = set()

        # 查找段落中的占位符
        for para in self.doc.paragraphs:
            found = re.findall(r'\{\{(\w+)\}\}', para.text)
            placeholders.update(found)

        # 查找表格中的占位符
        for table in self.doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        found = re.findall(r'\{\{(\w+)\}\}', para.text)
                        placeholders.update(found)

        return sorted(list(placeholders))

    def replace_in_paragraph(self, paragraph: Paragraph, placeholder: str, content: str) -> bool:
        """
        在段落中替换占位符

        Args:
            paragraph: 段落对象
            placeholder: 占位符名称（不含{{}}）
            content: 替换内容

        Returns:
            是否替换成功
        """
        pattern = r'\{\{' + re.escape(placeholder) + r'\}\}'

        if not re.search(pattern, paragraph.text):
            return False

        # 保留原始格式的替换策略:
        # 1. 如果整个段落只有一个占位符，直接替换整个段落文本
        # 2. 如果有多个run（格式片段），逐个run替换

        # 检查是否整段只有占位符
        if paragraph.text.strip() == f'{{{{{placeholder}}}}}':
            # 清空所有runs，添加新内容（保留第一个run的格式）
            if paragraph.runs:
                first_run = paragraph.runs[0]
                # 删除所有runs
                for _ in range(len(paragraph.runs)):
                    paragraph._element.remove(paragraph.runs[0]._element)
                # 添加新run，保留格式
                new_run = paragraph.add_run(content)
                if first_run.font:
                    new_run.font.name = first_run.font.name
                    new_run.font.size = first_run.font.size
                    new_run.font.bold = first_run.font.bold
                    new_run.font.italic = first_run.font.italic
                    new_run.font.color.rgb = first_run.font.color.rgb if first_run.font.color else None
            else:
                paragraph.text = content

            self.replacements_made += 1
            return True

        # 逐个run替换（保留各run的原始格式）
        replaced = False
        for run in paragraph.runs:
            if re.search(pattern, run.text):
                run.text = re.sub(pattern, content, run.text)
                replaced = True

        if replaced:
            self.replacements_made += 1

        return replaced

    def replace_in_table(self, table: Table, placeholder: str, content: str) -> bool:
        """
        在表格中替换占位符

        Args:
            table: 表格对象
            placeholder: 占位符名称
            content: 替换内容

        Returns:
            是否替换成功
        """
        replaced = False

        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    if self.replace_in_paragraph(para, placeholder, content):
                        replaced = True

        return replaced

    def replace_placeholder(self, placeholder: str, content: str) -> int:
        """
        替换文档中所有出现的指定占位符

        Args:
            placeholder: 占位符名称（不含{{}}）
            content: 替换内容

        Returns:
            替换次数
        """
        count = 0

        # 替换段落中的占位符
        for para in self.doc.paragraphs:
            if self.replace_in_paragraph(para, placeholder, content):
                count += 1

        # 替换表格中的占位符
        for table in self.doc.tables:
            if self.replace_in_table(table, placeholder, content):
                count += 1

        return count

    def replace_all(self, placeholder_content: Dict[str, str]) -> Dict[str, int]:
        """
        批量替换所有占位符

        Args:
            placeholder_content: {placeholder_name: content}

        Returns:
            {placeholder_name: replacement_count}
        """
        results = {}

        for placeholder, content in placeholder_content.items():
            count = self.replace_placeholder(placeholder, content)
            results[placeholder] = count

            if count > 0:
                print(f"  ✅ {placeholder}: 替换 {count} 处")
            else:
                print(f"  ⚠️  {placeholder}: 未找到匹配")

        return results

    def save(self, output_path: str | Path) -> Path:
        """
        保存文档

        Args:
            output_path: 输出路径

        Returns:
            输出文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.doc.save(str(output_path))
        return output_path

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取文档统计信息

        Returns:
            统计字典
        """
        return {
            "total_paragraphs": len(self.doc.paragraphs),
            "total_tables": len(self.doc.tables),
            "total_replacements": self.replacements_made,
        }


def build_docx_from_annotations(
    base_docx_path: str | Path,
    annotations: List[Dict[str, Any]],
    generated_content: Dict[str, str],
    output_docx_path: str | Path,
) -> Dict[str, Any]:
    """
    基于标注和生成内容构建DOCX文档

    Args:
        base_docx_path: 原始模板DOCX路径
        annotations: 标注列表（包含placeholder_name等）
        generated_content: {placeholder_name: content}
        output_docx_path: 输出DOCX路径

    Returns:
        构建结果字典
    """
    print(f"\n🔨 构建DOCX文档...")
    print(f"   模板: {Path(base_docx_path).name}")
    print(f"   待替换占位符: {len(generated_content)} 个")

    # 创建构建器
    builder = DocxBuilder(base_docx_path)

    # 查找模板中所有占位符
    template_placeholders = builder.find_placeholders()
    print(f"   模板中占位符: {len(template_placeholders)} 个")

    # 批量替换
    print(f"\n📝 开始替换占位符...")
    replacement_results = builder.replace_all(generated_content)

    # 保存
    output_path = builder.save(output_docx_path)
    stats = builder.get_statistics()

    print(f"\n✅ DOCX构建完成:")
    print(f"   输出文件: {output_path}")
    print(f"   总替换数: {stats['total_replacements']}")
    print(f"   文档段落: {stats['total_paragraphs']}")
    print(f"   文档表格: {stats['total_tables']}")

    # 检查未替换的占位符
    unmatched = set(generated_content.keys()) - set(k for k, v in replacement_results.items() if v > 0)
    if unmatched:
        print(f"\n⚠️  未匹配的占位符 ({len(unmatched)}):")
        for placeholder in sorted(unmatched):
            print(f"   - {placeholder}")

    # 检查模板中剩余的占位符
    remaining_placeholders = []
    doc_check = Document(str(output_path))
    for para in doc_check.paragraphs:
        found = re.findall(r'\{\{(\w+)\}\}', para.text)
        remaining_placeholders.extend(found)
    for table in doc_check.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    found = re.findall(r'\{\{(\w+)\}\}', para.text)
                    remaining_placeholders.extend(found)

    if remaining_placeholders:
        print(f"\n⚠️  文档中仍有未替换占位符 ({len(set(remaining_placeholders))}):")
        for placeholder in sorted(set(remaining_placeholders)):
            print(f"   - {{{{{placeholder}}}}}")

    return {
        "output_path": str(output_path),
        "total_replacements": stats["total_replacements"],
        "template_placeholders": template_placeholders,
        "generated_placeholders": list(generated_content.keys()),
        "matched_placeholders": [k for k, v in replacement_results.items() if v > 0],
        "unmatched_placeholders": list(unmatched),
        "remaining_placeholders": list(set(remaining_placeholders)),
        "statistics": stats,
    }


def quick_build_docx(
    template_path: str | Path,
    placeholder_content: Dict[str, str],
    output_path: str | Path,
) -> Path:
    """
    快捷方法：直接构建DOCX

    Args:
        template_path: 模板路径
        placeholder_content: {placeholder_name: content}
        output_path: 输出路径

    Returns:
        输出文件路径
    """
    builder = DocxBuilder(template_path)
    builder.replace_all(placeholder_content)
    return builder.save(output_path)


if __name__ == "__main__":
    # 测试示例
    print("V6 DOCX构建器")
    print("\n使用示例:")
    print("  from docuagent.v6.docx_builder import quick_build_docx")
    print("  ")
    print("  quick_build_docx(")
    print("      template_path='template.docx',")
    print("      placeholder_content={")
    print("          'course_name': 'Python编程',")
    print("          'teacher_name': '张老师',")
    print("      },")
    print("      output_path='output.docx'")
    print("  )")
