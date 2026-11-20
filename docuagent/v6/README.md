# DocuAgent V6 - 并行标注 + 批量生成 + VLM审查

## 概述

V6是DocuAgent的最新版本，实现了完整的**并行处理**和**简化的DOCX构建**流程。

### 核心改进

| 特性 | V4 | V5 | V6 |
|------|----|----|-----|
| 标注方式 | 顺序标注（3秒延迟） | 顺序标注 | **多线程并行标注** |
| 内容生成 | LangGraph单字段生成 | LangGraph单字段生成 | **批量并行生成** |
| 文档分类 | ❌ | ✅ | ✅ |
| VLM审查 | ❌ | ✅ | ✅ |
| 知识库学习 | ❌ | ✅ | ✅ |
| DOCX构建 | Markdown中间层 | Markdown中间层 | **直接占位符替换** |
| 预计加速比 | 1.0x | 1.0x | **3-5x** |

---

## 完整流程

```
1. DOCX → Markdown 转换
   ↓
2. LLM文档类型分类 (lesson_plan/task_proposal/thesis/report/other)
   ↓
3. 加载文档类型知识库 (knowledge/{doc_type}/experiences.jsonl)
   ↓
4. 多线程并行标注 ⚡ (ThreadPoolExecutor + Semaphore)
   ↓
5. JSON格式修正 (JSONFixer)
   ↓
6. 批量并行生成 ⚡ (批量prompt，一次生成多字段)
   ↓
7. 基于占位符构建DOCX ⚡ (直接替换{{placeholder}})
   ↓
8. VLM审查 + 反思学习 (仅training模式)
```

---

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 环境变量

```bash
# 必需
export DASHSCOPE_API_KEY="sk-xxx"  # 通义千问API

# 可选
export VLM_MODEL="qwen-vl-max"                 # VLM模型
export USE_QWEN_FOR_REFLECTION="true"         # 使用Qwen进行反思
```

### 基本使用

```bash
# Training模式（完整流程 + VLM审查）
python run_v6_pipeline.py "教学设计模板.docx" \
  --prompt "生成Python编程基础课程教案" \
  --mode training

# Inference模式（快速生成，跳过VLM审查）
python run_v6_pipeline.py "教学设计模板.docx" \
  --prompt "生成数据结构课程教案" \
  --mode inference

# 自定义并发配置
python run_v6_pipeline.py "模板.docx" \
  --prompt "生成内容" \
  --max-concurrent-annotate 5 \
  --max-concurrent-generate 10
```

---

## 模块说明

### 1. pipeline.py - 主管道
协调整个V6流程，返回`V6PipelineResult`对象。

### 2. parallel_annotator.py - 并行标注器
多线程并行标注文档，加速3-5x。

### 3. parallel_generator.py - 并行生成器
批量并行生成字段内容，加速10x。

### 4. docx_builder.py - DOCX构建器
直接基于占位符构建Word文档，无需Markdown中间层。

### 5-8. V5复用模块
- `doc_classifier.py`: 文档分类器
- `knowledge_base.py`: 知识库管理
- `vlm_checker.py`: VLM质量检查器
- `reflection.py`: 反思分析器

### 9. json_fixer.py - JSON修复器
修复LLM返回的不规范JSON。

---

## 性能对比

### 标注阶段（3段文档）
- V4/V5: 60秒（顺序处理）
- V6: 20秒（3线程并发）
- **加速比: 3.0x**

### 生成阶段（30个字段）
- V4/V5: 300秒（30次API调用）
- V6: 30秒（3次批量调用）
- **加速比: 10.0x**

### 总体加速
**典型场景**: 360秒 → 50秒，**加速7.2x**

---

## 输出文件

```
results/v6_20250117_123456/
├── markdown/
│   ├── template.md
│   └── manifest.json
├── annotation/
│   ├── annotations.json            # 标注结果
│   └── raw_parallel/
├── generation/
│   └── final.docx                  # 最终生成的Word文档 ⭐
├── vlm_review/                     # VLM审查（仅training模式）
└── v6_run_report_*.json            # 运行报告 ⭐
```

---

## 配置建议

| 参数 | 建议值 | 说明 |
|------|-------|------|
| `max_concurrent_annotate` | 3-5 | 标注阶段并发数 |
| `max_concurrent_generate` | 5-10 | 生成阶段并发数 |

### 模式选择

| 模式 | VLM审查 | 知识库更新 | 速度 |
|------|---------|----------|------|
| `training` | ✅ | ✅ | 慢 |
| `inference` | ❌ | ❌ | 快 |

---

## 与V4/V5的兼容性

- ✅ 可以使用V4/V5的模板DOCX
- ✅ 可以读取V5的知识库
- ✅ 输出格式与V5一致

---

## 已知限制

1. 并发数限制: 受API限流影响，建议不超过5线程
2. 批量生成字段数: 每批不超过15个字段
3. VLM模型: 仅支持Qwen-VL系列
4. DOCX格式: 不支持嵌入对象

---

## 详细文档

完整文档请查看项目README.md的V6章节。
