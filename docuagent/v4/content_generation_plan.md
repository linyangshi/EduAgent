# DocuAgent v4 - 内容生成流程设计

## 📋 需求概述

根据标注好的模板（包含占位符如 `{{course_name}}`）和用户提供的课程信息，自动生成完整的教案内容。

## 🏗️ 整体架构

```
输入：
├── 标注 JSON (annotation.json) - 包含所有占位符位置和类型
├── Markdown 模板 (template.md) - 包含占位符的模板
├── Manifest (manifest.json) - 文档结构元数据
└── 用户输入 (user_input.json) - 课程基本信息

输出：
├── 生成内容 JSON (generated_content.json) - 所有占位符的填充内容
└── 填充后的 DOCX (filled.docx) - 最终教案文档
```

## 🔄 LangGraph 工作流设计

### 状态定义

```python
@dataclass
class ContentGenerationState:
    # 输入数据
    annotations: List[Dict]           # 所有标注
    user_input: Dict[str, Any]        # 用户提供的基本信息
    manifest: Dict                     # 文档结构元数据
    markdown_context: str              # Markdown 上下文
    
    # 工作状态
    current_index: int = 0             # 当前处理的占位符索引
    analyzed_fields: List[Dict] = field(default_factory=list)  # 已分析的字段
    generated_content: Dict[str, str] = field(default_factory=dict)  # 已生成的内容
    
    # 控制标志
    is_complete: bool = False          # 是否完成所有生成
    error_message: Optional[str] = None
```

### 节点设计

#### 1. **Field Analyzer（字段分析器）**

**职责**：分析单个占位符，确定需要生成什么内容、长度、风格。

**输入**：
- 当前占位符信息（location, placeholder, action, reason）
- 上下文（周围的文本、表格结构）
- 已生成的相关内容

**输出**：
```python
{
    "placeholder": "teaching_objective",
    "field_type": "paragraph",  # 段落 / 列表 / 短语
    "content_type": "教学目标",
    "length_requirement": {
        "min_chars": 50,
        "max_chars": 300,
        "target_items": 3  # 如果是列表
    },
    "style": "formal",  # 正式 / 描述性 / 条目式
    "context_dependencies": ["course_name", "course_category"],  # 依赖的其他字段
    "generation_priority": "high",  # high / medium / low
    "generation_strategy": "structured_list"  # 生成策略
}
```

**LLM Prompt 示例**：
```
你是教案字段分析专家，请分析以下占位符需要什么样的内容：

占位符信息：
- 名称：{{teaching_objective}}
- 位置：段落，标签"教学目标："之后
- 上下文：这是一个教学设计表格，位于课程基本信息之后

周围内容：
- 前文：课程名称：{已知}，课程类别：{已知}
- 后文：教学重点、教学难点

请输出 JSON 格式的分析结果：
{
    "field_type": "...",
    "content_type": "...",
    "length_requirement": {...},
    "style": "...",
    "generation_strategy": "..."
}
```

#### 2. **Content Generator（内容生成器）**

**职责**：根据字段分析结果生成具体内容。

**输入**：
- 字段分析结果
- 用户提供的课程信息
- 已生成的相关内容（保持一致性）

**输出**：
```python
{
    "placeholder": "teaching_objective",
    "content": "1. 掌握Python基础语法...\n2. 理解面向对象编程思想...\n3. 能够独立编写简单程序...",
    "metadata": {
        "char_count": 156,
        "item_count": 3,
        "generation_time": "2025-11-11 21:15:30"
    }
}
```

**LLM Prompt 示例**：
```
你是专业的教案内容生成专家。请根据以下要求生成教学目标：

课程信息：
- 课程名称：{user_input.course_name}
- 课程类别：{user_input.course_category}
- 教学对象：{user_input.target_students}

生成要求：
- 内容类型：教学目标（3条结构化条目）
- 长度范围：50-300字
- 风格：正式，使用"掌握"、"理解"、"能够"等动词开头
- 格式：编号列表

已生成的相关内容：
- 课程名称：{generated.course_name}
- 课程简介：{generated.course_intro}

请直接输出教学目标内容（不要包含"教学目标："标签）：
```

#### 3. **Dependency Resolver（依赖解析器）**

**职责**：确定字段生成的顺序（解决依赖关系）。

**逻辑**：
- 基础信息字段（课程名称、教师名称等）优先生成
- 依赖其他字段的内容后生成
- 构建 DAG（有向无环图）确定执行顺序

**示例依赖关系**：
```
course_name (基础)
    ↓
teaching_objective (依赖课程名称)
    ↓
teaching_content (依赖教学目标)
    ↓
teaching_method (依赖教学内容)
```

#### 4. **Content Injector（内容注入器）**

**职责**：将生成的内容注入到 Markdown 模板中。

**输入**：
- 原始 Markdown
- 生成内容 Dict
- Annotation JSON

**输出**：
- 填充后的 Markdown

**逻辑**：
- 复用现有的 `apply_annotations_to_markdown` 逻辑
- 将占位符替换为生成的实际内容

#### 5. **Quality Checker（质量检查器）**

**职责**：检查生成内容的质量。

**检查项**：
- 长度是否符合要求
- 格式是否正确
- 是否与上下文一致
- 是否包含必要的关键词

**输出**：
- 如果通过：标记为完成
- 如果不通过：返回到生成器重新生成

### 工作流状态转换

```python
START
  ↓
[load_inputs] 加载所有输入数据
  ↓
[resolve_dependencies] 解析字段依赖关系，确定生成顺序
  ↓
[analyze_field] 分析当前字段 ←─────┐
  ↓                                 │
[generate_content] 生成内容         │
  ↓                                 │
[check_quality] 质量检查            │
  ↓                                 │
  ├─ 不通过 ──────────────────────┘
  ↓ 通过
[save_content] 保存生成内容
  ↓
[check_completion] 是否所有字段都完成？
  ├─ 否 ─→ current_index++ ─→ [analyze_field]
  ↓ 是
[inject_content] 将内容注入 Markdown
  ↓
[rebuild_docx] 重建 DOCX
  ↓
END
```

## 📁 代码模块组织

```
docuagent/v4/
├── content_generation/
│   ├── __init__.py
│   ├── state.py                    # 状态定义
│   ├── field_analyzer.py           # 字段分析器
│   ├── content_generator.py        # 内容生成器
│   ├── dependency_resolver.py      # 依赖解析器
│   ├── quality_checker.py          # 质量检查器
│   ├── content_injector.py         # 内容注入器
│   ├── prompts.py                  # 所有 LLM prompts
│   └── workflow.py                 # LangGraph 工作流定义
└── run_content_generation.py       # 主入口脚本
```

## 🔧 实现细节

### 1. 字段类型识别策略

```python
def identify_field_type(annotation: Dict, context: str) -> str:
    """
    根据标注和上下文识别字段类型
    
    字段类型分类：
    - basic_info: 基础信息（课程名称、教师姓名等）
    - time_info: 时间信息（学年学期、上课时间等）
    - objective: 目标类（教学目标、学习目标等）
    - content: 内容类（教学内容、教学过程等）
    - method: 方法类（教学方法、教学手段等）
    - assessment: 评价类（考核方式、作业布置等）
    """
    placeholder = annotation['placeholder']
    reason = annotation.get('reason', '')
    
    # 规则 1: 基于命名模式
    if any(kw in placeholder for kw in ['name', 'teacher', 'unit']):
        return 'basic_info'
    
    # 规则 2: 基于位置和上下文
    if 'objective' in placeholder or '目标' in reason:
        return 'objective'
    
    # 规则 3: 基于表格结构
    if 'table' in annotation.get('location_type', ''):
        # 分析表格上下文...
        pass
    
    return 'unknown'
```

### 2. 长度预估策略

```python
def estimate_content_length(field_type: str, location: Dict) -> Dict:
    """
    根据字段类型和位置预估内容长度
    
    考虑因素：
    - 单元格宽度（如果在表格中）
    - 字段类型的典型长度
    - 上下文中相似字段的长度
    """
    # 基础规则
    length_rules = {
        'basic_info': {'min': 2, 'max': 50},
        'objective': {'min': 50, 'max': 300, 'items': 3},
        'content': {'min': 100, 'max': 500},
        'method': {'min': 50, 'max': 200},
    }
    
    # 如果在表格中，分析单元格宽度
    if location.get('location_type') == 'table_cell':
        cell_span = extract_span_from_marker(location['cell_marker'])
        # span 越大，内容可能越长
        multiplier = min(cell_span / 3.0, 2.0)
        return {
            'min': int(length_rules[field_type]['min'] * multiplier),
            'max': int(length_rules[field_type]['max'] * multiplier)
        }
    
    return length_rules.get(field_type, {'min': 20, 'max': 200})
```

### 3. 依赖关系自动检测

```python
def build_dependency_graph(annotations: List[Dict]) -> nx.DiGraph:
    """
    构建字段依赖关系图
    
    依赖判断规则：
    1. 基础信息字段无依赖（课程名称、教师等）
    2. 目标类字段依赖基础信息
    3. 内容类字段依赖目标类
    4. 方法类字段依赖内容类
    5. 评价类字段依赖所有前序内容
    """
    graph = nx.DiGraph()
    
    # 添加所有节点
    for ann in annotations:
        graph.add_node(ann['placeholder'], data=ann)
    
    # 添加边（依赖关系）
    for ann in annotations:
        field_type = identify_field_type(ann)
        dependencies = infer_dependencies(field_type, ann)
        
        for dep in dependencies:
            if dep in graph.nodes:
                graph.add_edge(dep, ann['placeholder'])
    
    # 检查循环依赖
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("检测到循环依赖！")
    
    return graph
```

### 4. 生成策略

不同类型字段使用不同的生成策略：

```python
GENERATION_STRATEGIES = {
    'basic_info': 'direct_mapping',      # 直接映射用户输入
    'time_info': 'format_conversion',    # 格式转换
    'objective': 'structured_list',      # 结构化列表生成
    'content': 'paragraph_generation',   # 段落生成
    'method': 'method_suggestion',       # 方法建议
    'assessment': 'assessment_design',   # 评价设计
}
```

## 📊 用户输入格式

```json
{
    "basic_info": {
        "course_name": "Python程序设计",
        "course_category": "专业必修课",
        "teacher_name": "张老师",
        "teaching_unit": "计算机学院",
        "class_hours": 48,
        "credits": 3.0
    },
    "teaching_context": {
        "target_students": "计算机专业大一学生",
        "prerequisite": "已学习计算机基础",
        "course_objectives": "掌握Python编程基础",
        "teaching_focus": "面向对象编程"
    },
    "content_preferences": {
        "style": "formal",              # formal / casual / interactive
        "detail_level": "detailed",     # brief / normal / detailed
        "include_examples": true,
        "language_level": "undergraduate"
    }
}
```

## 🎯 优化策略

### 1. 批量生成

对于相似的字段（如多个教学环节的"教学内容"），可以批量生成：

```python
def batch_generate_similar_fields(fields: List[Dict]) -> List[str]:
    """
    批量生成相似字段，提高效率和一致性
    """
    prompt = f"""
    请为以下教学环节分别生成教学内容：
    1. {fields[0]['context']}
    2. {fields[1]['context']}
    3. {fields[2]['context']}
    
    要求保持风格一致，内容连贯。
    """
    # 一次调用生成多个
    return llm.generate(prompt)
```

### 2. 渐进式生成

先生成大纲，再填充细节：

```
第一轮：生成所有字段的简要内容
第二轮：根据需要扩展详细内容
第三轮：优化和润色
```

### 3. 缓存机制

对于常见的字段组合，缓存生成结果：

```python
# 缓存键：课程类型 + 字段类型
cache_key = f"{course_category}:{field_type}"
if cache_key in generation_cache:
    return adapt_cached_content(generation_cache[cache_key], user_input)
```

## 🧪 测试策略

### 1. 单元测试

```python
def test_field_analyzer():
    annotation = {
        'placeholder': 'teaching_objective',
        'reason': '教学目标填写区域'
    }
    result = analyze_field(annotation, context="...")
    assert result['field_type'] == 'objective'
    assert result['length_requirement']['target_items'] == 3
```

### 2. 端到端测试

```python
def test_full_generation_pipeline():
    user_input = load_test_user_input()
    annotations = load_test_annotations()
    
    result = run_content_generation(annotations, user_input)
    
    assert len(result['generated_content']) == len(annotations)
    assert all(len(v) > 0 for v in result['generated_content'].values())
```

## 📝 实施计划

### Phase 1: 核心框架（1-2天）
- [ ] 定义状态类和基础数据结构
- [ ] 实现 LangGraph 工作流骨架
- [ ] 实现简单的字段分析器（基于规则）

### Phase 2: 生成器实现（2-3天）
- [ ] 实现内容生成器（集成 LLM）
- [ ] 设计和测试各类字段的 prompt
- [ ] 实现依赖解析器

### Phase 3: 质量保证（1-2天）
- [ ] 实现质量检查器
- [ ] 添加重试机制
- [ ] 实现内容注入和 DOCX 重建

### Phase 4: 优化和测试（2-3天）
- [ ] 批量生成优化
- [ ] 缓存机制
- [ ] 完整的端到端测试
- [ ] 性能优化

## 🚀 使用示例

```python
from docuagent.v4.content_generation import run_content_generation

# 准备输入
user_input = {
    "basic_info": {
        "course_name": "Python程序设计",
        "teacher_name": "张老师",
        # ...
    },
    "teaching_context": {
        "target_students": "大一学生",
        # ...
    }
}

# 运行生成流程
result = run_content_generation(
    annotation_path="results/v4_pipeline/xxx/annotation/annotation.json",
    markdown_path="results/v4_pipeline/xxx/markdown/template.md",
    manifest_path="results/v4_pipeline/xxx/markdown/manifest.json",
    user_input=user_input,
    output_dir="results/v4_generated/"
)

# 输出
print(f"生成完成！")
print(f"填充后的 DOCX: {result['output_docx']}")
print(f"生成了 {len(result['generated_content'])} 个字段")
```

## 🎓 最佳实践

1. **保持上下文一致性**：已生成的内容要传递给后续生成，保持整体连贯
2. **处理生成失败**：设置重试机制和降级策略
3. **用户可控**：允许用户审阅和修改生成的内容
4. **增量生成**：支持只生成部分字段，其他保留占位符
5. **模板适配**：针对不同类型的教案模板，调整生成策略

## 📚 参考资料

- LangGraph 文档: https://langchain-ai.github.io/langgraph/
- 教案编写规范: (根据实际需求补充)
- LLM Prompt 工程最佳实践

## 🔄 未来扩展

- [ ] 多模态支持：生成图表、图片
- [ ] 协作编辑：多人协作完善教案
- [ ] 版本管理：保存生成历史
- [ ] 个性化：学习用户偏好，优化生成效果
