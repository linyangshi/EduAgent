# DocuAgent - GitCode 集成使用说明

> 使用 GitCode API 和 Qwen/Qwen3-30B-A3B 模型

---

## 🎯 快速开始

### 1. 确认配置

确保在 `config/settings.py` 中已配置 GitCode API Key：

```python
GITCODE_API_KEY = "your-gitcode-api-key"
```

### 2. 安装依赖

```bash
pip install openai  # GitCode 使用 OpenAI 兼容的 API
```

### 3. 基本使用

```python
from docuagent import DocuAgent

# 初始化 - 使用 GitCode
agent = DocuAgent(provider="gitcode")

# 处理模板
output = agent.process(
    template_path="教案模版.docx",
    user_instruction="生成一份关于深度学习的教案",
    output_path="output.docx"
)

print(f"完成！文件：{output}")
```

---

## 📋 与通义千问的区别

| 特性 | GitCode | 通义千问 |
|------|---------|----------|
| **模型** | Qwen/Qwen3-30B-A3B | qwen-plus/qwen-turbo |
| **Max Tokens** | 131,072 (128k) | 默认值 |
| **流式输出** | 支持 | 支持 |
| **API 格式** | OpenAI 兼容 | 阿里云 DashScope |
| **配置方式** | `provider="gitcode"` | `provider="tongyi"` |

---

## 🧪 测试脚本

我们提供了专门的测试脚本：

```bash
# 测试 GitCode 集成
python test_docuagent_gitcode.py
```

测试包括：
1. ✅ XML 提取测试
2. ✅ LLM 初始化测试
3. ✅ Schema 识别测试
4. ✅ Content Planning 测试

---

## 📚 使用示例

### 示例 1: 基础使用

```python
from docuagent import fill_template

fill_template(
    template_path="template.docx",
    user_instruction="生成Python教案",
    output_path="output.docx",
    provider="gitcode"  # 指定使用 GitCode
)
```

### 示例 2: 自定义模型

```python
from docuagent import DocuAgent

agent = DocuAgent(
    provider="gitcode",
    model_name="Qwen/Qwen3-30B-A3B"  # 可以指定其他模型
)

output = agent.process(
    template_path="template.docx",
    user_instruction="生成教案",
    output_path="output.docx"
)
```

### 示例 3: 运行示例文件

```bash
cd docuagent
python example.py
# 选择选项 6: 使用 GitCode API (Qwen3-30B-A3B)
```

---

## 🔧 配置选项

### DocuAgent 初始化参数

```python
agent = DocuAgent(
    provider="gitcode",           # 使用 GitCode API
    model_name="Qwen/Qwen3-30B-A3B",  # 可选，默认值
    cache_dir="./cache"           # 缓存目录
)
```

### API 配置方式

**方式 1: config/settings.py (推荐)**
```python
GITCODE_API_KEY = "your-api-key"
```

**方式 2: 环境变量**
```bash
export GITCODE_API_KEY="your-api-key"
```

---

## 💡 优势

1. **强大的模型能力**: Qwen3-30B-A3B 是目前最先进的开源模型之一
2. **大 Token 上下文**: 支持 128k tokens，可以处理超长文档
3. **流式输出**: 实时生成，提升用户体验
4. **OpenAI 兼容**: 标准化的 API 接口，易于集成

---

## ⚠️ 注意事项

1. **API Key**: 确保 GitCode API Key 已正确配置
2. **网络连接**: 需要能够访问 GitCode API 端点 (https://api.gitcode.com/v1)
3. **依赖包**: 确保已安装 `openai` 包

---

## 🐛 问题排查

### 问题 1: API Key 错误

```
❌ 未找到 GITCODE_API_KEY
```

**解决方法**: 在 `config/settings.py` 中添加：
```python
GITCODE_API_KEY = "your-api-key"
```

### 问题 2: 缺少依赖

```
❌ 请安装 openai: pip install openai
```

**解决方法**:
```bash
pip install openai
```

### 问题 3: 网络连接失败

**解决方法**: 
- 检查网络连接
- 确认能访问 https://api.gitcode.com
- 检查防火墙设置

---

## 📞 支持

如有问题，请：
1. 查看 `docuagent/README.md` 获取详细文档
2. 运行测试脚本诊断问题
3. 查看代码中的详细注释

---

## 🎉 更新日志

**v1.0 (2025-11-07)**
- ✅ 添加 GitCode API 支持
- ✅ 集成 Qwen/Qwen3-30B-A3B 模型
- ✅ 支持流式输出 (128k tokens)
- ✅ 提供完整测试脚本
- ✅ 更新文档和示例

---

**祝使用愉快！** 🚀

