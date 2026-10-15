# LingoPath backend（共享层）

Python + Django + django-ninja。这里只有五个 agent 共用的部分：领域模型、Agent Runtime、编排、升级、审计、API 网关和 RBAC。各 agent 的逻辑由负责人在 `agents/<id>/` 和 `orchestration/coordinator/` 中实现。

- **共享层规范**（agent 负责人必读）：[docs/shared-conventions.md](docs/shared-conventions.md)

## 运行

需要 Python 3.11 及以上。

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # macOS/Linux 用 .venv/bin/pip
.venv/Scripts/python run_demo.py                      # migrate → load_demo_data → runserver
```

启动后打开 OpenAPI 文档 http://127.0.0.1:8000/api/v1/docs。重置数据用 `python manage.py load_demo_data --reset`。

演示账号的密码都是 `demo1238`：

- `ivy.lin@example.com`、`sophia.chen@example.com`（学生）
- `emily.walker@example.com`（教师）
- `alex.hu@example.com`（Founder）

前端要连这个后端，在 `frontend/.env.local` 里设 `VITE_USE_MOCK_API=false` 和 `VITE_API_BASE_URL=http://localhost:8000/api/v1`。

| 命令 | 作用 |
|---|---|
| `python -m pytest` | 全部测试（不调用真实 LLM，不需要 API key） |
| `python manage.py run_agent_worker` | `AGENT_TASK_EXECUTION=worker` 时的串行 worker |
| `python manage.py ingest_materials` | 导入检索语料（`RETRIEVAL_BACKEND=none` 时不做任何事） |
| `python manage.py check_llm` | 测试当前 LLM 接口支持哪些能力，并给出 `LLM_CAPABILITIES` 的建议值 |
| `python manage.py makemigrations --check` | 检查模型改动是否都有 migration |

## 配置

全部从环境变量读取。复制 `.env.example` 为 `.env` 后填写（`.env` 不提交，也不放进上传到 Canvas 的源码包）。常用项：

- `LLM_PROVIDER`：`fake`（离线）或 `openai`（任何 OpenAI 兼容接口，`school` 是它的别名）。用 `openai` 时还要填 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL_*`，见下一节。
- `AGENT_TASK_EXECUTION`：`inline`（默认，同步返回）或 `worker`。
- `RETRIEVAL_BACKEND`：目前只实现了 `none`。
- `CORS_ALLOWED_ORIGINS`：前端开发服务器的地址。
- `INTAKE_TEACHER_EMAIL`：学生还没有教师时，学习类复核交给这位教师。

## 切换 LLM 接口

agent 只通过 runtime 调用 LLM，换接口只改 `.env`，不改代码。`.env.example` 里有两套示例：

- **Google Gemini**（开发和云端默认）：用 AI Studio 的免费 key，走 Gemini 的 OpenAI 兼容端点，在哪里都能访问。
- **ELEC5620 课程代理**（`campus-qwen`）：必须先连 USYD VPN，云端主机访问不到。

改完运行 `python manage.py check_llm`。它会逐项测试纯文本、JSON schema 输出和工具调用，并打印 `LLM_CAPABILITIES` 应该填的值。接口不支持的能力，runtime 会自动改用提示词要求输出 JSON，agent 代码不用改。

**数据外发**（规范 8.6）：

- 发给外部接口的只有完成任务必需的字段，不发送姓名和邮箱。
- Gemini 免费层的输入可能被 Google 用于改进产品，这一点要写进报告。
- API key 只放在 `.env` 里，不进仓库，也不进 Canvas 源码包。

## 部署（只做到能部署）

运行时依赖只有 Django 和 django-ninja，云端再加 gunicorn，不需要 Docker。

- **Cloud Run**：仓库自带 `Procfile`，可以用 `gcloud run deploy --source backend` 直接部署（buildpacks）。这一步还没有在云端实测。上线时设置 `DJANGO_DEBUG=false`、`DJANGO_SECRET_KEY`、`DJANGO_ALLOWED_HOSTS`、`CORS_ALLOWED_ORIGINS`。
- **SQLite 在 Cloud Run 上不持久**：实例重启后数据回到演示数据，多实例之间也不共享，所以要把实例数上限设为 1。需要持久化时，设置 `DATABASE_URL=postgresql://…` 并另外安装 `psycopg`。

## 目录

```
config/            settings（环境变量）、urls、wsgi/asgi
access_control/    gateway（API、认证、错误、CORS、presenters）、identity（User、RBAC、load_demo_data）
orchestration/     task_queue（dispatcher、pipelines、contracts、worker）、escalation、audit、coordinator（← 负责人）
agents/            runtime（共享）、assessment / planning / teaching_support / tech_operations（← 负责人）
domain/            common、learning、governance（models / selectors / services / views）
infrastructure/    llm、retrieval、scheduling、monitoring
fixtures/          demo_*.json（演示数据）
tests/             runtime、domain、pipeline、api、layers；stub_agents.py 是测试替身
```
