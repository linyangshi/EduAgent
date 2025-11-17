# 文档生成服务 (Document Generator)

统一的文档生成API，整合V6 pipeline核心功能，可独立使用。

## 功能特性

- ✅ **自动文档分类**: LLM自动识别文档类型（教案、任务书、论文等）
- ✅ **知识库集成**: 自动加载历史经验，提升生成质量
- ✅ **并行标注**: 多线程标注，速度提升1.4-2倍
- ✅ **完美格式保留**: 使用V4 workflow，保留原始DOCX格式
- ✅ **质量检查**: VLM视觉检查（可选，training模式）
- ✅ **反思学习**: 自动分析错误并存储改进建议
- ✅ **批量生成**: 支持批量处理多个文档

## 快速开始

### 方式1: 使用便捷函数（推荐）

```python
from core.document_generator import generate_document

# 快速生成文档
result = generate_document(
    template_path="template.docx",
    user_requirement="生成Python编程基础课程教案，包括变量、数据类型、控制结构等内容",
    mode="inference"  # 或 "training"
)

if result.success:
    print(f"✅ 生成成功: {result.final_docx}")
    print(f"📊 文档类型: {result.doc_type_name}")
    print(f"⏱️  耗时: {result.performance['total_time']:.2f}秒")
else:
    print(f"❌ 生成失败: {result.error}")
```

### 方式2: 使用DocumentGenerator类

```python
from core.document_generator import DocumentGenerator

# 创建生成器实例
generator = DocumentGenerator(
    max_concurrent_annotate=3,  # 并行标注线程数
    max_concurrent_generate=10,  # 并行生成线程数
    vlm_max_iterations=3,        # VLM最大迭代次数
    vlm_quality_threshold=0.7    # VLM质量阈值
)

# 生成单个文档
result = generator.generate(
    template_path="template.docx",
    user_requirement="生成课程教案",
    mode="inference",
    output_dir="results/output"  # 可选，默认自动生成
)

# 批量生成
results = generator.generate_batch(
    templates=["template1.docx", "template2.docx"],
    requirements=["需求1", "需求2"],
    mode="inference"
)
```

### 方式3: 命令行使用

```bash
# 快速生成
python core/document_generator.py template.docx "生成Python课程教案" inference

# 指定输出目录
python core/document_generator.py template.docx "生成任务书" training
```

## API 参考

### DocumentGenerator

主文档生成器类。

#### 构造函数参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_concurrent_annotate` | int | 3 | 并行标注最大线程数 |
| `max_concurrent_generate` | int | 10 | 并行生成最大线程数 |
| `vlm_max_iterations` | int | 3 | VLM检查最大迭代次数 |
| `vlm_quality_threshold` | float | 0.7 | VLM质量阈值（0-1） |

#### generate() 方法

生成单个文档。

```python
result = generator.generate(
    template_path="template.docx",      # 必需: 模板路径
    user_requirement="生成需求描述",     # 必需: 用户需求
    mode="inference",                    # 可选: inference/training
    output_dir=None,                     # 可选: 输出目录
    no_segment=False                     # 可选: 禁用分段标注
)
```

**参数说明:**

- `template_path` (str): 模板文档路径，必须是 `.docx` 格式
- `user_requirement` (str): 用户需求描述，描述要生成的内容
- `mode` (str): 运行模式
  - `"inference"`: 推理模式，跳过VLM检查，快速生成
  - `"training"`: 训练模式，执行VLM检查和反思学习
- `output_dir` (str, optional): 输出目录，默认自动生成
- `no_segment` (bool): 是否禁用分段标注，默认False

**返回值:**

`DocumentGenerationResult` 对象，包含以下属性:

```python
result.success           # bool: 是否成功
result.doc_type          # str: 文档类型代码 (lesson_plan/task_proposal等)
result.doc_type_name     # str: 文档类型名称 (教案/任务书等)
result.final_docx        # str: 最终生成的DOCX路径
result.annotation_json   # str: 标注JSON路径
result.markdown          # str: Markdown路径
result.statistics        # dict: 统计信息
result.performance       # dict: 性能指标
result.error             # str: 错误信息（失败时）
```

#### generate_batch() 方法

批量生成多个文档。

```python
results = generator.generate_batch(
    templates=["t1.docx", "t2.docx"],
    requirements=["需求1", "需求2"],
    mode="inference",
    output_base_dir="results/batch"
)
```

### generate_document()

便捷函数，快速生成文档。

```python
from core.document_generator import generate_document

result = generate_document(
    template_path="template.docx",
    user_requirement="生成需求",
    mode="inference",
    output_dir=None,
    **kwargs  # 其他参数传递给DocumentGenerator
)
```

## 工作流程

完整的文档生成流程包含以下阶段:

```
1. DOCX → Markdown 转换
   ↓
2. LLM 文档类型分类
   ↓
3. 加载对应知识库
   ↓
4. 多线程并行标注
   ↓
5. JSON 格式修正
   ↓
6. V4 内容生成 workflow
   ↓
7. VLM 质量检查 (training模式)
   ↓
8. 反思学习存储 (training模式)
```

### 阶段详解

#### 阶段1: DOCX → Markdown 转换

使用V4的 `docx_to_markdown_v4` 将DOCX转换为带有DOCX-BLOCK标记的Markdown。

**输出:**
- `教学设计模板_v4.md` - Markdown文件
- `教学设计模板_v4_manifest.json` - 结构元数据

#### 阶段2: LLM 文档类型分类

使用LLM自动识别文档类型，支持:

- `lesson_plan` - 教案
- `task_proposal` - 任务书
- `thesis` - 论文
- `report` - 报告
- `other` - 其他

#### 阶段3: 知识库加载

根据文档类型加载对应的知识库:

```
knowledge/
├── lesson_plan/experiences.jsonl      # 教案知识库
├── task_proposal/experiences.jsonl    # 任务书知识库
├── thesis/experiences.jsonl           # 论文知识库
└── ...
```

#### 阶段4: 多线程并行标注

使用V6的 `parallel_annotate` 进行多线程标注:

- 自动分段处理大文档
- 并行调用LLM标注各段落
- 合并标注结果
- **性能提升**: 1.4-2倍加速

#### 阶段5: JSON 格式修正

使用 `fix_annotation_json` 修正和验证标注JSON格式。

#### 阶段6: V4 内容生成

调用V4的 `run_content_generation`:

- 字段分析和依赖解析
- 批量生成 (减少API调用)
- 注入知识库洞察
- Markdown填充
- DOCX重建 (完美保留格式)

#### 阶段7: VLM 质量检查 (training模式)

使用VLM检查生成的DOCX:

- DOCX → PDF → 图片
- VLM视觉检查
- 检测未替换占位符、格式错误
- 最多迭代3次

#### 阶段8: 反思学习 (training模式)

分析VLM反馈并存储改进建议:

- 根因分析 (标注器/生成器/模板)
- 生成可操作建议
- 存储到知识库

## 使用示例

### 示例1: 生成教案

```python
from core.document_generator import generate_document

result = generate_document(
    template_path="教学设计模板.docx",
    user_requirement="""
    生成Python编程基础课程教案，第一课：变量与数据类型
    - 课程对象: 高一学生
    - 教学目标: 理解变量概念，掌握基本数据类型
    - 教学重点: 变量赋值，整数、浮点数、字符串的使用
    - 教学难点: 类型转换
    """,
    mode="inference"
)

print(f"生成文档: {result.final_docx}")
```

### 示例2: 生成任务书（带质量检查）

```python
from core.document_generator import DocumentGenerator

generator = DocumentGenerator(
    max_concurrent_annotate=2,
    vlm_max_iterations=3
)

result = generator.generate(
    template_path="任务书模板.docx",
    user_requirement="生成基于深度学习的图像识别系统毕业设计任务书",
    mode="training",  # 启用VLM检查
    output_dir="results/task_book"
)

if result.success:
    print(f"✅ 任务书生成完成")
    print(f"📄 文件: {result.final_docx}")
    print(f"📊 标注数: {result.statistics['total_annotations']}")
    print(f"⏱️  总耗时: {result.performance['total_time']:.2f}秒")
```

### 示例3: 批量生成

```python
from core.document_generator import DocumentGenerator

generator = DocumentGenerator()

templates = [
    "教案模板.docx",
    "任务书模板.docx",
    "开题报告模板.docx"
]

requirements = [
    "生成Python课程教案",
    "生成图像识别毕业设计任务书",
    "生成深度学习开题报告"
]

results = generator.generate_batch(
    templates=templates,
    requirements=requirements,
    mode="inference",
    output_base_dir="results/batch_generation"
)

for i, result in enumerate(results):
    if result.success:
        print(f"[{i+1}] ✅ {result.final_docx}")
    else:
        print(f"[{i+1}] ❌ {result.error}")
```

### 示例4: 自定义配置

```python
from core.document_generator import DocumentGenerator

# 高性能配置 (适合服务器)
generator_fast = DocumentGenerator(
    max_concurrent_annotate=5,   # 5个并发标注线程
    max_concurrent_generate=20,  # 20个并发生成线程
)

# 保守配置 (适合API限流)
generator_safe = DocumentGenerator(
    max_concurrent_annotate=2,
    max_concurrent_generate=5,
    vlm_max_iterations=2,
)

# 高质量配置 (适合训练)
generator_quality = DocumentGenerator(
    vlm_max_iterations=5,
    vlm_quality_threshold=0.8,  # 更高的质量要求
)
```

## 输出文件结构

生成完成后，输出目录包含:

```
results/output_20251117_120000/
├── markdown/
│   ├── template_v4.md               # Markdown转换
│   └── template_v4_manifest.json    # 结构元数据
├── annotation/
│   ├── annotations.json             # 标注结果
│   └── raw_parallel/                # 原始并行标注输出
│       ├── segment_01_parallel.txt
│       └── segment_02_parallel.txt
├── generation/
│   ├── generated_content.json       # 生成的内容
│   ├── filled_annotation.json       # 填充后的标注
│   ├── template_v4_annotated.md     # 标注后的Markdown
│   └── final.docx                   # ⭐ 最终生成的文档
└── generation_report_20251117_120000.json  # 运行报告
```

## 性能优化

### 并发配置建议

| 场景 | 标注并发 | 生成并发 | 说明 |
|------|----------|----------|------|
| 本地开发 | 2-3 | 5-10 | 避免API限流 |
| 服务器部署 | 5-8 | 10-20 | 最大性能 |
| API限流严格 | 1-2 | 3-5 | 保守配置 |
| 大文档 | 3-5 | 10-15 | 平衡速度与稳定性 |

### 性能指标

典型性能（以教案模板为例）:

- **小文档** (< 5KB): 2-3分钟
- **中等文档** (5-20KB): 5-10分钟
- **大文档** (> 20KB): 10-20分钟

V6并行标注相比V4顺序标注:

- **小文档** (1段): 1.0x (无加速)
- **中等文档** (2-3段): 1.4-1.6x
- **大文档** (4+段): 1.8-2.0x

## 错误处理

```python
from core.document_generator import generate_document

try:
    result = generate_document(
        template_path="template.docx",
        user_requirement="生成内容",
        mode="inference"
    )

    if result.success:
        print(f"✅ 成功: {result.final_docx}")
    else:
        print(f"❌ 失败: {result.error}")

except FileNotFoundError:
    print("模板文件不存在")
except Exception as e:
    print(f"未知错误: {e}")
```

## 与Flask集成

在Flask应用中使用:

```python
from flask import Flask, request, jsonify
from core.document_generator import generate_document

app = Flask(__name__)

@app.route('/api/generate-document', methods=['POST'])
def api_generate_document():
    data = request.json

    result = generate_document(
        template_path=data['template_path'],
        user_requirement=data['requirement'],
        mode=data.get('mode', 'inference'),
        output_dir=data.get('output_dir')
    )

    return jsonify(result.to_dict())
```

## 常见问题

### Q: 如何选择mode参数？

- **inference模式**: 快速生成，跳过VLM检查，适合生产环境
- **training模式**: 包含VLM检查和反思学习，适合训练和质量改进

### Q: 并发数设置多少合适？

根据API限流策略:
- Qwen API: 建议标注并发2-3，生成并发5-10
- 本地部署: 可适当提高到5-8和10-20

### Q: 生成失败怎么办？

1. 检查API配置: `DASHSCOPE_API_KEY`
2. 检查模板格式: 必须是 `.docx` 格式
3. 查看错误信息: `result.error`
4. 检查输出报告: `generation_report_*.json`

### Q: 如何提高生成质量？

1. 使用 `training` 模式启用VLM检查
2. 提供详细的 `user_requirement`
3. 积累知识库（多次训练）
4. 调整 `vlm_quality_threshold` (提高标准)

## 完整示例

```python
#!/usr/bin/env python3
"""
完整示例: 生成教案并查看结果
"""

from core.document_generator import DocumentGenerator

def main():
    # 创建生成器
    generator = DocumentGenerator(
        max_concurrent_annotate=3,
        max_concurrent_generate=10,
        vlm_max_iterations=3,
        vlm_quality_threshold=0.7
    )

    # 生成文档
    result = generator.generate(
        template_path="教学设计模板.docx",
        user_requirement="""
        生成高一Python编程课程教案
        课题: 第1课 - 变量与数据类型

        教学目标:
        1. 理解变量的概念和作用
        2. 掌握Python基本数据类型（int, float, str, bool）
        3. 能够进行数据类型转换

        教学重点:
        - 变量的命名规则和赋值
        - 不同数据类型的特点和使用

        教学难点:
        - 类型转换的规则和应用场景
        """,
        mode="inference",
        output_dir="results/python_lesson1"
    )

    # 处理结果
    if result.success:
        print("\n" + "="*80)
        print("✅ 文档生成成功！")
        print("="*80)
        print(f"\n📄 文档类型: {result.doc_type_name}")
        print(f"📁 最终文档: {result.final_docx}")
        print(f"\n📊 统计信息:")
        print(f"   - 标注数量: {result.statistics['total_annotations']}")
        print(f"   - 生成字段: {result.statistics['generation_summary']['completed_fields']}")
        print(f"\n⏱️  性能指标:")
        print(f"   - 总耗时: {result.performance['total_time']:.2f} 秒")
        print(f"   - 标注耗时: {result.performance['parallel_annotation']:.2f} 秒")
        print(f"   - 生成耗时: {result.performance['content_generation']:.2f} 秒")
        print("="*80 + "\n")
    else:
        print("\n" + "="*80)
        print("❌ 文档生成失败")
        print("="*80)
        print(f"\n错误信息:\n{result.error}")
        print("="*80 + "\n")

if __name__ == "__main__":
    main()
```

## 依赖说明

`core/document_generator.py` 依赖以下模块:

```
docuagent/
├── v4/
│   ├── docx_to_markdown.py          # DOCX转Markdown
│   └── content_generation/
│       └── workflow.py               # 内容生成workflow
├── v6/
│   ├── parallel_annotator.py        # 并行标注
│   ├── doc_classifier.py            # 文档分类
│   ├── knowledge_base.py            # 知识库管理
│   ├── vlm_checker.py               # VLM检查
│   ├── reflection.py                # 反思学习
│   └── json_fixer.py                # JSON修复
```

**注意**: 这些模块已在项目中，无需额外安装。
