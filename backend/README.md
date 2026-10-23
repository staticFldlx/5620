# LingoPath 后端

Python + Django + django-ninja 实现的 API 服务，包含五个 AI agent、任务编排、人工复核与审批、审计和权限控制。前端通过 `/api/v1` 调用。

## 1. 运行

需要 Python 3.11 及以上（CI 用 3.12）。在 `backend` 目录：

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env
.venv\Scripts\python run_demo.py
```

macOS / Linux 把 `.venv\Scripts\` 换成 `.venv/bin/`，`copy` 换成 `cp`。

`run_demo.py` 依次执行 `migrate`、`load_demo_data`（数据库里已有演示数据时跳过），然后在 `127.0.0.1:8000` 启动服务；`AGENT_TASK_EXECUTION=worker` 时还会启动 `run_agent_worker`。可用 `--host`、`--port` 修改地址。

- 接口文档（OpenAPI）：http://127.0.0.1:8000/api/v1/docs
- `.env.example` 默认 `LLM_PROVIDER=fake`：不需要 API key，每个 agent 使用自己的离线脚本，所有流程都能走通。
- 重置演示数据：`python manage.py load_demo_data --reset`（清空数据库后重新导入）。
- 前端如何连接本服务见 [frontend/README.md](../frontend/README.md)。

演示账号的密码都是 `demo1238`：

| 角色 | 邮箱 |
|---|---|
| 学生 | `ivy.lin@example.com`、`sophia.chen@example.com` |
| 教师 | `emily.walker@example.com` |
| Founder | `alex.hu@example.com` |

## 2. 配置

全部配置来自环境变量。`backend/.env` 会被自动读取（进程里已有的环境变量优先）；`.env` 不提交，也不放进上传到 Canvas 的源码包。

| 变量 | 默认 | 说明 |
|---|---|---|
| `DJANGO_SECRET_KEY` | 开发时自动使用不安全的默认值 | `DJANGO_DEBUG=false` 时必须设置 |
| `DJANGO_DEBUG` | `true` | 部署时设为 `false` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | |
| `DATABASE_PATH` | `db.sqlite3` | SQLite 文件；设置 `DATABASE_URL=postgresql://…` 时改用 PostgreSQL（需另装 `psycopg`） |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | 前端开发服务器的地址；换端口时要加上 |
| `INTAKE_TEACHER_EMAIL` | `emily.walker@example.com` | 学生还没有教师时，学习类复核交给这位教师 |
| `LLM_PROVIDER` | `fake` | `openai`（任何 OpenAI 兼容接口，`school` 是别名）或 `fake` |
| `LLM_BASE_URL`、`LLM_API_KEY` | | `openai` 时必填 |
| `LLM_MODEL_DEFAULT`、`LLM_MODEL_FAST` | | `fast` 档用于评分等低延迟调用，不填时同 default |
| `LLM_TIMEOUT_SECONDS` | `30` | 单次 LLM 调用超时；Technical Manager 可按 agent 单独覆盖（见 5.5） |
| `LLM_CAPABILITIES` | `tools,json_schema` | 接口支持的能力，按 `check_llm` 的输出填写 |
| `AGENT_TASK_EXECUTION` | `inline` | `inline`：在 HTTP 请求里跑完；`worker`：只入队，由 `run_agent_worker` 执行 |
| `TASK_TIMEOUT_SECONDS`、`TASK_MAX_ATTEMPTS` | `120`、`2` | 任务超时后最多重新排队的次数 |
| `AGENT_CONFIDENCE_THRESHOLD` | `0.70` | 全系统唯一的置信度阈值 |
| `TEACHING_SUPPORT_EXPLAIN_MODE` | `single` | Teaching Assistant 答疑：`single`（一次结构化调用）或 `loop`（先用工具查资料） |
| `TEACHING_SUPPORT_LOOP_BUDGET_SECONDS` | `6` | `loop` 模式超过这个时间就不再调用模型 |
| `RETRIEVAL_BACKEND` | `none` | 目前只实现 `none` |

### 切换 LLM 接口

agent 只通过共享的 runtime 调用 LLM，换接口只改 `.env`，不改代码。`.env.example` 里有两套示例：

- **Google Gemini**：AI Studio 的免费 key，走 Gemini 的 OpenAI 兼容端点（`https://generativelanguage.googleapis.com/v1beta/openai`），在哪里都能访问。免费层每个模型每天的请求数很少，开发和测试请用 `fake`。
- **ELEC5620 课程代理**（`campus-qwen`）：必须先连 USYD VPN，云端主机访问不到。

改完运行 `python manage.py check_llm`：它逐项测试纯文本、JSON schema 输出和工具调用，并打印 `LLM_CAPABILITIES` 应填的值。接口不支持的能力，runtime 会自动改为在提示词里要求输出 JSON。

**数据外发**：发给外部接口的只有完成任务必需的字段，不发送姓名、邮箱和用户 id，学生输入只放在 user 消息的标签里并要求模型把它当作数据。Gemini 免费层的输入可能被 Google 用于改进产品。

## 3. 常用命令

| 命令 | 作用 |
|---|---|
| `python -m pytest` | 全部测试（不调用真实 LLM，不需要 API key） |
| `python manage.py load_demo_data [--reset]` | 导入演示数据；`--reset` 先清空数据库 |
| `python manage.py check_llm [--model …]` | 测试当前 LLM 接口支持哪些能力 |
| `python manage.py monitor_agents [--once] [--interval 60]` | Technical Manager 监控：检测异常、诊断新事故（见 5.5） |
| `python manage.py run_agent_worker [--once]` | `AGENT_TASK_EXECUTION=worker` 时的串行 worker |
| `python manage.py ingest_materials` | 导入检索语料（`RETRIEVAL_BACKEND=none` 时不做任何事） |
| `python manage.py makemigrations --check` | 检查模型改动是否都有 migration |

## 4. 架构

### 4.1 分层与目录

```
config/            settings（环境变量）、urls、wsgi/asgi
access_control/    gateway：API 路由、认证、错误、CORS、工作区组装
                   identity：用户、角色、权限、load_demo_data
orchestration/     task_queue：调度器、流水线表、结果契约、管理命令
                   escalation：EscalationManager（复核与审批）
                   audit：审计入口
                   coordinator：AI Course Coordinator
agents/            runtime：共享的 Agent Runtime（LLM 调用、结构化输出、工具循环、置信度、trace）
                   assessment / planning / teaching_support / tech_operations：四个 agent
domain/            learning（学习数据）、governance（任务、复核、审计、事故、提案）
                   每个包分 models / selectors（只读）/ services（写入）/ views（转成前端 JSON）
infrastructure/    llm（OpenAI 兼容适配器、离线 FakeAdapter）、retrieval、scheduling、monitoring
fixtures/          demo_*.json 演示数据
tests/             pytest
```

依赖只能向下：`access_control → orchestration → agents → domain`，agent 之间不能互相 import，`agents.runtime` 不依赖 Django 和 domain，只有 `infrastructure` 可以访问网络。`tests/test_layers.py` 会检查这些规则。

数据写入一律经过 `domain/*/services.py`：每个模型声明哪些 agent 或角色可以写（`WRITERS`），写入时自动检查并记审计。

### 4.2 一次请求怎么走

1. **网关**（`access_control/gateway`）：Bearer token 认证（签名 token，默认 7 天有效）、角色检查、学生数据的访问检查、按 `contracts.py` 校验输入。
2. **调度器**（`orchestration/task_queue/dispatcher.py`）：按流水线表（`pipelines.py`）建立 ServiceRequest 和第一个 AgentTask；前置检查不通过时返回 409。
3. **agent 执行**：调度器按 `settings.AGENT_REGISTRY` 加载 agent，交给它一个共享 runtime，再按返回的 `AgentStatus` 处理：

| agent 返回 | 请求状态（前端看到的） | 调度器的处理 |
|---|---|---|
| `OK` | `completed` | 执行流水线下一步；没有下一步就合并各步结果并按契约校验。置信度低于阈值的 OK 视为需要复核 |
| `TRIGGER_REPLAN` | `completed` | 在下一步插入 `planning.revise_plan`（每个请求最多一次） |
| `NEEDS_INPUT` | `awaiting_confirmation` | 等用户回答；用户用 `context_id` 回复后，交回同一个 task_type 继续 |
| `NEEDS_ESCALATION` | `escalated` | 开复核 case，交给教师或 Founder |
| `AWAITING_APPROVAL` | `pending_review` | 开审批 case；批准前不执行任何变更 |
| `FAILED` | `failed`（HTTP 422） | 请求失败，错误码取 agent 的原因码 |

保护措施：每个请求内 agent 交接最多 6 次；agent 抛出未捕获的异常记为 `unhandled_exception`；超时任务按 `TASK_MAX_ATTEMPTS` 重新排队。

### 4.3 复核与审批（EscalationManager）

所有升级和审批都经过 `orchestration/escalation/manager.py`，全系统使用同一个阈值和同一套分派规则：

- 测评结果、学习计划、学生问题交给学生当前（或待审计划上）的教师；学生还没有教师时交给 `INTAKE_TEACHER_EMAIL`。
- 业务异常、变更提案交给 Founder。
- 教师可选的动作：计划 `approve` / `request_changes`；测评 `confirm_result` / `request_changes`（可附修正等级）；问题 `answer` / `request_changes`。决定必须附说明。
- 决定后，调度器按 case 记录的 `resume` 任务继续原来的流程（例如批准计划后执行 `planning.activate_plan`）。
- 提案审批绑定版本号；拒绝必须写理由；批准后由 Technical Manager 执行并验证。

### 4.4 审计与 trace

- 每次写入、请求和任务状态变化、人工决定都会写一条只追加的审计（AuditLog 不能修改或删除），同时以一行 JSON 输出到 stdout。
- agent 用 `runtime.note()` 记录决策理由，LLM 调用的模型、token 和耗时也会自动记录。Founder 和请求发起人可以用 `GET /api/v1/requests/{id}/trace` 查看每一步。

## 5. 五个 agent

每个 agent 都继承 `agents.runtime.AIAgent`，用 `task_types` 声明能处理的任务。`LLM_PROVIDER=fake` 时调度器使用 agent 自带的 `fake_script()`，离线结果可重复。

### 5.1 AI Course Coordinator（`orchestration/coordinator/`）

学生的第一个联系人：把学习目标整理成结构化目标，保存学习档案（UC01）。

| task_type | 做什么 |
|---|---|
| `coordinator.collect_goal` | 读取目标原文、所选技能、已有档案和之前的问答，一次结构化调用判断信息是否足够：需要知道学习目的和每周可上课时间。不够就追问一个问题（最多 2 次，`NEEDS_INPUT`，`phase=follow_up_question`）；够了就给出摘要（以 Academic English / Workplace English / Exam preparation / Everyday English 开头，供 Consultant 匹配教师）。这一步不写数据库 |
| `coordinator.confirm_goal` | 保存学生确认的目标、摘要、技能、每周时数和等级；追问中得到的上课时间和学习需求一并写入，学生没选技能时使用 Coordinator 建议的技能。还没有已确认测评时返回 `phase=initial_assessment_next`，提示去做入学测评 |
| `coordinator.record_material_completion` | 在学习记录里记一次教材完成（重复提交不重复记录） |

模型不可用时，摘要直接使用学生原文，请求不会失败。原因码：`invalid_goal`、`student_not_found`、`material_not_found`。路由本身由流水线表按请求类型决定（前端每个按钮都发送明确的类型），没有用 LLM 分类。

### 5.2 AI Assessment Agent（`agents/assessment/`）

自适应测评（UC02 入学测评、UC05 阶段测评、UC06 教师定向测评）。

| task_type | 做什么 |
|---|---|
| `assessment.conduct_assessment` | 每出一题返回 `NEEDS_INPUT`，学生作答（`POST /assessments/{id}/answers`）后交回同一任务。结束时发布结果（`OK`，交给 Consultant）或转教师复核 |
| `assessment.apply_review` | 教师确认 / 修正等级后发布；教师要求重测时以 `FAILED assessment_changes_requested` 结束，结果不进入计划 |

- **选技能和起点**：学生的重点技能优先；前端只有文本框，听、说、发音用书面代理（写作、阅读、词汇）测。起始等级：入学用自报等级，阶段 / 定向测评用最近一次确认的等级，都没有时用 B1。
- **出题和评分**：每次生成一道题；LLM 从两个角度评分（按 rubric 打分 + 判断回答体现的 CEFR 等级）并取平均，分数接近升降阈值时再独立评一次。空白、离题或试图指挥模型的回答记 0 分。出题失败时改用内置题库，测评不会中断。
- **难度和停止**：分数 ≥ 0.75 升一级、< 0.4 降一级；至少 4 题且最近 3 次能力估计相差不超过 0.75 级时停止，最多 6 题。
- **等级和置信度**：等级由规则计算，LLM 只写优势、弱项和反馈。置信度不用模型自报，由三个信号加权：稳定性 0.5、评分一致性 0.25、覆盖度 0.25。低于阈值（`low_confidence`），或一半以上回答空白 / 离题（`insufficient_evidence`）时转教师复核。
- 提示词带版本号（`assessment.generate_item.v1`、`assessment.score_answer.v2`、`assessment.report.v1`）。

### 5.3 AI Course Consultant（`agents/planning/`）

生成和调整个性化学习计划，匹配教师，安排课程（UC03、UC07）。

| task_type | 做什么 |
|---|---|
| `planning.generate_plan` | 测评确认后自动执行。没有计划时起草初始计划；已有计划时，新的测评结果触发重新规划（`TRIGGER_REPLAN`）；已有草稿在等审批时直接完成，不再起草 |
| `planning.revise_plan` | 学生或教师给出理由（或测评结果）后起草新版本；当前计划保持有效 |
| `planning.activate_plan` | 教师批准后激活计划，并在每个阶段开始的那一周预订一节课；教师要求修改时生成修正版本再次送审 |
| `planning.match_teacher` | 为更换教师准备新计划；找不到合适教师时交给 Founder |
| `planning.propose_slot` / `planning.book_slot` | 学生改课时：检查冲突，冲突时给出可选时间，学生确认后再改 |

- **起草**：一次结构化调用，输入学生档案、已确认的测评、课程目录（通过只读工具读取）、上一版计划和修改理由；输出分阶段计划。代码再校验每周时数不超过预算、阶段连续、课程真实存在、先修课程在更早的阶段。
- **匹配教师**：候选是学生当前的教师和接待教师，按教师 `subject_areas` 与学习目标的关键词匹配；没有匹配时交给 Founder（`teacher_unavailable`），Founder 选 `widen_match` 后放宽条件。
- **排课**：只在学生和教师的每周可用时间内找时间，并用 `check_lesson_slot` 检查冲突（NFR-03）；都排不下时给学生几个可选时间（`NEEDS_INPUT`）。
- 计划先以 `pending_review` 保存，必须由教师批准才生效（`AWAITING_APPROVAL`）。

### 5.4 AI Teaching Assistant（`agents/teaching_support/`）

答疑、资料、练习、给教师的分析和备课（UC04–UC08）。没有向量检索：资料就是学生当前计划阶段里已批准的教材，正文直接放进提示词。

| task_type | 前端入口 | 做什么 |
|---|---|---|
| `answer_question` | `/s6` 提问 | 按学生等级回答并引用教材；没把握时转教师 |
| `retrieve_material` | `/s6` 找资料 | 当前阶段教材按问题排序，并写一段使用指引；没有教材时记 `corpus_gap` 审计 |
| `generate_practice` / `give_feedback` | `/s6` 练习 | 按当前阶段和弱项出一道短练习，提交后即时反馈；不改测评和计划 |
| `analyze_progress` / `recommend_adjustments` | `/t2` | 给教师的进度分析（列出缺失数据，必要时建议定向测评）和 2–4 条计划调整建议 |
| `lesson_briefing` / `generate_material` | `/t5` | 课前摘要；生成教材草稿，教师批准后学生才能看到 |

- **答疑置信度** = 模型自评 0.5 + 是否引用了提供的教材 0.3 + 是否在学习范围内 0.2。只认真正提供给模型的教材 id。
- **转教师**：敏感问题（许可、版权、学术诚信）、超出范围、置信度低于阈值、模型不可用或输出两次无效。学生先看到“老师会回复”，老师在 `/t4` 回答后自动替换。
- **两种模式**：`single` 一次调用；`loop` 先让模型用 4 个只读工具查学生情况和教材，超步数或超时间预算时退回 `single`。
- 教师观察、课后反馈和问题里出现的学生姓名会替换成 “the learner”。

### 5.5 AI Technical Manager（`agents/tech_operations/`）

系统监控、诊断、受控更新（UC09、UC10）。所有任务只接受 Founder 或系统发起。

| task_type | 做什么 |
|---|---|
| `tech_operations.apply_correction` | Founder 在 `/f3` 提交纠正请求（一段文字）。LLM 把它整理成变更提案：调整某个 agent 的 LLM 超时（5–120 秒）时生成可执行的配置提案，其他要求生成人工处理提案。返回 `AWAITING_APPROVAL`，批准后在同一请求里执行 |
| `tech_operations.execute_proposal` | 执行已批准的提案：配置更新和回滚（写入并验证超时覆盖值，`registry.runtime_config` 随即生效）；恢复类 `resume_agent`（恢复被暂停的 agent 并验证）；`retry_request` 只记录；其他类型记为 `manual_review`，由人完成 |
| `tech_operations.detect_anomalies` | 由 `monitor_agents` 命令以内部请求 `system_monitoring` 触发：统计最近 7 天每个 agent 的任务（至少 5 个，失败率 ≥ 30% 或平均耗时 > 10 秒）→ 建事故记录 → 对新事故做 LLM 诊断 → 需要恢复时生成恢复提案等 Founder 批准 |
| 其他 | `monitor_agents`、`diagnose_incident`、`generate_report`、`check_student_records`、`check_plan_versions`，供代码和下面的运营接口使用 |

诊断只使用运营数据（任务数、失败率、耗时、agent 状态），不读取学生内容。诊断建议只能是 `retry_request`、`resume_agent`、`request_founder_review`、`no_action` 之一，执行前都要 Founder 批准。

## 6. API

### 6.1 接口

前端使用的 20 个接口：

| 接口 | 调用者 | 说明 |
|---|---|---|
| `POST /auth/register`、`POST /auth/login` | 访客 | 注册只能创建学生；登录返回 `session` token |
| `GET /workspace` | 三种角色 | 按角色返回工作区；教师可带 `student_id` |
| `POST /requests`、`GET /requests/{id}` | 学生、教师 | 发起 agent 请求（类型见 6.2）；回答追问时带上原请求的 `context_id` |
| `POST /assessments`、`GET /assessments/{id}`、`POST /assessments/{id}/answers` | 学生、教师 | 学生发起入学 / 阶段测评，教师发起定向测评 |
| `GET /reviews/{id}`、`POST /reviews/{id}/decision` | 复核负责人 | 计划、测评、问题的人工决定 |
| `PATCH /students/{id}/observation`、`PATCH /teachers/me/availability`、`PATCH /lessons/{id}` | 教师 | 教师观察、可授课时间、出席和课后反馈 |
| `GET /materials/{id}`、`PATCH /materials/{id}` | 学生（只能看已批准的）、教师 | 打开、编辑、批准教材 |
| `GET /cases/{id}`、`POST /cases/{id}/decision` | Founder | 业务异常和技术事故 |
| `POST /agents/{id}/decision` | Founder | `pause`、`resume`、`request_correction` |
| `GET /proposals/{id}`、`POST /proposals/{id}/decision` | Founder | 变更提案的查看和审批 |

另有 `GET /requests/{id}/trace`（决策过程），以及 Technical Manager 的 Founder 运营接口：`GET /agents/health`、`GET /operations/audit-logs`、`GET /operations/incidents/{id}/timeline`、`GET /operations/maintenance-report`、`GET /operations/students/{id}/record-health`、`GET /operations/students/{id}/archive-eligibility`、`POST /operations/configuration/{id}/execute`、`POST /operations/configuration/{id}/rollback`。对外的 agent id 为 `coordinator`、`assessment`、`consultant`、`assistant`、`technical`。

### 6.2 请求类型与流水线

`POST /requests` 的 `type` 决定由哪些 agent 按什么顺序处理（`orchestration/task_queue/pipelines.py`）：

| type | 发起者 | 流水线 | 结果主要字段 |
|---|---|---|---|
| `collect_goal` | 学生 | `coordinator.collect_goal` | `summary`、`focus_skills`，或追问的 `question` |
| `confirm_goal` | 学生 | `coordinator.confirm_goal` | `profile` |
| `complete_material` | 学生 | `coordinator.record_material_completion` | `material` |
| `explain` / `resources` | 学生 | `teaching_support.answer_question` / `retrieve_material` | `interaction` |
| `practice` / `practice_answer` | 学生 | `teaching_support.generate_practice` / `give_feedback` | `question` / `feedback` |
| `revise_plan` | 学生、教师 | `planning.revise_plan` → 教师审批 → `planning.activate_plan` | `plan`、`review_id` |
| `reschedule` / `confirm_slot` | 学生 | `planning.propose_slot` / `planning.book_slot` | `slots` / `lesson` |
| `replace_teacher` | 学生 | `planning.match_teacher` | `plan` 或 `message` |
| `review_progress` / `recommend_plan` | 教师 | `teaching_support.analyze_progress` / `recommend_adjustments` | `recommendation`、`evidence` |
| `lesson_briefing` / `generate_material` | 教师 | `teaching_support.lesson_briefing` / `generate_material` | `briefing` / `material` |
| `start_assessment`（`POST /assessments`） | 学生、教师 | `assessment.conduct_assessment` → `planning.generate_plan` | `session_id` |
| `agent_correction`（内部） | Founder | `tech_operations.apply_correction` → 审批 → `execute_proposal` | 提案 |
| `system_monitoring`（内部） | 系统 | `tech_operations.detect_anomalies` | 检测和诊断结果 |
| `decision_follow_up`（内部） | 教师、Founder | 人工决定后的 resume 任务 | 不限 |

### 6.3 错误

错误体统一为 `{"message": "…", "error": {"code": "…", "message": "…", "request_id": "…"}}`。状态码：400 入参错误、401 未登录、403 无权限、404 不存在、409 状态冲突（例如已有待审计划）、422 请求已执行但失败（body 里另带 `request` 信封）、500 未预期的错误。

## 7. 演示数据

`load_demo_data` 按文件名顺序导入 `fixtures/demo_*.json`；记录的 `key` 会转成固定的 uuid5，所以每次导入的 id 都一样。

| 文件 | 内容 |
|---|---|
| `demo_01_accounts.json` | 四个账号；Emily 的科目为 Academic English、Workplace English，可授课时间为周二、周四 18:00–20:00 和周六 17:00–18:00（悉尼时间） |
| `demo_02_catalogue.json` | 两组课程（学术 CAT-01–04、职场 WORK-1–4，含先修关系）和两份教材 |
| `demo_03_students.json` | Ivy：B2，已有生效的计划 v1 和一份待审的 v2、一次待复核的阶段测评、一个已升级的问题、两份已批准教材。Sophia：B1，初始计划待审 |
| `demo_04_operations.json` | 运行日志、四个待处理复核（RV-019-v2、RV-021、RV-A104、RV-Q09）、两个业务异常（ES-12、ES-13）、两个技术事故（IN-014、IN-012）、三个变更提案（UP-07 语料、UP-08 恢复、UP-09 配置） |

## 8. 测试

`python -m pytest` 运行全部测试，共 202 个，使用 fake LLM，不需要 API key：

- `test_layers.py`：分层规则；`test_runtime.py`、`test_domain.py`、`test_pipeline.py`、`test_api.py`：共享层。
- `test_coordinator.py`、`test_assessment.py`、`test_planning.py`、`test_teaching_support.py`、`test_tech_operations.py`：五个 agent，其中包括从注册到计划生效的完整入学流程。
- 需要只替换某个 agent 时，用 `tests/stub_agents.py` 的 `stubs` fixture 注册测试替身。

GitHub Actions（`.github/workflows/ci.yml`）在每次 push 和 PR 时运行迁移检查和全部测试。

## 9. 部署

运行时依赖只有 Django 和 django-ninja，云端再加 gunicorn（`Procfile`），不需要 Docker。

- **Cloud Run**：可以用 `gcloud run deploy --source backend` 部署（buildpacks）。上线时设置 `DJANGO_DEBUG=false`、`DJANGO_SECRET_KEY`、`DJANGO_ALLOWED_HOSTS`、`CORS_ALLOWED_ORIGINS`。
- **SQLite 在 Cloud Run 上不持久**：实例重启后数据回到演示数据，多实例之间也不共享，所以实例数上限要设为 1；需要持久化时设置 `DATABASE_URL` 使用 PostgreSQL。


### 学生撤回计划修改申请

`GET /workspace` 的 `pending_plan.revision_request` 包含学生提交的 `reason`、
`submitted_at` 和 `can_withdraw`。学生页面展示原始要求及拟议计划，待审期间隐藏重复提交表单。
`POST /api/v1/plans/{id}/withdraw` 仅允许学生撤回自己的待审修改申请；初始计划、教师发起的申请和已决定的版本不可撤回。
撤回保留当前生效计划、已有课程和历史记录，并关闭该申请的审核流程。老师打开旧审核页面也无法再批准。
之后可提交新的版本；版本号继续递增，不复用已撤回的版本号。无需数据库迁移。


### 课程改期时间检查

学生端 `Check slot` 可留空，查询未来 28 天内最多 5 个推荐时段；输入时间时，检查该时间的完整课时是否落在老师每周可用窗口内且没有师生课程冲突。
返回 `requested_available`、`slots`、`message`、`teacher_availability` 和 `teacher_timezone`。不可用时保留原因并提供替代选项，无选项时提示联系老师。
学生选定返回的时段后，使用 `confirm_slot` 的 `slot_request_id` 和 `slot_id` 确认，后端再次检查冲突。编辑输入或切换课程后前端清除旧检查结果。

### UC05：阶段进度与自动里程碑测评

新增迁移 `learning.0002` 仅增加测评与阶段的关联、测评开始时的等级/目标快照及阶段发布请求关联，不清空或回填原有业务记录。

- 老师保存课程记录后，若当前阶段所有未取消课程均已完成且出席为 `attended`，自动发布一次关联该阶段的里程碑测评。没有课程、缺席、仍有未完成课程或非当前阶段都不会触发。
- 同一阶段复用正在进行/等待审核的测评，重复保存反馈不会生成重复测评。教师要求重测后，由学生再次点击开始测评发起新一轮。
- 仅已确认的结果用于进度判断。等级较测评开始时下降至少一个 CEFR 等级，或阶段结业测评未达到阶段目标，会提议修改计划；原计划在新版本批准前保持生效。
- 阶段目标优先读取 milestone 中明确的 CEFR 等级；没有时采用关联课程的最高等级，再回退到计划依据的已确认等级。该目标在发布测评时保存，并在学生计划页展示。没有有效等级信息时默认 B1。
- 达标且没有等级退步：阶段标为 `completed`、下一阶段标为 `current`，计划版本不变；最后一个阶段达标后计划标为 `completed`，学生工作区仍可查看完成记录。
- 普通阶段中途/教师定向测评可以判断等级退步，但不代替关联当前阶段的结业测评。旧版本或已完成阶段的迟到结果不会推进当前阶段。
- 进度决定写入 `progress_decision` 学习历史。自动请求与原有测评、低置信审核、计划审批共用调度流程，支持 inline 和 worker。

回归测试：`pytest tests/test_learning_progress.py tests/test_planning.py`。测试使用独立测试数据库和离线模型。
