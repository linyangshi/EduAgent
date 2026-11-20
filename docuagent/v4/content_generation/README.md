# DocuAgent v4 - 内容生成模块

## 📋 功能概述

根据标注好的模板（包含占位符如 `{{course_name}}`）和用户提供的课程信息，自动生成完整的教案内容。

## 🏗️ 架构设计

### 核心组件

```
content_generation/
├── __init__.py              # 模块导出
├── state.py                 # 状态定义
├── field_analyzer.py        # 字段分析器
├── content_generator.py     # 内容生成器
├── prompts.py              # LLM Prompts
└── workflow.py             # LangGraph 工作流
```

### 工作流程

```
输入：标注JSON + 用户输入 + Markdown模板
  ↓
[load_inputs] 加载输入数据
  ↓
[analyze_fields] 分析所有字段
  ↓
[generate_content] 生成字段内容 ←────┐
  ↓                                  │
[check_quality] 质量检查             │
  ↓                                  │
  ├─ 未通过 → 重试（最多3次）────────┘
  ↓ 通过
[move_next] 移动到下一个字段
  ↓
  ├─ 未完成 → 回到 [generate_content]
  ↓ 完成
[inject_content] 注入内容
  ↓
输出：生成内容JSON
```

## 📦 模块详解

### 1. FieldAnalyzer（字段分析器）

**职责**：分析每个占位符，确定其类型、长度要求、生成策略等。

**字段类型**：
- `basic_info`: 基础信息（课程名、教师名等）
- `time_info`: 时间信息（学年学期、日期等）
- `objective`: 目标类（教学目标、学习目标）
- `content`: 内容类（教学内容、知识点）
- `method`: 方法类（教学方法、策略）
- `activity`: 活动类（教师活动、学生活动）
- `assessment`: 评价类（考核方式、作业）
- `resource`: 资源类（教学资源、材料）

**生成策略**：
- `direct_mapping`: 直接映射用户输入
- `structured_list`: 结构化列表生成（如教学目标）
- `paragraph_generation`: 段落生成
- `method_suggestion`: 方法建议
- `activity_design`: 活动设计
- `assessment_design`: 评价设计

### 2. ContentGenerator（内容生成器）

**职责**：根据字段分析结果，调用 LLM 生成实际内容。

**特性**：
- 支持直接映射（基础信息）
- 自动创建合适的 Prompt
- 内容后处理（格式规范化）
- 质量检查（长度、格式、内容）

### 3. LangGraph 工作流

**特性**：
- 自动处理字段依赖关系
- 失败重试机制（最多3次）
- 进度追踪
- 批量生成支持

## 🚀 使用方法

### 基本用法

```bash
python run_v4_content_generation.py <annotation_json_path> [user_input_json_path]
```

**示例**：
```bash
# 使用示例数据
python run_v4_content_generation.py \
    results/v4_pipeline/未标注模板2_xxx/annotation/annotation.json

# 使用自定义数据
python run_v4_content_generation.py \
    results/v4_pipeline/未标注模板2_xxx/annotation/annotation.json \
    my_user_input.json
```

### 用户输入格式

```json
{
  "basic_info": {
    "course_name": "Python程序设计基础",
    "course_category": "专业必修课",
    "teacher_name": "张老师",
    "teaching_unit": "计算机学院",
    "class_hours": 48,
    "credits": 3.0
  },
  "teaching_context": {
    "target_students": "计算机专业大一学生",
    "prerequisite": "计算机基础",
    "course_objectives": "掌握Python编程基础",
    "teaching_focus": "面向对象编程"
  },
  "content_preferences": {
    "style": "formal",
    "detail_level": "detailed",
    "include_examples": true
  }
}
```

### 编程方式调用

```python
from docuagent.v4.content_generation import run_content_generation

user_input = {
    "basic_info": {
        "course_name": "Python程序设计",
        # ...
    },
    "teaching_context": {
        "target_students": "大一学生",
        # ...
    }
}

result = run_content_generation(
    annotation_path="path/to/annotation.json",
    user_input=user_input,
    markdown_path="path/to/template.md",
    manifest_path="path/to/manifest.json",
    output_dir="results/generated/"
)

print(f"生成了 {result['completed_fields']} 个字段")
print(f"失败字段: {result['failed_fields']}")
```

## 📊 输出

### generated_content.json

```json
{
  "course_name": {
    "content": "Python程序设计基础",
    "metadata": {
      "char_count": 10,
      "quality_score": 0.9,
      "retry_count": 0
    }
  },
  "teaching_objective": {
    "content": "1. 掌握Python基础语法...\n2. 理解面向对象...",
    "metadata": {
      "char_count": 156,
      "quality_score": 0.9,
      "retry_count": 0
    }
  }
}
```

## ⚙️ 配置

### 环境变量

```bash
export FIREWORKS_API_KEY="your-api-key"
export FIREWORKS_ANNOTATION_MODEL="accounts/fireworks/models/deepseek-v3p1-terminus"
```

### 状态配置

可以在创建 `ContentGenerationState` 时配置：

```python
state = ContentGenerationState(
    max_retries=3,       # 每个字段最大重试次数
    batch_size=5,        # 批量生成大小（暂未实现）
)
```

## 🔧 扩展和优化

### 添加新的字段类型

1. 在 `field_analyzer.py` 的 `FIELD_TYPE_PATTERNS` 中添加模式
2. 在 `DEFAULT_LENGTH_REQUIREMENTS` 中定义长度
3. 在 `DEFAULT_GENERATION_STRATEGIES` 中定义策略

### 自定义 Prompt

编辑 `prompts.py` 中的相关函数：
- `_create_structured_list_prompt`: 列表类型
- `_create_paragraph_prompt`: 段落类型
- `_create_generic_prompt`: 通用类型

### 批量生成优化

`ContentGenerator.batch_generate()` 预留了批量生成接口，可以实现：
- 一次性生成多个相似字段
- 减少 API 调用次数
- 提高一致性

## 🐛 故障排除

### 1. RecursionLimit 错误

如果字段过多（>100），可能触发递归限制。已在代码中设置为500，如需更多：

```python
graph.invoke(initial_state, {"recursion_limit": 1000})
```

### 2. 字段分类错误

如果某些字段分类不正确，检查：
- `field_analyzer.py` 中的 `_identify_field_type` 逻辑
- 添加特殊规则处理边缘情况

### 3. 生成内容质量问题

- 调整 `content_generator.py` 中的 temperature（当前0.7）
- 优化 `prompts.py` 中的 prompt 模板
- 增加 `check_quality` 中的检查规则

### 4. 重试次数过多

某些字段可能无法满足长度要求，导致不断重试：
- 检查 `DEFAULT_LENGTH_REQUIREMENTS` 是否合理
- 在 `_determine_length_requirement` 中添加特殊处理

## 📈 性能指标

- **平均生成速度**: ~2-3秒/字段（取决于LLM响应）
- **165个字段预计时间**: 5-10分钟
- **重试率**: <10%（良好调优下）

## 🔮 未来改进

- [ ] 批量生成相似字段
- [ ] 缓存常见内容
- [ ] 渐进式生成（先大纲后细节）
- [ ] 用户可编辑中间结果
- [ ] 支持多轮对话式生成
- [ ] 生成内容的可视化预览

## 📚 参考

- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [DocuAgent v4 主文档](../README_v4.md)
- [完整设计文档](content_generation_plan.md)
