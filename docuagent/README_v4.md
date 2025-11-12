# DocuAgent v4 - Markdown-based Reversible Preprocessing Pipeline

## 概述

v4 是 DocuAgent 的最新版本，采用基于 Markdown 的可逆预处理流程，实现了 DOCX 模板的智能标注和填充。

## 核心特性

- **可逆转换**：DOCX ↔ Markdown 无损往返
- **结构保留**：完整保留字体、表格、合并单元格等元数据
- **LLM 友好**：生成易于 LLM 理解的特征 Markdown
- **精确定位**：通过 block marker 和 cell marker 实现精确的内容回写
- **多模型支持**：支持 DeepSeek、Qwen 等多种 LLM

## 项目结构

```
docuagent/v4/
├── __init__.py                  # v4 模块导出
├── docx_markdown_converter.py  # DOCX → Markdown 转换器
├── feature_markdown.py          # 特征 Markdown 生成器
├── llm_annotator.py            # LLM 标注器（含 prompt 工程）
├── run_llm_annotation.py       # LLM 标注流程（LangGraph）
├── apply_annotations.py        # 标注应用器
└── markdown_to_docx.py         # Markdown → DOCX 重建器
```

## 使用方法

### 方法 1：使用主流程脚本

```bash
python run_v4_docx_to_annotation.py "模板文件.docx"
```

这将自动执行完整的 v4 流程：
1. DOCX → Markdown 转换
2. 生成特征 Markdown
3. LLM 标注
4. 应用标注并重建 DOCX

### 方法 2：分步调用

```python
from docuagent.v4 import (
    export_docx_to_markdown,
    generate_feature_markdown,
    apply_annotations_and_rebuild_docx,
)

# 1. 导出 Markdown
md_path, manifest_path = export_docx_to_markdown(
    docx_path="template.docx",
    output_dir="output/"
)

# 2. 生成特征 Markdown
features_path = generate_feature_markdown(
    md_path=md_path,
    manifest_path=manifest_path,
    output_dir="output/"
)

# 3. LLM 标注（需要单独运行 run_llm_annotation.py）
# ...

# 4. 应用标注并重建 DOCX
filled_docx = apply_annotations_and_rebuild_docx(
    md_path=md_path,
    manifest_path=manifest_path,
    annotations_json_path="annotations.json",
    output_dir="output/"
)
```

## 环境配置

需要设置以下环境变量：

```bash
export FIREWORKS_API_KEY="your-api-key"
```

或在 `config/settings.py` 中配置：

```python
FIREWORKS_API_KEY = "your-api-key"
```

## 输出结构

```
results/v4_pipeline/<template_name>_<timestamp>/
├── markdown/
│   ├── <name>_v4.md          # 原始 Markdown
│   ├── <name>_manifest.json  # 结构元数据
│   └── <name>_features.md    # 特征 Markdown
├── annotation/
│   ├── annotation_<timestamp>.json  # 标注结果
│   └── raw_<timestamp>/             # 原始 LLM 响应
└── applied/
    ├── <name>_v4_annotated.md       # 应用标注后的 Markdown
    └── <name>_v4_filled.docx        # 最终填充的 DOCX
```

## 依赖项

- `python-docx`: DOCX 文件处理
- `langchain-fireworks`: LLM API 调用
- `langgraph`: LLM 工作流编排

安装依赖：

```bash
pip install python-docx langchain-fireworks langgraph
```

## v4 相比旧版本的改进

1. **完全可逆**：v4 实现了 DOCX ↔ Markdown 的无损往返
2. **更好的表格支持**：正确处理合并单元格和复杂表格结构
3. **精确的位置追踪**：通过 marker 系统实现精确的内容定位
4. **改进的提示工程**：更智能的 LLM 提示，支持示例文本替换、矩阵覆盖等
5. **健壮的 JSON 解析**：多层次的 JSON 修复机制

## 迁移指南

如果你之前使用 v1/v2/v3，现在应该：

1. 旧版本代码已移至 `docuagent/_legacy_v1/`
2. 直接使用 `from docuagent.v4 import ...`
3. 或使用新的 `from docuagent import ...`（默认导出 v4）

## 故障排除

### 1. API 连接错误

如果遇到 `httpx.RemoteProtocolError`，这通常是网络问题，请：
- 检查网络连接
- 重试即可

### 2. 导入错误

如果遇到导入错误，确保：
```bash
export PYTHONPATH=.
python your_script.py
```

### 3. Token 超限

如果模板过大导致 token 超限，可以：
- 调整 `DEFAULT_MAX_TOKENS`（默认 100,000）
- 启用分段处理（将 `no_segment=False`）

## 贡献指南

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License
