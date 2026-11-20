# DocuAgent v5：VLM 闭环质量检查系统

## 概述

v5 在 v4 的基础上增加了 **VLM 视觉质量检查**和**知识库管理**功能，实现了真正的闭环自我改进系统。

### v5 新特性

1. **VLM 质量检查器** (`vlm_checker.py`)
   - 将生成的 DOCX 转换为图片
   - 使用视觉语言模型（Qwen-VL）检查文档质量
   - 识别占位符未替换、表头覆盖、空白区域、格式错误等问题
   - 返回结构化的问题列表和严重程度评级

2. **错误分析与反思模块** (`reflection.py`)
   - 分析 VLM 检查结果，判断错误来源（标注器 vs 生成器）
   - 使用 LLM 进行根因分析
   - 生成针对性的改进建议
   - 输出结构化的分析报告

3. **知识库管理系统** (`knowledge_base.py`)
   - 存储历史经验（JSONL 格式）
   - 聚合洞察：按标注器/生成器分类
   - 自动生成提示词注入内容
   - 支持统计、查询、清理等功能

4. **两种运行模式**
   - **训练模式**：迭代改进，直到 VLM 认可
   - **推理模式**：直接输出，不进行 VLM 检查

## 架构

```
v5 训练模式流程：
┌─────────────────────────────────────────────────────────────┐
│  DOCX 模板                                                   │
└──────────────┬──────────────────────────────────────────────┘
               ↓
┌──────────────────────────────────────────────────────────────┐
│  第 N 次迭代                                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  1. 标注器（注入知识库洞察）                           │ │
│  │     - 从知识库加载历史标注问题                          │ │
│  │     - 改进标注策略                                      │ │
│  └────────────┬───────────────────────────────────────────┘ │
│               ↓                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  2. 生成器（注入知识库洞察）                           │ │
│  │     - 从知识库加载历史生成问题                          │ │
│  │     - 改进生成策略                                      │ │
│  └────────────┬───────────────────────────────────────────┘ │
│               ↓                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  3. 应用标注并生成 DOCX                                │ │
│  └────────────┬───────────────────────────────────────────┘ │
│               ↓                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  4. VLM 质量检查                                        │ │
│  │     - DOCX → PDF → Images                              │ │
│  │     - VLM 视觉检查                                      │ │
│  │     - 返回问题列表 + 严重程度                           │ │
│  └────────────┬───────────────────────────────────────────┘ │
│               ↓                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  5. 错误分析                                            │ │
│  │     - 判断错误来源（标注器 vs 生成器）                  │ │
│  │     - 生成改进建议                                      │ │
│  └─────────��──┬───────────────────────────────────────────┘ │
│               ↓                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  6. 存入知识库                                          │ │
│  │     - 保存问题 + 分析 + 建议                            │ │
│  │     - 供下次迭代使用                                    │ │
│  └────────────┬───────────────────────────────────────────┘ │
│               ↓                                              │
│        [VLM 认可?]  ─No→  返回第 1 步（下一次迭代）          │
│               ↓                                              │
│             Yes                                              │
└─────��────────┬───────────────────────────────────────────────┘
               ↓
        ✅ 输出最终 DOCX
```

## 文件结构

```
docuagent/v5/
├── vlm_checker.py          # VLM 质量检查器
├── reflection.py           # 错误分析与反思
├── knowledge_base.py       # 知识库管理
└── README.md              # 本文件

run_v5_pipeline.py         # v5 主入口脚本（项目根目录）
```

## 使用方法

### 训练模式（带 VLM 检查，迭代改进）

```bash
python run_v5_pipeline.py "未标注模板2.docx" \
    --mode training \
    --prompt "生成2课时的Python编程课程教案" \
    --max-iterations 3
```

**流程**：
1. 运行标注 + 生成（注入知识库经验）
2. VLM 检查生成的 DOCX
3. 如果有问题：
   - 错误分析（判断来源）
   - 存入知识库
   - 返回第 1 步，使用新知识重试
4. 如果 VLM 认可（severity <= low）：
   - 输出最终 DOCX
   - 结束

### 推理模式（直接输出，无 VLM 检查）

```bash
python run_v5_pipeline.py "未标注模板2.docx" \
    --mode inference \
    --prompt "生成2课时的Python编程课程教案"
```

**流程**：
1. 运行标注 + 生成（注入知识库经验）
2. 直接输出 DOCX
3. 结束

### 指定知识库路径

```bash
python run_v5_pipeline.py "template.docx" \
    --mode training \
    --kb results/custom_knowledge_base.jsonl
```

## 输出结构

```
results/v5_pipeline/{template_name}_{mode}_{timestamp}/
├── markdown/
│   ├── {template}_v4.md                # 原始 Markdown
│   ├── {template}_features.md          # 特征 Markdown
│   └── {template}_manifest.json        # 文档元数据
│
├── annotation/
│   └── iter0/                          # 第 0 次迭代
│       ├── annotation_*.json           # 标注结果
│       └── raw_*/                      # LLM 原始响应
│
├── generated/
│   └── iter0/                          # 第 0 次迭代
│       ├── generated_content.json      # 生成的内容
│       ├── filled_annotation_iter0.json # 填充后的标注
│       ├── annotated_iter0.md          # 注入后的 Markdown
│       └── generated_iter0.docx        # ✅ 生成的 DOCX
│
├── vlm_checks/                         # 仅训练模式
│   └── iter0/
│       ├── vlm_review.json             # VLM 检查结果
│       ├── error_analysis.json         # 错误分析
│       ├── reflection_raw.txt          # LLM 原始响应
│       └── {template}_page_*.png       # 文档截图
│
├── user_input.json                     # 用户输入
└── pipeline_summary.json               # 管线摘要
```

## 依赖

### 必需
- Python 3.10+
- `python-docx`
- `openai` (Fireworks API)
- `dashscope` (Qwen-VL API)

### VLM 检查器额外依赖
```bash
# macOS
brew install poppler libreoffice
pip install pdf2image

# 或使用 docx2pdf（Windows/macOS）
pip install docx2pdf
```

## 知识库格式

知识库以 JSONL 格式存储，每行一个 JSON 对象：

```json
{
  "timestamp": "2025-11-14T10:30:00",
  "template_name": "未标注模板2.docx",
  "user_requirement": "生成Python课程教案",
  "vlm_severity": "high",
  "issue_count": 5,
  "issues": [
    {
      "kind": "placeholder_not_filled",
      "location": "第1页，表格第3行",
      "detail": "{{course_name}} 未替换",
      "severity": "high"
    }
  ],
  "analysis": [
    {
      "issue_index": 1,
      "root_cause": "generator",
      "reason": "生成器未识别该占位符",
      "recommendation": {
        "for_annotator": "",
        "for_generator": "增强占位符识别逻辑"
      }
    }
  ],
  "overall_recommendation": {
    "priority": "high",
    "key_insights": ["需要改进占位符识别"],
    "next_steps": ["检查生成器配置"]
  }
}
```

## 配置

### 环境变量

```bash
# VLM 模型（默认: qwen-vl-max）
export VLM_MODEL="qwen-vl-max"

# 错误分析模型（默认: qwen2p5-72b-instruct）
export REFLECTION_MODEL="accounts/fireworks/models/qwen2p5-72b-instruct"

# API Keys
export DASHSCOPE_API_KEY="sk-..."
export FIREWORKS_API_KEY="..."
```

### VLM 认可阈值

在 `run_v5_pipeline.py` 中修改：

```python
VLM_APPROVAL_THRESHOLD = "low"  # low/medium/high
# severity <= threshold 时认为合格
```

## 与 v4 的区别

| 特性 | v4 | v5 |
|------|----|----|
| 标注 + 生成 | ✅ | ✅ |
| VLM 质量检查 | ❌ | ✅ |
| 错误分析 | ❌ | ✅ |
| 知识库管理 | ❌ | ✅ |
| 闭环改进 | ❌ | ✅（训练模式）|
| 直接输出 | ✅ | ✅（推理模式）|

## 最佳实践

1. **首次使用**：用训练模式运行几个模板，积累知识库
2. **生产使用**：用推理模式快速生成，利用已有知识
3. **定期训练**：每隔一段时间用新模板训练，更新知识库
4. **知识库清理**：定期调用 `kb.prune_old_entries(keep_latest=100)` 清理旧条目

## 示例

### 查看知识库统计

```python
from docuagent.v5.knowledge_base import get_knowledge_base

kb = get_knowledge_base()
stats = kb.get_stats()
print(stats)
# {
#   "total_entries": 15,
#   "date_range": {"earliest": "...", "latest": "..."},
#   "severity_distribution": {"high": 5, "medium": 8, "low": 2},
#   "avg_issues_per_entry": 3.2
# }
```

### 手动聚合洞察

```python
insights = kb.aggregate_insights(max_entries=50, min_severity="medium")
print(insights["annotator_insights"][:3])
# [
#   {
#     "pattern": "遗漏表头单元格标注",
#     "recommendation": "检查表头识别逻辑",
#     "frequency": 5
#   },
#   ...
# ]
```

## 注意事项

1. **VLM API 成本**：每次检查需要渲染 PDF 并调用 VLM API，训练模式成本较高
2. **图片渲染**：需要 LibreOffice 或 docx2pdf，确保系统已安装
3. **知识库大小**：定期清理，避免过大影响性能
4. **API 限流**：如果频繁调用，可能触发 API 限流，建议在迭代间添加延迟

## 故障排除

### VLM 检查失败

```
RuntimeError: pdf2image 未安装
```

**解决**：
```bash
# macOS
brew install poppler
pip install pdf2image

# Linux
sudo apt install poppler-utils
pip install pdf2image
```

### LibreOffice 转换失败

```
RuntimeError: LibreOffice 转换失败
```

**解决**：
```bash
# macOS
brew install libreoffice

# Linux
sudo apt install libreoffice
```

### 知识库为空

如果首次运行推理模式，知识库可能为空，此时：
- 不影响运行，只是没有历史经验可用
- 建议先用训练模式运行几次，积累知识

## 后续改进方向

1. **VLM 并行检查**：多页并行处理，加速检查
2. **更细粒度的错误定位**：精确到段落/单元格
3. **自动化测试**：基于 VLM 的质量回归测试
4. **知识库可视化**：Web 界面查看和管理知识库
5. **多模型支持**：支持更多 VLM 模型（Claude Vision, GPT-4V 等）

## 许可证

与 DocuAgent 主项目相同
