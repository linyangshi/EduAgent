# AI文档编辑器 - 独立模块

AI驱动的智能文档编辑器，可独立运行或集成到其他Flask项目中。

## 功能特性

- 🎯 **Tab键智能续写** - 按Tab键自动补全内容
- 🔮 **@@@指令生成** - 输入`@@@教学目标`回车即可生成
- 💬 **AI对话助手** - 侧边栏聊天，支持内容生成
- ✏️ **选中重写** - 选中文本，AI帮你优化改写
- 📄 **DOCX支持** - 上传Word文档，保留格式编辑

## 快速开始

### 1. 安装依赖

```bash
cd ai_editor_standalone
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 必须: LLM API密钥 (二选一)
export DASHSCOPE_API_KEY="sk-xxx"   # 通义千问
# 或
export LLM_API_KEY="sk-xxx"         # 其他OpenAI兼容接口

# 可选: 自定义LLM配置
export LLM_API_URL="https://api.openai.com/v1/chat/completions"
export LLM_MODEL="gpt-3.5-turbo"
```

### 3. 运行

```bash
python app.py
```

访问 http://localhost:5030

## 集成到其他项目

### 方式一：注册蓝图

```python
from flask import Flask
from ai_editor_standalone import editor_bp
from ai_editor_standalone.app import register_routes

app = Flask(__name__)

# 注册编辑器API蓝图
app.register_blueprint(editor_bp)

# 注册AI相关路由
register_routes(app)
```

### 方式二：使用工厂函数

```python
from ai_editor_standalone import create_app

app = create_app({
    'SECRET_KEY': 'your-secret-key',
    'MAX_CONTENT_LENGTH': 50 * 1024 * 1024
})
```

## 目录结构

```
ai_editor_standalone/
├── app.py              # Flask应用入口
├── requirements.txt    # 依赖包
├── README.md           # 说明文档
├── __init__.py         # 模块入口
│
├── templates/
│   └── ai_editor.html  # 编辑器页面
│
├── static/
│   ├── js/
│   │   └── ai_editor.js    # 前端逻辑 (1400+行)
│   └── css/
│       └── ai_editor.css   # 样式文件 (1400+行)
│
├── editor/
│   ├── __init__.py
│   ├── api.py          # 编辑器API蓝图
│   └── session.py      # 会话管理
│
├── utils/
│   ├── __init__.py
│   └── llm_call.py     # LLM调用工具
│
├── editor_sessions/    # 编辑会话存储 (自动创建)
└── uploads/            # 临时上传目录 (自动创建)
```

## API接口

### 编辑器API (`/api/editor/`)

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/editor/new` | POST | 创建新文档 |
| `/api/editor/upload` | POST | 上传DOCX文件 |
| `/api/editor/document/<id>` | GET | 获取文档内容 |
| `/api/editor/document/<id>` | PUT | 保存文档变更 |
| `/api/editor/export/<id>` | POST | 导出DOCX |
| `/api/editor/download/<id>/<file>` | GET | 下载文件 |

### AI功能API (`/api/ai/`)

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/ai/chat` | POST | 聊天/内容生成 |
| `/api/ai/complete` | POST | Tab键自动补全 |
| `/api/ai/generate-placeholder` | POST | @@@指令生成 |
| `/api/ai/rewrite` | POST | 文本重写 |

## LLM配置

默认使用通义千问，也支持其他OpenAI兼容接口：

```python
# utils/llm_call.py 中的配置
LLM_API_KEY = os.environ.get('LLM_API_KEY', os.environ.get('DASHSCOPE_API_KEY', ''))
LLM_API_URL = os.environ.get('LLM_API_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions')
LLM_MODEL = os.environ.get('LLM_MODEL', 'qwen-plus')
```

支持的后端：
- 通义千问 (DashScope)
- OpenAI
- Azure OpenAI
- 其他OpenAI兼容API

## 完整DOCX功能

简化版仅支持新建文档和基础编辑。如需完整的DOCX解析和导出功能，需要添加原项目的`docuagent.v4`模块：

1. 复制 `docuagent/v4/` 目录到项目中
2. 安装 `python-docx` 包
3. 重启应用

## 注意事项

1. **会话存储**: 编辑会话默认存储在 `editor_sessions/` 目录
2. **文件大小**: 默认限制50MB，可通过 `MAX_CONTENT_LENGTH` 配置
3. **并发**: 生产环境建议使用 gunicorn 或 uwsgi

## License

MIT
