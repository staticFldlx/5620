# LingoPath

ELEC5620 Model-Based Software Engineering · Wed 14-16 Group 3

LingoPath 是一个由 LLM agent 驱动、由一位创始人运营的个性化英语教育服务。五个 AI 角色承担一所语言学校的咨询、测评、规划、助教和运维工作；人类教师负责上课和最终的学术判断，Founder 负责监督和审批。AI 没有把握的结果一律交给人决定。

## 五个 AI 角色

| Agent | 对应需求 | 主要能力 | 人工把关 |
|---|---|---|---|
| AI Course Coordinator | AR01、AR11；UC01 | 把学生的学习目标整理成结构化目标，信息不够时追问，保存学习档案 | 学生确认后才保存 |
| AI Assessment Agent | AR02、AR05、AR13；UC02、UC05 | 自适应测评：逐题调整难度、规则定级、可解释的置信度 | 低置信结果由教师确认或修正 |
| AI Course Consultant | AR03、AR07；UC03、UC07 | 按档案和测评结果起草分阶段计划，匹配教师，在双方可用时间内排课 | 计划必须教师批准才生效；找不到教师时交给 Founder |
| AI Teaching Assistant | AR04–AR08；UC04–UC08 | 答疑（引用教材）、找资料、练习与反馈、教师侧进度分析、备课摘要、教材草稿 | 敏感或没把握的问题转教师；教材草稿须教师批准 |
| AI Technical Manager | AR09、AR10、AR12；UC09、UC10 | 监控 agent、诊断事故、把 Founder 的纠正请求整理成变更提案并执行 | 所有变更和恢复都要 Founder 批准 |

学生入学的闭环：Coordinator 建档 → Assessment Agent 测评 → Course Consultant 起草计划 → 教师批准 → 计划生效并排课 → Teaching Assistant 日常辅导 → 阶段测评后重新规划。

## 仓库结构

| 目录 | 内容 |
|---|---|
| [`backend/`](backend/README.md) | Python + Django + django-ninja：API、五个 agent、任务编排、复核与审批、审计、权限、演示数据和测试 |
| [`frontend/`](frontend/README.md) | React + TypeScript + Vite：学生、教师、Founder 三种角色的 18 个页面 |
| `.github/workflows/ci.yml` | GitHub Actions：前端构建，后端迁移检查和全部测试（不调用真实 LLM） |

## 快速开始

需要 Python 3.11+ 和 Node.js 22.12+。以下命令以 Windows 为例；macOS / Linux 把 `.venv\Scripts\` 换成 `.venv/bin/`，`copy` 换成 `cp`。

**1. 后端**（终端一）

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env
.venv\Scripts\python run_demo.py
```

默认 `LLM_PROVIDER=fake`，不需要 API key 就能走完全部流程。要接真实模型（Gemini 或课程代理），见后端 README 第 2 节。

**2. 前端**（终端二）

```bash
cd frontend
npm install
```

新建 `frontend/.env.local`：

```dotenv
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

然后运行 `npm run dev`，打开 http://localhost:5173/ 。

**3. 登录**：演示账号的密码都是 `demo1238`，登录页可以一键填入。

| 角色 | 邮箱 | 首页 |
|---|---|---|
| 学生 | `ivy.lin@example.com`、`sophia.chen@example.com` | `/s1` |
| 教师 | `emily.walker@example.com` | `/t1` |
| Founder | `alex.hu@example.com` | `/f1` |

也可以在登录页注册新的学生账号，从设定学习目标开始体验完整的入学流程。

**重置演示数据**：在 `backend` 目录运行 `.venv\Scripts\python manage.py load_demo_data --reset`。

## 更多说明

- [后端 README](backend/README.md)：配置、命令、架构、五个 agent 的工作方式、API、演示数据、测试和部署。
- [前端 README](frontend/README.md)：运行方式、连接后端、离线演示模式、页面列表。
- [Render 部署说明](docs/render-deployment.md)：单个 Web Service 同时提供前端与 API，连接持久化 PostgreSQL。
