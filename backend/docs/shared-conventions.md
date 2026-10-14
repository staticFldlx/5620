# 后端共享层规范（已落地版）

> 对应《后端共享规范（Django）》第 3、4、5 节，以及第 6–9 节中已经写成代码的部分。本文以 `backend/` 的实际代码为准；规范与前端代码冲突时以前端为准，冲突裁决见[附录 A](#附录-a与规范和-stage-1-报告的偏离)。
>
> 面向五个 agent 的负责人：读完本文就能写自己的 agent，不需要改共享层。需要改共享层（模型字段、流水线表、契约）时提 PR。

## 0. 分工与分层

| 共享层（已实现） | 各 agent 负责人 |
|---|---|
| 领域模型、selectors / services / views（`domain/`） | agent 内部调用链、循环和终止条件 |
| Agent Runtime（`agents/runtime/`）、LLM 适配器（`infrastructure/llm/`） | 提示词、专有工具、结构化输出 schema |
| Task Orchestrator、EscalationManager、Audit（`orchestration/`） | `classify_request` / `consolidate_response`（Coordinator 负责人） |
| API 网关、认证与 RBAC（`access_control/`） | 自己的 fixtures 和测试 |
| 检索接口（只实现 `none` 档位）、配置、错误、测试、启动 | — |

分层（Fig 24），由 `tests/test_layers.py` 强制检查：

- `access_control → orchestration → agents → domain`，只能向下 import。
- agent 之间不能互相 import。agent 包只能依赖：
  - `agents.runtime`
  - `domain.common`
  - `domain.*.{selectors, services, views, models}`
  - `infrastructure.retrieval`
- `agents.runtime` 不 import Django 和 domain，单元测试不需要数据库。
- 只有 `infrastructure` 可以使用网络库（urllib.request、requests、SDK 等）。

---

## 1. 数据模型（规范第 3 节）

字段以 Fig 6b/6c 为准，命名用 snake_case。所有模型继承 `domain.common.DomainModel`：主键为 UUID，自带 `created_at`、`updated_at` 和 `WRITERS`。

### 1.1 LearningDomain（`domain/learning`）

| 模型 | Stage 1 字段 | 补充字段 | 写入方 |
|---|---|---|---|
| LearningProfile | learning_goal、english_level、preferences、learning_needs | student（1:1）；structured_objective `{summary, focus_skills[], target_level}`；preferences 中存 `{weekly_hours, timezone, availability[]}` | coordinator、role:student |
| AssessmentSession | type、difficulty、status | student、items、requested_by、focus、max_items、started_at、completed_at | assessment |
| ProficiencyProfile | overall_level、strengths、weak_areas、gap_to_goal、confidence；`is_low_confidence()` | session（1:0..1）、reviewed_by、status、feedback、review_note | assessment |
| Course | — | code、title、skill、level、prerequisites（自关联）、materials | tech_operations、role:founder |
| LearningPlan | version、status、weekly_hours | student、teacher、based_on、previous_version、rationale（必填，NFR-04）、approved_by、approved_at、stage_index（从 0 开始）；每个学生最多一个 active | planning |
| PlanStage | stage_number（从 1 开始）、milestone、status | plan、title、topics[]、start_week、end_week、courses、materials | planning |
| AvailabilitySlot | — | teacher、day（Mon..Sun）、start_time、end_time：**每周循环窗口** | role:teacher |
| Lesson | status | student、teacher、stage、title、starts_at、ends_at、classroom_url、attendance | planning、role:teacher（只写出席） |
| LessonMaterial | — | lesson、title、locator、content、citations、status（draft / approved）、approved_by | teaching_support（草稿）、role:teacher |
| TeacherComment | — | teacher、student、lesson（可空）、kind（lesson_feedback / observation）、text | teaching_support、role:teacher |
| LearningMaterial | title、type、source、difficulty_level | file、source_type、license、url、content_hash、stage_topics | tech_operations |
| Conversation / ChatMessage | — | 规范 3.1 的字段 | coordinator（ChatMessage 另加 role:student） |
| LearningHistoryEntry | — | student、source_agent、kind、payload、confidence、escalated。**只追加**，source_agent 自动等于写入的 agent | coordinator、assessment、planning、teaching_support |

### 1.2 GovernanceDomain（`domain/governance`）

| 模型 | 说明 | 写入方 |
|---|---|---|
| ServiceRequest（补充） | 一次请求（SM1），即前端信封 `GET /requests/{id}` 的数据来源 | task_queue |
| AgentTask | 规范字段齐全；`request_id` 是指向 ServiceRequest 的外键 | task_queue |
| EscalationCase | 规范字段，另加 student、subject_type、subject_id、summary、diagnosis、evidence、resolved_by | escalation_manager |
| AuditLog | 只追加。修改或删除会抛 PermissionError（包括 QuerySet.update / delete） | 任何 actor（经 `record_audit`） |
| IncidentRecord | 另加 subject、trigger、evidence、verification | tech_operations |
| UpdateProposal | 另加 title、incident、before、after、validation、rollback、version、decision_note、execution_status、verification | tech_operations；审批结果由 escalation_manager 写 |
| Notification | Fig 5 INotifyHuman；只存储，没有推送通道，也没有未读 API | escalation_manager |
| AgentState（补充） | agent_id、status（healthy / degraded / paused）、note | role:founder、tech_operations |

Goal / Intention / Belief / PlatformEnvironment 不单独建表，对应关系见 `domain/governance/models.py` 文件头。

### 1.3 status 取值

各状态机归写入方的 agent 定义，但下面这些值前端已经在用，要沿用：

- **ProficiencyProfile.status**：`pending_review`、`confirmed`、`changes_requested`。
- **AssessmentSession.status**：前端只有在 `in_progress` 时才显示下一题，结束后可用 `awaiting_review`、`completed`。
- **LearningPlan.status**：`pending_review`、`active`、`changes_requested`；被新版本取代时为 `superseded`。
- **Lesson**：
  - status：`proposed`、`confirmed`、`completed`
  - attendance：`not_recorded`、`attended`、`absent`
- **LessonMaterial.status**：`draft`、`approved`。学生只能看到 approved 的教材。

### 1.4 读写约定

- **只读**：一律走 `selectors.py`，不在业务代码里直接写 `Model.objects`。
- **视图**：`views.py` 把模型渲染成前端 JSON（与 `frontend/src/api/types.ts` 一致），例如 `plan_view`、`lesson_view`、`interaction_view`。agent 组装返回结果时直接用这些函数，不要手写 dict。
- **写入**：一律走 `services.py`，第一个参数是 actor，可以是以下几种：
  - agent id，如 `"planning"`
  - 共享组件 id：`"task_queue"`、`"escalation_manager"`
  - `"system"`：仅限管理命令
  - 已登录的 User：按 `role:<角色>` 匹配
- **写入归属**：services 函数先检查 actor 是否在模型的 `WRITERS` 里，不在就抛 `WriterNotAllowed`（403）；写入成功后自动审计。
- **新增 service**：建议用 `@writes(Model, "action")`（新建）或 `save_fields(actor, obj, action, fields)`（更新），这两个都会自动做写入检查和审计。
- **审计上下文**：`trace_context(request_id=…, task_id=…)` 会把请求号和任务号带进这段代码里写出的每一条审计。Orchestrator 已经替 agent 设置好，agent 不用管。
- **迁移**：migrations 由共享层统一合并。需要新字段时提 PR 改模型，不要在自己的包里定义 model。

---

## 2. Agent Runtime（规范第 4 节）

```python
from agents.runtime import AIAgent, AgentResult, AgentStatus, TaskInput, Message, LoopSpec, ToolSpec

class PlanningAgent(AIAgent):          # 放在 agents/planning/agent.py，类名与 AGENT_REGISTRY 一致
    agent_id = "planning"
    task_types = ("planning.generate_plan", "planning.revise_plan", "planning.activate_plan", ...)

    def execute_task(self, task: TaskInput) -> AgentResult: ...
```

### 2.1 AgentRuntime 方法

| 方法 | 说明 |
|---|---|
| `execute_prompt(system, messages, *, tier="default", tools=None, max_tokens=1024, json_schema=None)` | 一次 LLM 调用。提供方出错时返回 `stop="error"`，不抛异常。模型名、token 和耗时自动写入 trace |
| `structured(system, messages, Schema, *, tier)` | 返回通过 pydantic 校验的对象；校验失败带上错误信息重试 1 次，仍失败返回 `None` |
| `call_tool(name, args)` | 工具抛出的异常、参数不合法都转成 `{"error": ...}` 返回，不往上抛 |
| `run_tool_loop(LoopSpec, messages)` | 通用工具循环：max_steps 上限；相同调用不重复执行；工具错误不中断循环。返回值的 `stopped` 为 `end`、`max_steps` 或 `error` |
| `calculate_confidence(signals, weights=None)` | 把若干 [0,1] 信号做加权平均 |
| `is_low_confidence(c)` | `c < AGENT_CONFIDENCE_THRESHOLD`。阈值全系统只有这一个，不要自己定义第二个 |
| `note(decision, **details)` | 把决策理由写进 trace，供 `GET /requests/{id}/trace` 展示 |
| `embed(texts)` | 仅在适配器声明了 embeddings 能力时可用 |

每次运行都从新的 messages 开始，长期信息从领域模型读取（规范 4.4）。

### 2.2 LLM 适配器

- **FakeAdapter**：按脚本返回结果。脚本的每一步可以是文本、dict（转成 JSON 文本）、`LLMResponse`，或 `tool_call(name, args)`。测试和 CI 都用它。
- **SchoolAdapter**：按 OpenAI 兼容的 `/chat/completions` 协议实现，只用标准库 urllib。
  - 支持超时；遇到 408/409/425/429/5xx 时退避重试 2 次。
  - `max_tokens` 和 `refused` 当失败处理。
  - 用 `LLM_CAPABILITIES` 声明接口支持哪些能力（`tools`、`json_schema`、`embeddings`）。未声明的能力由 runtime 降级为用提示词要求输出 JSON，agent 代码不用改。
- **离线演示**：`LLM_PROVIDER=fake` 时，如果 agent 类定义了 `fake_script(task) -> list`，Orchestrator 会用这份脚本构造 FakeAdapter（规范 8.10 “按预设脚本完整演示”）。
- **测试辅助**：`agents.runtime.testing` 提供 `make_runtime(script, capabilities=...)` 和 `make_task(task_type, payload)`。

---

## 3. 编排（规范第 5 节）

### 3.1 请求生命周期

1. 网关完成认证、RBAC 和入参校验（`contracts.INPUT_CONTRACTS`），然后调用 `dispatcher.submit(type, …)`。
2. 执行流水线的前置检查（precheck，违反时返回 409），新建 ServiceRequest 和第一个 AgentTask。
3. 执行模式：
   - `AGENT_TASK_EXECUTION=inline`（默认）：在本次 HTTP 请求里跑完，直接返回信封。
   - `worker`：只入队，由 `python manage.py run_agent_worker` 串行执行。
4. `run_task` 依次做：
   1. 检查 AgentState 是否为 paused。
   2. 按 AGENT_REGISTRY 导入 agent 类，用同一个 runtime 实例化。
   3. 调用 `execute_task`。
   4. 按 3.3 的表处理返回的 status。
5. 流水线走完后合成结果：Coordinator 实现了 `consolidate_response()` 就调用它；否则把本请求所有成功任务的 `payload["result"]` **按顺序合并**。合成结果再按 `contracts.RESULT_CONTRACTS[type]` 校验，通过后才写进信封。

### 3.2 AgentResult.payload 约定

`payload["result"]` 是给用户看的部分，必须符合该请求类型的契约（见 3.6）。其余键是给 Orchestrator 的控制信息：

| 键 | 何时使用 | 含义 |
|---|---|---|
| `phase` | 任意状态 | 信封里的 `phase`，例如 `follow_up_question`、`student_choose_slot` |
| `subject_type` | NEEDS_ESCALATION / AWAITING_APPROVAL | `assessment`、`plan`、`question`、`business`、`proposal`。不填时按 agent 取默认值：assessment→assessment，planning→plan，teaching_support→question，coordinator→business，tech_operations→proposal |
| `subject_id` | 同上 | 被审核记录的 id：ProficiencyProfile、LearningPlan、LearningHistoryEntry、UpdateProposal 的 id |
| `trigger` | 同上 | 给人看的触发原因。不填时使用 reason |
| `resume` | 同上 | 人做出决定后要继续执行的 task_type。不填表示决定后直接结束这个请求 |
| `route_to` | 同上 | 填 `"founder"` 时强制交给 Founder，例如 UC03 6a 找不到合适教师 |
| `summary` / `diagnosis` / `evidence` | 业务异常 | 显示在 Founder 的 Case 页面上 |
| `message` | FAILED | 给用户看的失败说明 |

### 3.3 按 AgentStatus 处理

| agent 返回 | AgentTask 状态 | 信封 status | Orchestrator 的动作 |
|---|---|---|---|
| OK | succeeded | `completed`（或继续下一步） | 入队流水线的下一步；没有下一步就合成结果。**OK 但 confidence 低于阈值时，按 NEEDS_ESCALATION 处理**（统一的升级策略） |
| TRIGGER_REPLAN | succeeded | 同上 | 把 `planning.revise_plan` 插到下一步，每个请求最多 1 次 |
| NEEDS_INPUT | needs_input | `awaiting_confirmation` | 请求进入等待；用户的回复交回同一个 task_type（见 3.5） |
| NEEDS_ESCALATION | escalated | `escalated` | 开 review case 并通知负责人；人做出决定前不再自动路由 |
| AWAITING_APPROVAL | awaiting_approval | `pending_review` | 开 approval case；批准前不执行任何变更 |
| FAILED | failed | `failed` | 请求失败，错误码取 reason |

保护措施：

- 每个请求内 agent 之间自动交接（hops）最多 6 次；用户回复和人工决定不计入。
- agent 抛出未捕获的异常时，任务记为 `unhandled_exception`。
- 卡死任务（规范 8.5）：任务出队时设 `deadline_at`，超时后在 `TASK_MAX_ATTEMPTS` 次以内重新排队，超过则记为 `task_timeout`。worker 启动时和每轮取任务前都会扫描。

### 3.4 Orchestrator 传给 agent 的 TaskInput.payload

| 键 | 何时出现 |
|---|---|
| `input`、`context_id` | 始终有。`input` 是校验后的前端 `input` |
| `upstream`、`upstream_data` | 流水线的第二步及以后：上一步的 `payload["result"]` 和完整 payload |
| `reply`、`previous` | 用户回复了 NEEDS_INPUT：`reply` 是回复内容，`previous` 是上一轮的完整 payload，可用来取回 session_id 之类的状态 |
| `decision`、`case_id`、`subject_id` | 人工决定后的 resume 任务。`decision` 的格式为 `{action, note, decided_by, corrected_level?}` |

重新排队意味着同一个任务可能执行两次，所以写操作放在最后一步，并尽量做成幂等（规范 8.5）。

### 3.5 回复等待中的请求（NEEDS_INPUT）

前端用 `POST /requests {type: 原 type, context_id: <原请求 id>, input: {...}}` 回复。网关发现 `context_id` 指向本人发起、且正在等待输入的同类型请求时，调用 `dispatcher.reply()`：把等待中的任务标记为完成，再入队一个同 task_type 的新任务，payload 中加上 `reply` 和 `previous`，不新建流水线、不重新分类。测评作答走专门的 `POST /assessments/{id}/answers`，机制相同。

### 3.6 流水线表与结果契约

| 请求类型 | 可发起的角色 | 流水线（task_type） | `payload["result"]` 必须包含（`contracts.py`） |
|---|---|---|---|
| collect_goal | 学生 | coordinator.collect_goal | `summary` 或 `question`（追问）；`focus_skills[]` |
| confirm_goal | 学生 | coordinator.confirm_goal | `profile`（`profile_view`） |
| complete_material | 学生 | coordinator.record_material_completion | `material {id,title,locator,completed_at}` |
| explain / resources | 学生 | teaching_support.answer_question / retrieve_material | `interaction`（`interaction_view`） |
| practice | 学生 | teaching_support.generate_practice | `question`，可选 `item_id`、`source` |
| practice_answer | 学生 | teaching_support.give_feedback | `feedback` |
| revise_plan | 学生、教师 | planning.revise_plan → AWAITING_APPROVAL（resume：planning.activate_plan） | `plan`（`plan_view`）；`review_id` 由 Orchestrator 注入 |
| reschedule | 学生 | planning.propose_slot（通常返回 NEEDS_INPUT） | `lesson_id`，`proposed_slot` 或 `slots[]`，`message` |
| confirm_slot | 学生 | planning.book_slot（必须先用 `check_lesson_slot` / `move_lesson` 复查冲突） | `lesson`（`lesson_view`） |
| replace_teacher | 学生 | planning.match_teacher（找不到教师时 `route_to: founder`） | 可选 `plan`、`review_id`、`message` |
| review_progress / recommend_plan | 教师 | teaching_support.analyze_progress / recommend_adjustments | `recommendation`，可选 `evidence` |
| lesson_briefing | 教师 | teaching_support.lesson_briefing | `briefing`、`source_refs[]` |
| generate_material | 教师 | teaching_support.generate_material（用 `create_material_draft` 写草稿） | `material`（`material_view`） |
| start_assessment（`POST /assessments`） | 学生（initial / milestone）、教师（directed） | assessment.conduct_assessment → planning.generate_plan | `session_id` |
| decision_follow_up（内部） | — | 人工决定后执行的 resume task_type | 不限 |
| agent_correction（内部） | Founder | tech_operations.apply_correction | 不限 |

关于 reschedule / confirm_slot 的输入：前端发送的 `slot` 是不带时区的本地时间（`YYYY-MM-DDTHH:mm`），按学生 profile 里的 timezone 解释；confirm_slot 还会带上浏览器换算好的 `starts_at`（UTC），但这个值只能作参考，必须在服务端重新检查冲突。契约里的 `requested_time`、`slot_request_id`、`slot_id` 也可以接收。

关于 start_assessment：没有 active 计划时，generate_plan 起草计划并返回 AWAITING_APPROVAL（约束 C1）；已有 active 计划时，它把测评结果和里程碑比较，可以直接返回 OK，也可以返回 TRIGGER_REPLAN（UC05 第 6 步、7a）。

**测评专用约定**（前端已经写死，必须遵守）：

- `items` 的格式为 `[{item_id, prompt, answer|null}]`，`item_id` 依次为 `item-1`、`item-2`……（前端按 `item-${answered+1}` 发送）。
- 每出一题返回 NEEDS_INPUT，并在 `result` 里带上 `session_id`。
- 重复提交同一题由网关处理，保证幂等。
- 用 `record_answer` 保存答案，用 `record_proficiency` 保存测评结果。
- 低置信度时返回 NEEDS_ESCALATION，`subject_type="assessment"`，`subject_id=<ProficiencyProfile id>`，`resume="assessment.apply_review"`。

### 3.7 EscalationManager

- **定人规则**：
  - 学习类（assessment / plan / question）交给学生 active 或 pending 计划的教师。
  - 学生还没有教师时，交给 `INTAKE_TEACHER_EMAIL`（接待教师）；接待教师也不存在时交给 Founder。
  - business、proposal，以及 `route_to=founder` 的请求，交给 Founder。
- **教师可选的动作**：
  - plan：`approve` 或 `request_changes`
  - assessment：`confirm_result` 或 `request_changes`，可附 `corrected_level`
  - question：`answer` 或 `request_changes`
  - 决定必须附说明（note）。
- **resume 任务必须处理复核人能选的每一种动作**，例如 activate_plan 收到 `request_changes` 时要把计划标为 changes_requested。
- **回答升级问题不需要 agent**：前端显示的答案由 case 的决定叠加上去（`interaction_view(entry, case=...)`）。
- **Founder 业务 case 的动作**：`widen_match`、`request_teacher`、`resolve`。前端按钮发送的 `approve_resolution`、`request_followup` 会被映射成这几个。
- **提案审批**：审批绑定版本（`version` 不一致时返回 409），拒绝必须写理由。批准后入队 `tech_operations.execute_proposal`；执行和验证由 tech_operations 用 `record_proposal_execution` 分别记录审计。

### 3.8 审计（NFR-07）

以下事件自动记录，agent 不需要自己调用：

- Orchestrator：每次请求和任务的状态变化（`request.*`、`task.*`）
- services：每次写操作
- EscalationManager：每次决定（`escalation.resolved`、`proposal.approved` 等）

其他需要审计的事件用 `orchestration.audit.record(actor, action, target, detail=...)`。每条审计同时以一行 JSON 输出到 stdout。Founder 工作区的审计列表不显示 `task.*`、`request.*` 这类机器事件（它们以运行日志的形式显示）。

### 3.9 原因码（snake_case）

共享层使用的原因码：

| 原因码 | 含义 |
|---|---|
| `agent_not_implemented` | 找不到 agent 模块或类 |
| `agent_paused` | agent 被 Founder 暂停 |
| `unknown_task_type` | task_type 不在该 agent 的 `task_types` 里 |
| `unhandled_exception` | agent 抛出未捕获的异常 |
| `invalid_agent_result` | 返回值不是 AgentResult |
| `invalid_result` | 结果不符合契约 |
| `max_hops_exceeded` | agent 交接超过 6 次 |
| `task_timeout` | 任务超时且重试次数用完（`task_timeout_retry` 表示超时后重新排队） |
| `request_failed` | 请求失败，剩余排队任务一并取消 |
| `low_confidence` | 置信度低于阈值，自动升级 |
| `escalation_requested` | 返回 NEEDS_ESCALATION 但没写 reason 时的默认值 |
| `approval_required` | 返回 AWAITING_APPROVAL 但没写 reason 时的默认值 |
| `agent_failed` | 返回 FAILED 但没写 reason 时的默认值 |

agent 自己的原因码在各自的设计文档里列出，并说明对应哪个 status。

---

## 4. API 与权限（规范第 6 节）

- 一个 NinjaAPI 挂在 `/api/v1`，OpenAPI 文档在 `/api/v1/docs`。
- 路由函数只做三件事：校验、权限检查、调用 orchestration 或 domain。
- 认证：`POST /auth/login` 返回 `session`（签名 token），之后请求带 `Authorization: Bearer <session>`。
- 对象级权限只有一个入口 `can_access_student`：
  - 学生只能访问自己。
  - 教师可以访问三类学生：自己是其 active 或 pending 计划的 teacher，或者自己是该学生某个未关闭复核的负责人。
  - Founder 可以访问全部。
  - 被拒绝时返回 403，并写一条审计 `access.denied`。

| 接口 | 调用者 | 实现 |
|---|---|---|
| `POST /auth/register`、`POST /auth/login` | 访客 | identity（注册只能创建学生） |
| `GET /workspace?student_id` | 三种角色 | presenters 组装角色信封；Founder 只拿运营摘要 |
| `POST /requests`、`GET /requests/{id}`、`GET /requests/{id}/trace` | 学生、教师 / Founder | dispatcher |
| `POST /assessments`、`GET /assessments/{id}`、`POST /assessments/{id}/answers` | 学生、教师 | dispatcher（start_assessment 和 reply） |
| `GET /reviews/{id}`、`POST /reviews/{id}/decision` | 复核负责人 | EscalationManager |
| `PATCH /students/{id}/observation`、`PATCH /teachers/me/availability`、`PATCH /lessons/{id}` | 教师 | learning.services |
| `GET /materials/{id}`、`PATCH /materials/{id}` | 学生（只能看已批准且属于自己课程的）、教师 | learning.services |
| `GET /cases/{id}`、`POST /cases/{id}/decision` | Founder | 业务 case 由 EscalationManager 处理；技术事故返回 409，须走提案 |
| `POST /agents/{id}/decision` | Founder | `pause`、`resume`、`request_correction` |
| `GET /proposals/{id}`、`POST /proposals/{id}/decision` | Founder | EscalationManager |

错误体统一为 `{"message", "error": {"code", "message", "request_id"}}`。状态码：

- 400：入参错误
- 401：未登录
- 403：无权限
- 404：不存在
- 409：状态冲突
- 422：同步执行后请求失败，body 里额外带 `request` 信封
- 500：未预期的错误

---

## 5. 检索、配置、数据、测试、启动

- **检索**：`infrastructure.retrieval` 提供 `is_enabled()`、`search()`、`ingest()`。目前只实现了 `none` 档位，调用方必须先检查 `is_enabled()`；没有检索时如何回答（例如注明“未引用教材”）由 agent 自己决定。keyword 或 vector 档位以后可以在同一接口下补上。
- **配置**：全部来自环境变量，见 `.env.example`。全系统只有一个阈值 `AGENT_CONFIDENCE_THRESHOLD=0.70`。
- **演示数据**：`python manage.py load_demo_data [--reset]` 按文件名顺序导入 `fixtures/demo_*.json`。fixture 里的 `key` 会转成确定的 uuid5，所以每次导入的 id 都一样。负责人把自己的数据放在 `fixtures/<agent_id>_*.json`，用 Django 标准 fixture 格式，不要改别人的文件。
- **测试**：`python -m pytest`。
  - 测试替身 agent 在 `tests/stub_agents.py`，用 `stubs` fixture 按 task_type 注册行为，写法可参考 `tests/test_pipeline.py`。
  - CI 不调用真实 LLM。
- **启动**：`python run_demo.py`，会依次执行 migrate、load_demo_data、ingest_materials（检索不是 none 时），然后启动 runserver；worker 模式下再启动 run_agent_worker。

## 6. 负责人交付清单（规范 9.1）

- [ ] 在 `agents/<id>/agent.py` 写一个继承 `AIAgent` 的类，类名与 `settings.AGENT_REGISTRY` 一致；Coordinator 写在 `orchestration/coordinator/agent.py`。
- [ ] `task_types` 覆盖第 3.6 节中自己的全部 task_type，每个 task_type 有 pydantic 入参/出参 schema；新增 task_type 时提 PR 修改 `pipelines.py`。
- [ ] `payload["result"]` 符合 `contracts.py`，用 `domain.*.views` 生成记录。
- [ ] 列出原因码，说明每个原因码对应哪个 status。
- [ ] 需要的模型字段提 PR，并写明自己模型的 status 取值。
- [ ] 提供 fixtures 和 FakeAdapter 脚本（可选：在 agent 类上定义 `fake_script(task)`，供离线演示）。
- [ ] 至少一条成功路径测试和一条升级路径测试。
- [ ] （可选）用 `runtime.note()` 把决策理由写进 trace。

---

## 附录 A：与规范和 Stage 1 报告的偏离

写报告时可以直接引用。

| # | 偏离 | 理由 |
|---|---|---|
| A1 | 路由用 `/api/v1` 下前端的 20 个扁平接口，不按控制台分 router | 前端代码已经按这 20 个接口实现，接口冲突以前端为准 |
| A2 | 用 Bearer 签名 token 代替 session + CSRF | 前端用 localStorage 保存 token 并发 Bearer；token 无状态，云上部署更简单 |
| A3 | 默认 inline 执行，worker 模式保留 | 前端同步读取结果；Cloud Run 不适合常驻 worker |
| A4 | 错误体同时包含 `message` 和 `error{code,message,request_id}` | 前端读 `message`，规范要求 `error` |
| A5 | `POST /requests` 同步执行后失败时返回 422 | 前端靠 HTTP 错误显示提示；`GET /requests/{id}` 仍按规范返回 200 |
| A6 | 角色名对外首字母大写 | 前端用 `Student`、`Teacher`、`Founder` |
| A7 | agent id 对外用别名 consultant、assistant、technical | 前端 fixture 和 `/f3` 页面写死了这些 id；内部仍用规范的 id |
| A8 | 工作区按 `types.ts` 的结构返回，暂不分页 | `contract.json` 与前端代码不一致；前端不传 cursor |
| A9 | AvailabilitySlot 改为每周循环窗口，去掉 `Lesson.slot` | 前端可用时间的格式是 `{day,start,end}`；NFR-03 改在 services 中检查 |
| A10 | “已分配教师”包括 pending 计划的 teacher 和复核负责人 | 教师需要审批还没有 active 计划的学生 |
| A11、A12 | 教材修改接受 `status` 和 `action` 两种格式；Case 动作接受两套取值 | 兼容前端实际发送的值 |
| A13 | `type` 直接当作 intent，不做 LLM 分类 | 前端发送明确的 type |
| A14 | 测评作答走专门接口 | 前端有 `/assessments` 系列接口；内部仍是 NEEDS_INPUT 和 resume 机制 |
| A15 | 新增 ServiceRequest 表 | `GET /requests/{id}` 需要持久化的请求信封 |
| A16 | 对外状态值映射为前端用的词 | 前端按这些字符串判断状态 |
| A17 | 学生没有教师时，学习类复核交给接待教师，不交给 Founder | Founder 页面没有确认测评的入口 |
| B4 | 使用 SQLite、学校 LLM 接口、单机部署，检索档位为 none | 这是一个 demo；部署图 Fig 25 是目标架构。检索为 none 时，UC04 第 4 步无法给出引用 |
| — | 只用单个 settings 模块（不拆 base/dev/test） | 所有差异都通过环境变量配置 |
| — | ServiceRequest 和 AgentTask 是 Orchestrator 的状态，由 task_queue 写入；Conversation 只作为 Coordinator 自己的会话记录 | 等待输入的状态已经保存在 ServiceRequest 和 AgentTask 里 |
