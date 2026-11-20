# DocuAgent

> 🚀 零样本、高鲁棒性的 Word 模板智能填充系统  
> Zero-shot, Robust Word Template Filling System

---

## 🎯 核心理念

DocuAgent 是一个**完全依赖 LLM API** 的文档智能填充系统，无需任何模型训练。核心优势：

1. **零样本 (Zero-shot)**：无需训练数据，直接使用预训练的大语言模型
2. **高鲁棒性 (Robust)**：格式安全优先，绝不生成损坏的 .docx 文件
3. **流程编排 (Orchestration)**：清晰的四阶段工作流，可控、可调试

---

## 📐 核心架构

DocuAgent 采用**四阶段工作流**：

```
┌─────────────────────────────────────────────────────────────────┐
│                         DocuAgent 工作流                          │
└─────────────────────────────────────────────────────────────────┘

📄 Word 模板 (.docx)
        ↓
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 1: Schema Tagging (模式标记)                                 │
│  - 提取 word/document.xml                                        │
│  - 调用 Tagger LLM 识别占位符                                     │
│  - 输出: schema.json                                             │
└─────────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 2: Content Planning (内容规划)                               │
│  - 接收: schema.json + 用户指令                                   │
│  - 调用 Planner LLM 生成内容大纲                                  │
│  - 输出: content_plan.json                                       │
└─────────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 3: Content Writing (内容写作)                                │
│  - 接收: content_plan.json                                       │
│  - 对每个字段调用 Writer LLM                                      │
│  - 输出: filled_content.json                                     │
└─────────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 4: Safe Injection (安全注入)                                 │
│  - 使用 lxml 解析 XML                                            │
│  - 安全转义（防止 XML 注入）                                       │
│  - 处理多段落（\\n → 多个 <w:p>）                                 │
│  - 重新打包为 .docx                                               │
└─────────────────────────────────────────────────────────────────┘
        ↓
📄 填充完成的文档 (.docx)
```

---

## 🚀 快速开始

### 1. 安装

DocuAgent 已集成在项目中，无需额外安装。确保已安装项目依赖：

```bash
pip install -r requirements.txt
```

额外依赖（如果未安装）：

```bash
pip install lxml
```

### 2. 配置 API Key

在 `config/settings.py` 中配置 API Key：

**选项 1: 通义千问 (默认)**
```python
DASHSCOPE_API_KEY = "sk-你的API密钥"
```

**选项 2: GitCode (推荐 - 支持 Qwen3-30B-A3B)**
```python
GITCODE_API_KEY = "your-gitcode-api-key"
```

**选项 3: Fireworks AI**
```python
FIREWORKS_API_KEY = "fw-你的API密钥"
```

或设置环境变量：

```bash
export DASHSCOPE_API_KEY="sk-你的API密钥"
# 或
export GITCODE_API_KEY="your-gitcode-api-key"
# 或
export FIREWORKS_API_KEY="fw-你的API密钥"
```

### 3. 基本使用

#### 方式 1: 使用便捷函数（推荐）

```python
from docuagent import fill_template

output_path = fill_template(
    template_path="template.docx",
    user_instruction="写一份关于AI教育的项目申报书",
    output_path="output.docx"
)

print(f"完成！文件保存在: {output_path}")
```

#### 方式 2: 使用 DocuAgent 类（更多控制）

**使用通义千问 (默认):**
```python
from docuagent import DocuAgent

# 初始化
agent = DocuAgent(provider="tongyi")

# 处理模板
output_path = agent.process(
    template_path="template.docx",
    user_instruction="生成一份关于Python编程的教案",
    output_path="output.docx"
)

# 查看统计
stats = agent.get_statistics()
print(stats)
```

**使用 GitCode (Qwen3-30B-A3B 模型):**
```python
from docuagent import DocuAgent

# 初始化 - 使用 GitCode API
agent = DocuAgent(
    provider="gitcode",
    model_name="Qwen/Qwen3-30B-A3B"  # 可选，默认就是这个模型
)

# 处理模板
output_path = agent.process(
    template_path="template.docx",
    user_instruction="生成一份关于机器学习的教案",
    output_path="output.docx"
)

print(f"完成！文件保存在: {output_path}")
```

#### 方式 3: 命令行

```bash
cd docuagent
python main.py ../templates_library/标注教案.docx "生成一份关于机器学习的教案" -o output.docx
```

---

## 📚 使用示例

### 示例 1: 教案生成

```python
from docuagent import DocuAgent

agent = DocuAgent()

output = agent.process(
    template_path="templates_library/标注教案.docx",
    user_instruction="生成《卷积神经网络》教案，适用于AI专业大三学生，2学时"
)
```

### 示例 2: 项目申报书

```python
from docuagent import fill_template

output = fill_template(
    template_path="项目申报模板.docx",
    user_instruction="""
    项目名称：智教创想AI教育平台
    申报单位：XX大学计算机学院
    项目类型：教学改革研究项目
    预算：50万元
    """,
    output_path="智教创想_项目申报书.docx"
)
```

### 示例 3: 批量处理

```python
from docuagent import DocuAgent

agent = DocuAgent()

topics = ["深度学习", "自然语言处理", "计算机视觉"]

for topic in topics:
    agent.process(
        template_path="template.docx",
        user_instruction=f"生成关于{topic}的教案",
        output_path=f"{topic}_教案.docx"
    )
```

### 示例 4: 从缓存继续（高级用法）

如果某个阶段失败，或者想手动修改中间结果：

```python
from docuagent import DocuAgent

agent = DocuAgent()

# 第一次运行会生成缓存文件：
# - docuagent_cache/schema.json
# - docuagent_cache/content_plan.json
# - docuagent_cache/filled_content.json

# 可以手动编辑这些文件，然后继续
output = agent.process_from_cache(
    template_path="template.docx",
    schema_path="docuagent_cache/schema.json",
    content_path="docuagent_cache/filled_content.json",
    output_path="output_from_cache.docx"
)
```

---

## 📁 模块结构

```
docuagent/
├── __init__.py          # 模块初始化
├── utils_docx.py        # Word 文档处理（XML 提取、安全注入）
├── utils_llm.py         # LLM 调用封装（Tagger, Planner, Writer）
├── prompts.py           # Prompt 模板库
├── main.py              # 主流程编排（四阶段工作流）
├── example.py           # 使用示例
└── README.md            # 本文档
```

---

## 🔧 核心模块说明

### 1. `utils_docx.py` - Word 文档处理

**核心类：** `DocxHandler`

**主要功能：**
- `extract_xml(docx_path)`: 从 .docx 提取 word/document.xml
- `inject_content(xml, schema, content)`: 安全地将内容注入 XML
- `repackage_docx(original, modified_xml, output)`: 重新打包为 .docx

**技术要点：**
- 使用 `zipfile` 处理 .docx（本质是 ZIP）
- 使用 `lxml` 解析和操作 XML
- 使用 `xml.sax.saxutils.escape` 防止 XML 注入
- 支持多段落处理（`\n` → 多个 `<w:p>` 元素）

### 2. `utils_llm.py` - LLM 调用

**核心类：** `LLMOrchestrator`

**主要功能：**
- `get_semantic_schema(xml)`: 调用 Tagger LLM 识别占位符
- `get_content_plan(schema, instruction)`: 调用 Planner LLM 生成大纲
- `generate_content_from_plan(plan, schema, instruction)`: 调用 Writer LLM 生成内容

**支持的 LLM：**
- 通义千问 (Tongyi/Qwen) - 默认
- Fireworks AI
- OpenAI API

### 3. `prompts.py` - Prompt 模板

**包含三个核心 Prompt：**
1. `TAGGER_PROMPT`: 识别占位符
2. `PLANNER_PROMPT`: 生成内容大纲
3. `WRITER_PROMPT`: 生成详细内容

### 4. `main.py` - 主流程

**核心类：** `DocuAgent`

**主要方法：**
- `process(template, instruction, output)`: 执行完整的四阶段工作流
- `process_from_cache(...)`: 从缓存继续处理
- `get_statistics()`: 获取统计信息

---

## 🎨 模板要求

DocuAgent 支持两种类型的模板：

### 1. 标签模板（推荐）

在 Word 文档中使用 `{{placeholder}}` 标记：

```
课程名称：{{course_name}}
授课教师：{{teacher_name}}

一、教学目标
{{teaching_objectives}}

二、教学重点
{{teaching_focus}}
```

### 2. 智能识别模板

DocuAgent 可以自动识别以下格式的占位符：
- `{{variable_name}}` (双花括号)
- `[字段名称]` (方括号)
- `___________` (下划线)
- 明显的空白区域

---

## 📊 性能与成本

**处理时间：**
- 小型模板（10-20个字段）：约 3-5 分钟
- 中型模板（30-50个字段）：约 8-15 分钟
- 大型模板（50+字段）：约 20-30 分钟

**API 调用次数：**
- Schema Tagging: 1 次
- Content Planning: 1 次
- Content Writing: N 次（N = 字段数量）
- **总计**: N + 2 次

**成本估算（使用通义千问）：**
- qwen-plus: ¥0.008/1K tokens
- qwen-turbo: ¥0.002/1K tokens
- 平均每个字段约消耗 500-1000 tokens
- **估算成本**: 中型模板（30字段）约 ¥0.5-1.5

---

## 🔍 调试与故障排除

### 查看中间结果

所有中间结果保存在 `docuagent_cache/` 目录：

```
docuagent_cache/
├── extracted_document.xml       # 原始 XML
├── schema.json                  # 识别的占位符
├── content_plan.json            # 内容大纲
├── filled_content.json          # 生成的内容
└── modified_document.xml        # 修改后的 XML
```

### 常见问题

**Q: 生成的内容格式不对？**
A: 检查 `filled_content.json`，确认内容是否正确。可以手动编辑后使用 `process_from_cache()` 继续。

**Q: 某些字段没有填充？**
A: 检查 `schema.json`，确认占位符是否被正确识别。

**Q: 生成的 .docx 损坏？**
A: 检查 `modified_document.xml`，确认 XML 格式是否正确。可能是特殊字符没有被正确转义。

**Q: API 调用失败？**
A: 检查 API Key 是否正确配置，网络是否正常。

---

## 🚧 高级功能

### 1. 自定义 Prompt

编辑 `prompts.py` 中的模板，调整 LLM 的行为：

```python
from docuagent.prompts import WRITER_PROMPT

# 修改 Prompt
WRITER_PROMPT = """
你是一个非常严谨的学术写作专家...
（自定义 Prompt 内容）
"""
```

### 2. 使用不同的 LLM

```python
import os
from docuagent import DocuAgent

# 使用 OpenAI
agent = DocuAgent(
    provider="openai",
    api_key=os.environ["OPENAI_API_KEY"]
)

# 使用 Fireworks
agent = DocuAgent(
    provider="fireworks",
    api_key=os.environ["FIREWORKS_API_KEY"]
)
```

### 3. 并行处理（加速）

```python
from concurrent.futures import ThreadPoolExecutor
from docuagent import DocuAgent

agent = DocuAgent()

templates = ["template1.docx", "template2.docx", "template3.docx"]
instructions = ["主题1", "主题2", "主题3"]

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [
        executor.submit(agent.process, tmpl, inst)
        for tmpl, inst in zip(templates, instructions)
    ]
    
    results = [f.result() for f in futures]
```

---

## 📖 与现有系统的集成

DocuAgent 可以与项目中现有的教案生成系统配合使用：

### 集成到 Flask API

```python
from flask import Flask, request, jsonify
from docuagent import fill_template

app = Flask(__name__)

@app.route('/api/fill_template', methods=['POST'])
def api_fill_template():
    data = request.json
    
    output = fill_template(
        template_path=data['template_path'],
        user_instruction=data['instruction']
    )
    
    return jsonify({'output_path': output})
```

### 集成到现有 Agent

```python
from core.agent import UniversityCourseAgent
from docuagent import DocuAgent

class EnhancedAgent(UniversityCourseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.docuagent = DocuAgent()
    
    def fill_template_smart(self, template_path, topic):
        return self.docuagent.process(template_path, topic)
```

---

## 🎓 最佳实践

1. **模板设计**：
   - 使用清晰的占位符命名（英文 + 下划线）
   - 为每个占位符添加描述性标签
   - 保持模板结构清晰

2. **指令编写**：
   - 提供足够的上下文信息
   - 明确指出关键要求
   - 可以包含结构化信息（列表、表格）

3. **性能优化**：
   - 使用缓存避免重复调用
   - 批量处理时使用并行
   - 选择合适的模型（平衡速度与质量）

4. **质量控制**：
   - 生成后人工审核
   - 建立质量评估标准
   - 迭代优化 Prompt

---

## 📄 许可证

本模块是 EduAgent 项目的一部分，仅供学习和研究使用。

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**DocuAgent** - 让文档填充更智能、更可靠！ 🚀✨



