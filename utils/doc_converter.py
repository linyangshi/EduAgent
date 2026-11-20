"""
DOC to DOCX Converter Utility
使用 LibreOffice/soffice 将 .doc 文件转换为 .docx

依赖: LibreOffice (Linux服务器上通常已安装或可通过包管理器安装)
Ubuntu/Debian: sudo apt-get install libreoffice-writer-nogui
CentOS/RHEL: sudo yum install libreoffice-writer
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Union


class DocConverter:
    """DOC到DOCX转换器"""

    def __init__(self):
        """初始化转换器，检测LibreOffice是否可用"""
        self.soffice_path = self._find_soffice()
        if not self.soffice_path:
            raise RuntimeError(
                "未找到 LibreOffice/soffice。请安装 LibreOffice:\n"
                "  Ubuntu/Debian: sudo apt-get install libreoffice-writer-nogui\n"
                "  CentOS/RHEL: sudo yum install libreoffice-writer\n"
                "  macOS: brew install --cask libreoffice"
            )

    def _find_soffice(self) -> Optional[str]:
        """查找LibreOffice的soffice可执行文件"""
        # 常见路径
        possible_paths = [
            'soffice',  # 系统PATH中
            '/usr/bin/soffice',  # Linux标准路径
            '/opt/libreoffice/program/soffice',  # Linux备用路径
            '/Applications/LibreOffice.app/Contents/MacOS/soffice',  # macOS
            '/opt/homebrew/bin/soffice',  # macOS Homebrew
        ]

        for path in possible_paths:
            if shutil.which(path) or os.path.exists(path):
                return path

        return None

    def convert(
        self,
        input_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
        timeout: int = 60
    ) -> Path:
        """
        将 .doc 文件转换为 .docx

        Args:
            input_path: 输入的 .doc 文件路径
            output_dir: 输出目录（默认为输入文件所在目录）
            timeout: 转换超时时间（秒），默认60秒

        Returns:
            转换后的 .docx 文件路径

        Raises:
            FileNotFoundError: 输入文件不存在
            ValueError: 输入文件不是 .doc 格式
            RuntimeError: 转换失败
        """
        input_path = Path(input_path).resolve()

        # 验证输入文件
        if not input_path.exists():
            raise FileNotFoundError(f"文件不存在: {input_path}")

        if not input_path.suffix.lower() == '.doc':
            raise ValueError(f"输入文件必须是 .doc 格式，当前: {input_path.suffix}")

        # 确定输出目录
        if output_dir is None:
            output_dir = input_path.parent
        else:
            output_dir = Path(output_dir).resolve()
            output_dir.mkdir(parents=True, exist_ok=True)

        # 预期的输出文件路径
        output_path = output_dir / f"{input_path.stem}.docx"

        # 如果输出文件已存在，先删除（LibreOffice不会覆盖）
        if output_path.exists():
            output_path.unlink()

        # 构建转换命令
        cmd = [
            self.soffice_path,
            '--headless',  # 无GUI模式
            '--convert-to', 'docx',  # 转换为docx格式
            '--outdir', str(output_dir),  # 输出目录
            str(input_path)  # 输入文件
        ]

        try:
            # 执行转换
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )

            # 验证输出文件是否创建
            if not output_path.exists():
                raise RuntimeError(
                    f"转换失败: 输出文件未创建\n"
                    f"命令: {' '.join(cmd)}\n"
                    f"stdout: {result.stdout}\n"
                    f"stderr: {result.stderr}"
                )

            return output_path

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"转换超时（>{timeout}秒）")

        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"LibreOffice转换失败（退出码: {e.returncode}）\n"
                f"stdout: {e.stdout}\n"
                f"stderr: {e.stderr}"
            )

    def is_doc_file(self, file_path: Union[str, Path]) -> bool:
        """检查文件是否为 .doc 格式"""
        return Path(file_path).suffix.lower() == '.doc'

    def auto_convert_if_needed(
        self,
        file_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None
    ) -> Path:
        """
        自动检测并转换：如果是 .doc 则转换为 .docx，否则直接返回原路径

        Args:
            file_path: 输入文件路径
            output_dir: 输出目录（仅在需要转换时使用）

        Returns:
            .docx 文件路径（可能是转换后的，也可能是原文件）
        """
        file_path = Path(file_path)

        if self.is_doc_file(file_path):
            print(f"检测到 .doc 文件，自动转换为 .docx: {file_path.name}")
            return self.convert(file_path, output_dir)
        else:
            return file_path


# 便捷函数
def convert_doc_to_docx(
    input_path: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    timeout: int = 60
) -> Path:
    """
    将 .doc 文件转换为 .docx（便捷函数）

    Args:
        input_path: 输入的 .doc 文件路径
        output_dir: 输出目录（默认为输入文件所在目录）
        timeout: 转换超时时间（秒）

    Returns:
        转换后的 .docx 文件路径
    """
    converter = DocConverter()
    return converter.convert(input_path, output_dir, timeout)


def ensure_docx(
    file_path: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None
) -> Path:
    """
    确保文件为 .docx 格式，如果是 .doc 则自动转换

    Args:
        file_path: 输入文件路径
        output_dir: 输出目录（仅在需要转换时使用）

    Returns:
        .docx 文件路径
    """
    converter = DocConverter()
    return converter.auto_convert_if_needed(file_path, output_dir)


if __name__ == '__main__':
    # 测试代码
    import sys

    if len(sys.argv) < 2:
        print("用法: python doc_converter.py <input.doc> [output_dir]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        output_file = convert_doc_to_docx(input_file, output_dir)
        print(f"✅ 转换成功: {output_file}")
    except Exception as e:
        print(f"❌ 转换失败: {e}")
        sys.exit(1)
