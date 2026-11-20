# EduAgent 智教创想

EduAgent 是面向教学文档的开源工具。教师可以上传 Word 模板，输入课程主题或写作要求，生成教案、任务书或报告，并在浏览器中编辑和导出 DOCX。生成流程会识别模板中的段落与表格，按字段组织内容，再将结果写回文档。

## 本地运行

本地示例使用 Python 3.11 和 macOS / Linux shell。先克隆仓库，再创建虚拟环境。

```sh
git clone https://github.com/linyangshi/EduAgent.git
cd EduAgent
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -c 'import secrets; print(secrets.token_hex(32))'
```

把生成的随机值填入本机 `.env` 的 `SECRET_KEY`。使用默认通义千问生成文档时，还需填写你自己的 `DASHSCOPE_API_KEY`。如使用 Fireworks 模型，还需执行 `python -m pip install fireworks-ai`。邮件验证码、第三方登录和其他模型的可选参数见 `.env.example`。提交给在线模型的文档内容将发送至你配置的服务商。

```sh
set -a
. ./.env
set +a
python create_test_user.py
python web_main.py --host 127.0.0.1 --port 5029
```

脚本会提示输入本地测试账户的用户名、邮箱和密码。在浏览器中打开 <http://127.0.0.1:5029>。可访问 <http://127.0.0.1:5029/api/health> 检查 Web 服务。登录后上传自己的 DOCX 模板，填写生成要求并下载结果。使用 PDF 扫描件的 OCR 功能时，还需安装 Poppler、Tesseract 及相应语言包。

## 生成流程

1. 识别文档类型，分析模板的段落、表格和待填写字段。
2. 结合用户要求和本地积累的经验，调用配置的模型生成内容。
3. 将内容写回 Word。训练模式还会调用视觉模型检查文档，并将反思结果写入本机知识库。

| 目录 | 用途 |
| --- | --- |
| `core/` | 文档生成入口和会话逻辑 |
| `docuagent/v4/` | 字段分析、内容生成和 DOCX 重建 |
| `docuagent/v5/`、`docuagent/v6/` | 经验库、视觉检查、并行标注和文档分类 |
| `interface/`、`templates/`、`static/` | Flask 接口、页面与前端资源 |
| `ai_editor_standalone/` | 浏览器内的文档编辑器 |
| `templates_library/` | 可用于试运行的示例模板 |

## 许可证

EduAgent 使用 MIT 许可证。完整条款见 [LICENSE](LICENSE)。
