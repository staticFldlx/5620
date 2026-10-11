# LingoPath Stage One API、需求与 Agent 对照（拟议版）

> 版本：2026-10-11。适用范围：当前 `frontend` 的无后端原型，以及之后的后端对接讨论。本文件是**接口设计说明**，不是已经部署的后端说明。浏览器现在由 MSW 模拟 HTTP 请求；真正的鉴权、持久化、Agent 编排、课程预约和审批执行仍需后端实现。

**直接查对接细节：第 7 节逐一说明 20 个 HTTP 接口的网页输入、请求与响应 JSON；第 8 节逐一说明 `POST /requests` 的 15 种业务动作；第 9 节可从 18 个页面反查调用。**第 1–6 节提供需求编号、Agent 分工、字段字典和当前模拟版与目标契约的差异。

## 1. 编号、来源与边界

本文把提问中的 **UR（user requirement，用户需求）** 对应到《ELEC5620 Stage One Report》已有的 **AR01–AR13**（Ad hoc requirements）和 **UC01–UC10**（use cases）。报告没有独立的 `UR01` 一类编号，因此下文保留报告原编号，不另造一套 UR 编号。`SM3`、`SM4` 是压缩包原始契约对排课场景的补充引用，并非本报告的 AR/UC 编号。

设计依据：阶段一报告、`LingoPath_Core_Data_Preview_Pack.zip` 内的 `LingoPath_Core_API_Contract.json`，以及当前 `src/api/client.ts`、`src/api/types.ts`、`src/mocks/handlers.ts`。压缩包中的示意图和动效是界面参考，**不充当新增 API 需求或开发指令**。

统一前缀：`/api/v1`。下表的路径均省略此前缀。共 **20 个 HTTP 操作**；其中 `POST /requests` 用 `type` 承载 **15 种业务动作**。页面只调用 `src/api/client.ts`，不写接口地址。需要登录的请求携带 `Authorization: Bearer <session>`，请求和响应主体均为 JSON。所有日期时间建议使用 ISO 8601 带时区的字符串，ID 当作不透明字符串处理。

### Agent 与人的职责

| 名称 | 身份 | 负责的事 |
| --- | --- | --- |
| AI Course Coordinator（课程协调 Agent） | AI Agent | 接收与分类学习请求，安排流程、排课/换老师建议，路由其他 Agent，处理待确认状态；对应 AR11。 |
| AI Assessment Agent（测评 Agent） | AI Agent | 初始、阶段和教师定向测评，自适应出题、初步水平与薄弱项分析；对应 AR02、AR05。 |
| AI Course Consultant（课程顾问 Agent） | AI Agent | 根据目标、已确认测评和教学记录提出学习计划、调整建议；对应 AR03、AR07。 |
| AI Teaching Assistant（教学助理 Agent） | AI Agent | 答疑、资源定位、轻练习、学习反馈、教师备课与教材草稿；对应 AR04、AR05、AR08。 |
| AI Technical Manager（技术管理 Agent） | AI Agent | 检测、诊断运行问题，形成受控更改/恢复提案，向 Founder 汇报；对应 AR10、AR12。 |
| Human Teacher（教师） | 人工角色 | 确认低置信测评、批准计划与教材、处理升级问题、记录课堂结果。不是 AI Agent。 |
| Founder（创办人/运营负责人） | 人工角色 | 查看 Agent 和事故、决定业务异常、批准受控技术变更。不是 AI Agent。 |

认证、资料存取和审计是**后端服务职责**，不因为某个接口存在就虚构一个新的 AI Agent。表中“Agent”写“无”时，表示请求本身是读取/人工操作；它仍可能读取此前由 Agent 生成的记录。

## 2. 20 个 HTTP 接口总览

| # | 方法与路径 | 对应 AR / UC（UR） | 发起者；参与 Agent | 作用与主要 JSON 字段 |
| ---: | --- | --- | --- | --- |
| 1 | `POST /auth/register` | 注册/登录入口；角色权限基础 | 访客；无 | `{name,email,password}` → `{session,user}`；公开注册只创建 Student。 |
| 2 | `POST /auth/login` | NFR5 身份和角色权限 | 访客；无 | `{email,password}` → `{session,user}`。 |
| 3 | `GET /workspace` | AR01–AR10、AR12；UC01–UC10 的已授权摘要 | Student/Teacher/Founder；无 | 按角色返回工作区记录；可选 `student_id`（已分配教师）、`cursor`。 |
| 4 | `POST /requests` | AR01、AR03–AR08、AR11、AR13；UC01、UC03–UC08 | Student/Teacher；Coordinator 路由，见第 3 节 | `{type,student_id?,context_id?,input}` → 请求状态与业务结果。 |
| 5 | `GET /requests/{id}` | AR11、AR13；相关 UC | 请求本人/已分配教师；Coordinator 任务结果 | 查询异步、待确认或升级结果；返回同一个请求信封。 |
| 6 | `POST /assessments` | AR02、AR05、AR06；UC02、UC05、UC06 | Student/Teacher；Assessment | 创建初始/阶段/定向测评；`{student_id,kind,focus?}`。 |
| 7 | `GET /assessments/{id}` | AR02；UC02 | 学生本人/已分配教师；无新任务 | 恢复测评进度和查看结果。 |
| 8 | `POST /assessments/{id}/answers` | AR02、AR05；UC02、UC05 | 学生本人；Assessment | `{item_id,answer}` → 下一题或暂定测评结果。 |
| 9 | `GET /reviews/{id}` | AR02、AR03、AR07、AR13；UC03、UC06–UC08 | 已分配教师；无 | 查看计划、测评或升级问答的审核对象和证据。 |
| 10 | `POST /reviews/{id}/decision` | 同上 | 已分配教师；必要时 Coordinator/Consultant 继续流程 | 批准、要求修改、确认结果、回答问题。 |
| 11 | `PATCH /students/{id}/observation` | AR06；UC06 | 已分配教师；无 | 保存教师观察 `{note}`。 |
| 12 | `PATCH /teachers/me/availability` | AR03；UC03；SM4 | Teacher；Coordinator 后续使用 | 保存时区和可授课时段。 |
| 13 | `PATCH /lessons/{id}` | AR05、AR06；UC05、UC06；SM4 | 已分配教师；无 | 课后出席和反馈；排课变更走 Coordinator。 |
| 14 | `GET /materials/{id}` | AR04、AR08；UC04、UC08 | 学生/教师；无 | 按权限打开已批准教材或教师草稿正文。 |
| 15 | `PATCH /materials/{id}` | AR08；UC08 | 已分配教师；无 | 编辑或批准教材 `{content,action}`。 |
| 16 | `GET /cases/{id}` | AR09、AR10；UC09、UC10 | Founder/获准的 Technical Manager；无 | 读取业务异常/技术事故证据。 |
| 17 | `POST /cases/{id}/decision` | AR09、AR13；UC09 | Founder；Coordinator 执行后续业务动作 | 扩大匹配、请求教师介入或解决异常。 |
| 18 | `POST /agents/{id}/decision` | AR09；UC09 | Founder；目标 Agent | 暂停异常 Agent 或要求纠正，写审计。 |
| 19 | `GET /proposals/{id}` | AR09、AR10、AR12；UC09、UC10 | Founder；Technical Manager 提案 | 读取变更前后、验证、回退方案。 |
| 20 | `POST /proposals/{id}/decision` | AR09、AR10、AR12；UC09、UC10 | Founder；Technical Manager 获批后执行 | 批准/拒绝受控更改，执行和验证须分开记录。 |

对应页面：`/p01`–`/p02` 使用认证；`/s1`–`/s8` 使用工作区、请求、测评和教材；`/t1`–`/t5` 使用工作区、审核、课堂记录和教材；`/f1`–`/f4` 使用工作区、异常、Agent 决定和提案。具体路由见 `README.md`。

## 3. `POST /requests` 的 15 种动作与路由

公共请求体为 `{ "type": "...", "student_id": "...", "context_id": "...", "input": { ... } }`。Student 的 `student_id` 可省略并由会话确定；Teacher 代学生发起时必须是被分配的学生。`context_id` 是关联课程、计划或历史请求的可选 ID；具体业务 ID 仍应写在 `input` 的专用字段里。下面 `?` 表示可选字段，表内 JSON 是 `input` 的例子，不是完整请求体。

| `type` | 对应 AR / UC | 调用者 → Agent | `input` JSON 示例 | `result` 应包含什么 |
| --- | --- | --- | --- | --- |
| `collect_goal` | AR01 / UC01 | Student → Coordinator | `{"goal_text":"Improve academic writing","focus_skills":["writing"],"self_level":"B1","weekly_hours":4,"timezone":"Australia/Sydney","availability":[{"day":"Monday","start":"18:00","end":"20:00"}]}` | 目标摘要、关注技能、必要的追问；尚未正式保存。 |
| `confirm_goal` | AR01 / UC01 | Student → Coordinator | `{"summary_request_id":"RQ-101","confirmed_summary":"Write clearer academic arguments"}` | 已保存的 `profile`、下一步测评/复用计划提示。 |
| `explain` | AR04、AR11、AR13 / UC04 | Student → Coordinator → Teaching Assistant | `{"question":"How do I connect evidence to my claim?"}` | `interaction`：回答、置信度、来源；低置信则升级到 Teacher。 |
| `resources` | AR04 / UC04 | Student → Coordinator → Teaching Assistant | `{"question":"argument structure"}` | 仅当前阶段授权的教材引用。 |
| `practice` | AR05 / UC05 | Student → Coordinator → Teaching Assistant | `{"focus":"evidence linking"}` | 练习题、`item_id`、可追溯来源。 |
| `practice_answer` | AR05 / UC05 | Student → Coordinator → Teaching Assistant | `{"practice_request_id":"RQ-105","item_id":"P-1","answer":"The evidence supports the claim because ..."}` | 即时反馈；不直接修改正式测评或计划。 |
| `complete_material` | AR05 / UC04 | Student → Coordinator/记录服务 | `{"material_id":"M-201"}` | 自己的学习记录中该资料的 `completed_at`；不修改教材内容/审批。**拟议契约有此动作，当前前端尚未接入。** |
| `review_progress` | AR06 / UC06 | Teacher → Coordinator → Consultant（可用 Assessment 已确认结果） | `{"student_id":"student-ivy"}` | 基于已确认测评、计划、课堂和观察的分析及证据。 |
| `recommend_plan` | AR07 / UC07 | Teacher → Coordinator → Consultant | `{"student_id":"student-ivy"}` | 计划/教学策略建议及依据，尚不生效。 |
| `revise_plan` | AR03、AR07 / UC03、UC07 | Student/Teacher → Coordinator → Consultant | `{"student_id":"student-ivy","reason":"Writing goal changed","requested_change":"More writing practice"}` | `pending_plan` 草稿和 `review_id`；旧计划继续有效。 |
| `reschedule` | AR03 / UC03；SM3、SM4 | Student → Coordinator | `{"lesson_id":"L-018","requested_time":"2026-10-15T18:00:00+11:00"}` | 兼容时段提案及理由；旧预约保持。 |
| `confirm_slot` | AR03；SM4 | Student → Coordinator | `{"slot_request_id":"RQ-110","slot_id":"SL-01"}` | 服务端复核冲突后更新的 `lesson`；不能仅凭前端确认。 |
| `replace_teacher` | AR03 / UC03；SM3 | Student → Coordinator | `{"reason":"Need a teacher available on weekends"}` | 匹配提案；无可用教师时升级给 Founder。 |
| `lesson_briefing` | AR08 / UC08 | Teacher → Coordinator → Teaching Assistant | `{"lesson_id":"L-018"}` | 根据计划、薄弱项、问题和教师意见生成的备课摘要及来源。 |
| `generate_material` | AR08 / UC08 | Teacher → Coordinator → Teaching Assistant | `{"lesson_id":"L-018","topic":"Evidence linking","level":"B1","type":"exercise","guidance":"Use short academic texts"}` | 可编辑 `material` 草稿、来源；必须由教师批准后学生才可见。 |

公共响应信封示例（`phase` 解释当前等待步骤，`result` 只承载该动作需要的业务记录）：

```json
{
  "id": "RQ-110",
  "type": "reschedule",
  "status": "awaiting_confirmation",
  "phase": "student_choose_slot",
  "result": {
    "lesson_id": "L-018",
    "slots": [
      {"id": "SL-01", "starts_at": "2026-10-15T18:00:00+11:00", "ends_at": "2026-10-15T19:00:00+11:00"}
    ],
    "rationale": "Matches the student's and teacher's availability"
  }
}
```

`GET /requests/RQ-110` 返回相同结构，供页面刷新、恢复或等待人工处理。建议状态至少区分 `completed`、`awaiting_confirmation`、`pending_review`、`escalated`、`rejected`；具体状态值须由后端与前端类型一起锁定。失败可返回 `error`，例如 `{"code":"SLOT_CONFLICT","message":"The slot is no longer available"}`。

## 4. 各领域 JSON 结构与调用例子

以下示例 ID、姓名、时间均为说明用模拟值。字段来源是拟议契约；当契约只列了字段、未限定枚举/必填性时，这里用**建议值**演示，不把示例误写成已定型的 JSON Schema。

### 4.1 认证与工作区（#1–#3）

```http
POST /api/v1/auth/register
Content-Type: application/json

{"name":"Ivy Lin","email":"ivy@example.com","password":"example-password"}
```

```json
{"session":"opaque-session-token","user":{"id":"student-ivy","name":"Ivy Lin","email":"ivy@example.com","role":"Student"}}
```

`POST /auth/login` 仅提交 `{"email":"ivy@example.com","password":"example-password"}`，成功响应同上；Teacher 和 Founder 账户由受控方式预置或管理，公开注册不能选择这两种角色。`session` 是示意性 token，不应使用用户 ID 当生产 token。

当前前端使用的 `GET /workspace` 响应结构是一个角色化工作区信封；例如 Student：

```json
{
  "user": {"id":"student-ivy","name":"Ivy Lin","email":"ivy@example.com","role":"Student"},
  "students": {
    "student-ivy": {
      "profile": {
        "goal_text":"Improve academic writing",
        "goal_summary":"Write clearer academic arguments",
        "focus_skills":["writing","reading"],
        "target_level":"B2",
        "self_level":"B1",
        "weekly_hours":4,
        "timezone":"Australia/Sydney",
        "availability":[{"day":"Monday","start":"18:00","end":"20:00"}]
      },
      "assessments":[],
      "plan":null,
      "pending_plan":null,
      "material_records":[],
      "observation":""
    }
  },
  "lessons":[],
  "materials":[],
  "interactions":[]
}
```

Teacher 当前信封使用 `students`（可带 `?student_id=student-ivy`）、`lessons`、`materials`、`reviews`、`teacher_availability`；Founder 使用 `operations:{agents,services,logs,warnings,cases,proposals,audit}`。拟议契约期望列表分页（`cursor` / `next_cursor`）、学生教材仅给引用，以及 Founder 不获得学生私密学习内容；当前 MSW 未完整实现这些限制，真实后端必须落实。`GET /workspace?student_id=...` 只应允许查看被分配学生。

### 4.2 测评（#6–#8）：Assessment Agent

```http
POST /api/v1/assessments
Content-Type: application/json

{"student_id":"student-ivy","kind":"initial","focus":"academic writing"}
```

```json
{
  "id":"AS-101",
  "kind":"initial",
  "status":"in_progress",
  "answered":0,
  "max_items":3,
  "current_item":{"id":"Q-1","prompt":"What is the main claim?","type":"short_text"},
  "result":null
}
```

`kind` 为 `initial | milestone | directed`；`directed` 仅由教师发起。`GET /assessments/AS-101` 返回同一 session；`POST /assessments/AS-101/answers` 提交 `{"item_id":"Q-1","answer":"The author argues ..."}`，返回下一题或完成结果。相同 `item_id` 重复提交应幂等。测评完成后的 `result` 是 `ProficiencyRecord`：

```json
{
  "id":"A-101","kind":"initial","status":"pending_review",
  "created_at":"2026-10-11T09:00:00+11:00",
  "level":"B1","confidence":0.62,
  "strengths":["Academic reading"],"weaknesses":["Evidence links"],
  "goal_gap":"Need stronger evidence explanations",
  "feedback":"Provisional result; teacher review required",
  "review_note":null,"requested_focus":"academic writing"
}
```

低置信度时保持暂定并建立教师审核；只有确认/修正后，Consultant 才能用正式结果生成计划。当前模拟题目 `current_item` 是纯字符串，而上述对象形式是后端对接时建议锁定的结构；不要直接把示例对象当作当前 mock 已支持的格式。

### 4.3 计划、课程与进度（#4、#5、#11–#13）

`POST /requests` 发起 `revise_plan` 后的 `result.plan` 示例：

```json
{
  "id":"PL-102","version":2,"status":"pending_review","stage_index":1,
  "teacher":{"id":"teacher-emily","name":"Emily Walker"},
  "weekly_hours":4,
  "stages":[
    {"title":"Evidence and argument","course_ref":"CORE-2","start_week":4,"end_week":6,"topics":["Evidence linking"],"milestone":"Explain the link between evidence and claim","status":"upcoming"}
  ],
  "reason":"More writing practice requested",
  "review_id":"RV-102","approved_at":null
}
```

`LearningPlan` 的 `version` 用于避免审查旧草稿；`status` 应区分待审与已启用；教师一次批准后才把草稿变为 active，旧计划在此前继续有效。`PlanStage` 的 `start_week`/`end_week` 是计划周次，不是课程时间。

课时 `Lesson` 示例（`PATCH /lessons/L-018` 只能修改允许的课后字段）：

```json
{
  "id":"L-018","student_id":"student-ivy","title":"Academic argument workshop",
  "starts_at":"2026-10-15T18:00:00+11:00","ends_at":"2026-10-15T19:00:00+11:00",
  "teacher":{"id":"teacher-emily","name":"Emily Walker"},
  "stage_index":1,"status":"scheduled","classroom_url":null,
  "attendance":"unknown","feedback":"","material_ids":["M-201"]
}
```

```http
PATCH /api/v1/students/student-ivy/observation

{"note":"Needs more evidence-to-claim explanation"}
```

```json
{"note":"Needs more evidence-to-claim explanation","updated_at":"2026-10-11T09:00:00+11:00","teacher_id":"teacher-emily"}
```

```http
PATCH /api/v1/teachers/me/availability

{"timezone":"Australia/Sydney","availability":[{"day":"Monday","start":"18:00","end":"20:00"}]}
```

响应返回同一时间记录；已有预订冲突时应拒绝不兼容修改。`PATCH /lessons/L-018` 的请求例如 `{"attendance":"present","feedback":"Clearer explanations today"}`，响应为更新后的完整 Lesson。学生改时间用 `reschedule` + `confirm_slot`，不要直接 PATCH lesson 时间。

### 4.4 教师审核与教材（#9、#10、#14、#15）

`GET /reviews/RV-102` 示例：

```json
{
  "review":{"id":"RV-102","kind":"plan","student_id":"student-ivy","subject_id":"PL-102","status":"pending","trigger":"Major plan revision","decision":null},
  "subject":{"id":"PL-102","version":2,"status":"pending_review","review_id":"RV-102"},
  "evidence":"Confirmed assessment A-101 and teacher observation"
}
```

`subject` 根据 `kind` 为完整的计划、测评记录或问答记录；上方为节省篇幅只展示部分计划字段，完整计划结构见 4.3。教师提交决定：

```http
POST /api/v1/reviews/RV-102/decision

{"action":"approve","note":"Plan matches the confirmed assessment"}
```

`action` 为 `approve | request_changes | confirm_result | answer`。修正测评可附 `corrected_level`，例如 `{"action":"confirm_result","note":"Oral evidence supports B1","corrected_level":"B1"}`；覆盖 Agent 结果要保存依据。拟议响应是 `{"review":{...},"updated_subject":{...}}`。

`GET /materials/M-201` 的 `Material`：

```json
{
  "id":"M-201","title":"Evidence linking exercise","locator":"lesson/L-018/material/M-201",
  "status":"draft","lesson_id":"L-018",
  "content":"Read the paragraph and connect evidence to the claim.",
  "source_refs":[{"title":"Academic Argument Guide","locator":"library/argument-guide"}]
}
```

`PATCH /materials/M-201` 请求为 `{"content":"Revised exercise text","action":"save"}` 或 `{"content":"Approved exercise text","action":"approve"}`，响应返回完整 Material。批准后才把材料 ID 放进对应 Lesson 的 `material_ids`，学生只能 GET 已批准且属于自己的材料。工作区只应提供轻量 `LearningMaterialReference`（`id,title,locator,completed_at`）；正文在打开时 GET，避免重复传输。

### 4.5 Founder 运营、事故与审批（#16–#20）

`GET /cases/C-101`：

```json
{
  "id":"C-101","kind":"technical_incident","status":"open",
  "subject":"Search index unavailable","trigger":"Repeated retrieval failures",
  "diagnosis":"Index health check failed",
  "evidence":[{"ref":"LOG-201","summary":"Three failed retrievals"}],
  "proposal_id":"PR-101","decision":null,"verification":null
}
```

`POST /cases/C-101/decision` 用于业务异常人工决定，请求 `{"action":"request_teacher","note":"Please review the unresolved request"}`。允许动作 `widen_match | request_teacher | resolve`；返回更新 Case 和审计记录（目标契约）。技术事故的配置/索引/语料变更应走 Proposal 审批，不能靠此接口直接执行。

`POST /agents/assessment/decision` 请求 `{"action":"pause","note":"Unexpected assessment output","case_id":"C-101"}`，或 `action:"request_correction"`。只有 Founder 可调用，结果需有 Agent 状态/纠正请求和审计项。

`GET /proposals/PR-101`：

```json
{
  "id":"PR-101","type":"index_rebuild","title":"Rebuild search index",
  "case_id":"C-101","status":"pending_approval",
  "evidence":["LOG-201","health-check-01"],
  "before":"Index version 4, unhealthy",
  "after":"Index version 5, validated",
  "validation":"Run retrieval and access-scope checks",
  "rollback":"Restore version 4 snapshot",
  "decision":null,
  "execution":{"status":"not_started","verification":null}
}
```

`POST /proposals/PR-101/decision` 请求 `{"action":"approve","note":"Proceed with verification"}` 或 `{"action":"reject","note":"Rollback plan is insufficient"}`。拒绝必须有理由；批准须绑定已审阅的提案版本，Technical Manager 只能执行该版本。批准、执行、验证是不同的可审计事件；验证失败时 Case 不应关闭。Founder 工作区中的 Agent、Log、Audit 主要字段分别是 `Agent:{id,name,status,latest_task}`、`OperationalLog:{id,time,agent_id,event,severity,task_status,confidence,escalated}`、`Audit:{id,time,actor_role,actor_name,subject_id,action,result}`；不应暴露学生聊天、答案、目标或课堂笔记。

### 4.6 记录字段速查

`GET /workspace`、请求结果和详情接口会复用以下领域记录。`null` 表示尚无结果；空数组表示有权限但暂无记录。字符串枚举（如 `status`）需在后端 OpenAPI 中最终固定。

| JSON 对象 | 字段及含义 |
| --- | --- |
| `User` | `id` 标识、`name` 显示名、`email` 登录邮箱（当前前端使用）、`role` = `Student | Teacher | Founder`。 |
| `LearningProfile` | `goal_text` 原目标、`goal_summary` 确认摘要、`focus_skills[]`、`target_level`、`self_level`、`weekly_hours` 数字、`timezone`、`availability[]`。 |
| `ProficiencyRecord` | `id,kind,status,created_at,level,confidence,strengths[],weaknesses[],goal_gap,feedback,review_note?,requested_focus?`；`confidence` 是 0–1 的测评置信度。 |
| `LearningPlan` | `id,version,status,stage_index,teacher,weekly_hours,stages[],reason,review_id,approved_at`；每个 `PlanStage` 为 `title,course_ref,start_week,end_week,topics[],milestone,status`。 |
| `Lesson` | `id,student_id,title,starts_at,ends_at,teacher,stage_index,status,classroom_url,attendance,feedback,material_ids[]`。 |
| `LearningMaterialReference` | `id,title,locator,completed_at`；用于工作区卡片，不含正文。 |
| `TeacherObservation` | `note,updated_at,teacher_id`；原型的 StudentRecord 中只存 `observation` 文本。 |
| `Material` | `id,title,locator,status,lesson_id,content,source_refs[]`；`status` 至少区分草稿与批准。 |
| `LearningInteraction` | `id,student_id,type,question,answer,feedback,status,confidence,source_refs[],sent_at,escalation`；见下例。 |
| `Review` | `id,kind,student_id,subject_id,status,trigger,decision`；`kind` 指向计划、测评或问答。 |
| `Case` | `id,kind,status,subject,trigger,diagnosis,evidence[],proposal_id,decision,verification`。 |
| `Proposal` | `id,type,title,case_id,status,evidence[],before,after,validation,rollback,decision,execution`。 |
| `Agent` | `id,name,status,latest_task`；任务摘要可含 `id,status,confidence,output_summary`。 |
| `OperationalLog` | `id,time,agent_id,event,severity,task_status,confidence,escalated`。 |
| `Audit` | `id,time,actor_role,actor_name,subject_id,action,result`；记录人工批准、执行和验证。 |

答疑结果中的 `LearningInteraction` 完整例子：

```json
{
  "id":"I-101","student_id":"student-ivy","type":"explain",
  "question":"How do I connect evidence to my claim?",
  "answer":"Explain what the evidence shows, then link it to the claim.",
  "feedback":null,"status":"completed","confidence":0.89,
  "source_refs":[{"material_id":"M-201","title":"Academic Argument Guide","locator":"library/argument-guide"}],
  "sent_at":"2026-10-11T09:00:00+11:00","escalation":null
}
```

若答案证据不足，`status` 应变成 `escalated`，`escalation` 至少记录触发原因与待处理状态，并创建与之关联的 Teacher `Review`；不应把低置信文本当成正式教师答复。

## 5. 权限、错误和体量约束

- 后端应基于会话、角色和记录归属做授权，不能以是否显示页面为准。Student 只能看自己的记录；Teacher 只能看被分配学生；Founder 主要查看运营摘要。
- 建议统一错误体为 `{"code":"FORBIDDEN","message":"You cannot access this record","details":null}`；对应 HTTP `400` 字段错误、`401` 未认证、`403` 无权、`404` 不存在、`409` 状态/时段冲突、`500` 服务错误。**这是一项后端对接建议，不是现有 mock 的错误格式保证**；mock 目前多返回 `{message}`。
- `GET /workspace` 每类列表建议默认最多 20、上限 50，并用同一角色信封的 `next_cursor` 分页。界面统计仅针对已加载记录，并标明范围。
- 测评答题历史不能整个放进工作区；材料正文按需获取；涉及学生资料、权限、语料、索引、配置和归档的受控变更须留痕，关键或未知事故需 Founder 决定。
- 不在 Stage One 范围：支付、通知/未读数、作业版本与评分、下载报告、成本/Token 仪表盘、全站搜索等。不要为了每张卡片新增 API。

## 6. 当前前端/MSW 与拟议契约的差异（接后端前需处理）

| 项目 | 拟议契约 | 当前前端/MSW |
| --- | --- | --- |
| `POST /requests` 类型 | 15 种，含 `complete_material` | `RequestType` 和 mock 目前 14 种；尚不能标记教材完成。 |
| `confirm_goal` | `summary_request_id,confirmed_summary` | 页面/mock 用 `goal_text,goal_summary,focus_skills,...` 保存资料。 |
| 时段确认 | `requested_time` → `slot_request_id,slot_id`，服务端复核冲突 | mock 用 `slot,lesson_id,starts_at` 等临时字段；未完整实现真实冲突复核。 |
| 练习 | `practice` 返回 `item_id`；答案带 `practice_request_id,item_id` | mock 的练习结果无正式题目 ID，答案不校验对应题目。 |
| 测评题目 | 建议稳定 `item_id` + 题目内容 | mock `current_item` 为文本，答题 ID 由演示页面提供。 |
| 教材修改 | `{content,action:"save"|"approve"}` | `api.saveMaterial` / mock 目前传 `{content,status}`。 |
| 审核决定 | 允许 `corrected_level`，返回 `updated_subject` | 当前客户端未传 `corrected_level`；mock 仅返回 `{review}`。 |
| Case 决定 | `widen_match | request_teacher | resolve` | 当前页面/mock 使用演示动作值；mock 没有限制枚举。 |
| Agent 决定 | `pause | request_correction`，可带 `case_id` | 当前客户端只有 `request_correction`，mock 未执行暂停。 |
| 提案审批 | 版本绑定，批准后执行和验证分开 | mock 只记录审批状态与一条审计，未执行真实变更。 |
| 工作区/权限 | 按角色最小字段、已分配学生、分页、正文按需取 | mock 为演示保留完整 `students` 映射与 `materials` 列表；不满足生产授权/体量要求。 |

**接入顺序建议**：先固定后端与前端共用的 JSON Schema/OpenAPI 和上述差异，再完成认证、工作区和已用到的 14 种请求；随后补齐 `complete_material`、严格权限/分页、异步状态、审计与真实 Agent 编排。切换真实后端时设置 `VITE_USE_MOCK_API=false` 和 `VITE_API_BASE_URL`（见 `README.md`）。

## 7. 逐接口对接单：网页实际发送什么、后端返回什么

**阅读方法。** 以下每项都给出页面触发点、对应需求、负责角色/Agent、实际 HTTP 请求、完整可解析的响应例子及字段含义。示例以**当前前端 `src/api/client.ts` + MSW 的实际格式**为主；“目标差异”指出压缩包拟议契约对真实后端的要求。`POST`/`PATCH` 代码块是实际 JSON body；`GET` 没有 JSON body，展示 URL/查询参数。所有受保护接口均携带 `Authorization: Bearer <session>`。示例 token 与 ID 仅用于说明。

一个容易遗漏的调用顺序：登录/注册成功后，前端立即调用 `GET /workspace`；每次通过 `run(...)` 成功完成写操作后也会再次调用 `GET /workspace` 刷新页面。因此“写接口的响应”与“刷新后的工作区响应”是两次不同的 HTTP 响应。主题切换、动画开关、筛选、排序、页面内选中项和演示入口导航目前不发送给后端。

### 7.1 `POST /auth/register`

- **网页**：`/p02` 注册表单。输入 `name`、`email`、`password`；提交时三个字符串原样进入 JSON body。
- **需求**：注册入口及 NFR5 角色权限；为 AR01/UC01 建立 Student 身份。**Agent**：无，认证服务负责；注册者是访客。
- **请求字段**：`name:string` 必填显示名；`email:string` 必填且唯一；`password:string` 必填，当前 mock 最少 8 字符。公开表单**不发送** `role`，服务端固定创建 Student。

```json
{"name":"Ivy Lin","email":"ivy@example.com","password":"example-pass-123"}
```

- **成功响应字段**：`session:string` 会话凭证；`user.id:string`、`name:string`、`email:string`、`role:"Student"`。前端保存 `session`，随后请求工作区并进入 `/s1`。当前 mock 把新建的用户 ID 直接当 session；真实后端应返回独立、不可猜测的凭证。

```json
{"session":"student-new001","user":{"id":"student-new001","name":"Ivy Lin","email":"ivy@example.com","role":"Student"}}
```

- **失败**：当前 mock 对无效字段返回 `400 {"message":"Enter a name, valid email and at least 8 characters."}`，重复邮箱返回 409。真实后端不可把密码或其哈希放入响应。

### 7.2 `POST /auth/login`

- **网页**：`/p01` 登录表单。**需求**：NFR5 认证和角色权限。**Agent**：无；认证服务处理，Student/Teacher/Founder 都可登录。
- **请求字段**：`email:string`、`password:string`，均来自表单；页面不发送角色，角色由后端会话决定。

```json
{"email":"emily.walker@example.com","password":"demo1238"}
```

- **响应字段**：与注册相同的 `session` 和完整 `user`。前端按 `user.role` 进入 `/s1`、`/t1` 或 `/f1`，并请求工作区。

```json
{"session":"teacher-emily","user":{"id":"teacher-emily","name":"Emily Walker","email":"emily.walker@example.com","role":"Teacher"}}
```

- **失败**：当前 mock `401 {"message":"Invalid demo email or password."}`。示例密码只存在于演示环境，不能用于生产。

### 7.3 `GET /workspace`

- **网页**：登录后所有角色页的基础数据；每次成功写操作后自动重取。Teacher 详情理论上可用 `?student_id=student-ivy`；当前页面主要直接读已载入的 `students`，`api.workspace(studentId?)` 已预留参数。`cursor` 只在目标契约中，当前客户端尚未传。
- **需求**：AR01–AR10、AR12；为 UC01–UC10 的页面提供基础记录。**Agent**：无新 Agent 调用；读取已保存的 Agent/人工结果。**权限**：本人、已分配学生、Founder 运营摘要。
- **请求**：无 body。例如 `GET /api/v1/workspace`，或已分配教师的 `GET /api/v1/workspace?student_id=student-ivy`。`student_id` 是查询字符串，不是请求 JSON。
- **Student 响应字段**：`user`；`students` 为以 student ID 为键的对象，内含 `name,profile,assessments,plan,pending_plan,material_records,observation`；外层 `lessons[]`、`materials[]`、`interactions[]`。下面是完整、可解析的最小学生工作区例子：

```json
{
  "user":{"id":"student-ivy","name":"Ivy Lin","email":"ivy@example.com","role":"Student"},
  "students":{"student-ivy":{"name":"Ivy Lin","profile":{"goal_text":"Improve academic writing","goal_summary":"Write clearer arguments","focus_skills":["Writing"],"target_level":"B2","self_level":"B1","weekly_hours":4,"timezone":"Australia/Sydney","availability":[{"day":"Mon","start":"18:00","end":"20:00"}]},"assessments":[],"plan":null,"pending_plan":null,"material_records":[],"observation":""}},
  "lessons":[],"materials":[],"interactions":[]
}
```

- **Teacher 响应字段**：`user,students,lessons,materials,reviews,teacher_availability`。`students` 当前是映射，值与上述 StudentRecord 相同；`reviews[]` 每项有 `id,kind,student_id,subject_id,status,trigger,decision`。示例：

```json
{
  "user":{"id":"teacher-emily","name":"Emily Walker","email":"emily.walker@example.com","role":"Teacher"},
  "students":{"student-ivy":{"name":"Ivy Lin","profile":{"goal_text":"Improve academic writing","goal_summary":"Write clearer arguments","focus_skills":["Writing"],"target_level":"B2","self_level":"B1","weekly_hours":4,"timezone":"Australia/Sydney","availability":[]},"assessments":[],"plan":null,"pending_plan":null,"material_records":[],"observation":"Needs evidence links"}},
  "lessons":[],"materials":[],"reviews":[{"id":"RV-021","kind":"plan","student_id":"student-ivy","subject_id":"PL-021","status":"pending","trigger":"Plan needs approval","decision":null}],
  "teacher_availability":[{"day":"Tue","start":"18:00","end":"20:00"}]
}
```

- **Founder 响应字段**：`user,operations`；`operations` 下有 `agents[],services[],logs[],warnings[],cases[],proposals[],audit[]`。例子中展示一个 Agent 和日志，其他列表为空仍保留键：

```json
{
  "user":{"id":"founder-alex","name":"Alex Hu","email":"alex.hu@example.com","role":"Founder"},
  "operations":{"agents":[{"id":"technical","name":"Technical Manager","status":"active","latest_task":{"id":"TASK-1","status":"completed","confidence":0.91,"output_summary":"Index mismatch diagnosed"}}],"services":[{"name":"retrieval","status":"degraded","last_backup_at":"2026-10-10T00:00:00Z"}],"logs":[{"id":"LG-04","time":"2026-10-11T01:00:00Z","agent_id":"technical","event":"Retrieval mismatch","severity":"warning","task_status":"escalated","confidence":0.71,"escalated":true}],"warnings":[],"cases":[],"proposals":[],"audit":[]}
}
```

- **目标差异**：拟议契约要求列表上限 20/50、`cursor`/`next_cursor` 分页、学生教材卡片只传引用、Founder 不获学生聊天/答案等内容。当前 mock 的角色限制和载荷范围只是演示，真实后端必须自行实施。

### 7.4 `POST /requests`

- **网页**：`/s2` 目标整理/确认、`/s4` 修改计划、`/s5` 改时间、`/s6` 问答/资源/练习、`/t2` 进度分析/建议、`/t5` 备课/教材草稿。`complete_material` 仅在拟议契约中，当前网页尚无按钮。
- **需求**：AR01、AR03–AR08、AR11、AR13；UC01、UC03–UC08。**Agent**：Coordinator 负责分类与路由，按 `type` 分给 Assessment/Consultant/Teaching Assistant；逐动作对照见第 8 节。
- **请求字段**：`type:string`（第 8 节列出 15 种）；`input:object`（随 type 变化）；`student_id?:string`（Teacher 代表学生时传）；`context_id?:string`（关联 lesson 等上下文）。当前 Axios 在可选值为 `undefined` 时不写入 JSON body。

```json
{"type":"explain","input":{"question":"How do I connect evidence to my claim?"}}
```

- **响应字段**：`id:string` 请求 ID、`type:string`、`status:string`、`phase:string`、`result:object`、失败时可有 `error`。当前 mock 的 `phase` 通常与 `status` 相同。下面显示问答的实际响应形状；其他 14 种逐一见第 8 节。

```json
{"id":"RQ-101","type":"explain","status":"completed","phase":"completed","result":{"interaction":{"id":"RQ-101","student_id":"student-ivy","type":"explain","question":"How do I connect evidence to my claim?","answer":"Use a short because bridge: state the evidence, explain what it shows, then connect it to your claim.","feedback":null,"status":"completed","confidence":0.89,"source_refs":[{"material_id":"M-01","title":"Academic Argument Guide","locator":"Unit 3 · pp. 14–18"}],"sent_at":"2026-10-11T01:00:00Z","escalation":null}}}
```

### 7.5 `GET /requests/{id}`

- **网页**：当前客户端已有 `api.getRequest(id)`，但页面未调用；后端接入异步任务后，可用于刷新等待中的排课、升级问答和计划草稿。**需求**：AR11、AR13；相关 UC01/03/04/07/08。**Agent**：无新任务；返回 Coordinator 保存的任务状态。
- **输入**：路径 `id:string`，如 `GET /api/v1/requests/RQ-110`；无 JSON body。必须验证发起人或已分配教师权限。
- **输出**：与 #4 完全相同的 `id,type,status,phase,result,error?` 信封。例如：

```json
{"id":"RQ-110","type":"reschedule","status":"awaiting_confirmation","phase":"awaiting_confirmation","result":{"lesson_id":"L-018","proposed_slot":"2026-10-15T18:00","message":"A proposed time is ready for student confirmation."}}
```

- **目标差异**：拟议契约希望 `phase` 说明具体等待步骤，并用稳定的时段 ID；当前 mock 以 `proposed_slot` 文本比较，且缺少精确的请求归属校验。

### 7.6 `POST /assessments`

- **网页**：`/s3` 点“Start assessment”时，页面用登录用户 ID 作为 `student_id`，按历史记录选 `initial` 或 `milestone`；`/t2` 教师点定向测评时用所选学生 ID、`kind:"directed"` 与文本 `focus`。
- **需求**：AR02、AR05、AR06；UC02、UC05、UC06。**Agent**：Assessment Agent 出题/评估；Coordinator 管理入口。**请求字段**：`student_id:string`、`kind:"initial"|"milestone"|"directed"`、`focus?:string`。当前客户端可能把未填 `focus` 省略。

```json
{"student_id":"student-ivy","kind":"directed","focus":"Evidence-to-claim connections"}
```

- **响应字段**：当前 mock 返回 `id,student_id,kind,focus,answered,answered_items,max_items,status,current_item`。`current_item` 当前是题目文本字符串。前端把 `id` 存入本机以便恢复。

```json
{"id":"AS-101","student_id":"student-ivy","kind":"directed","focus":"Evidence-to-claim connections","answered":0,"answered_items":[],"max_items":3,"status":"in_progress","current_item":"What is the main claim in this short academic argument?"}
```

- **目标差异**：正式后端应让 `current_item` 包含稳定 `item_id`（或另有该字段），以避免当前页面根据题号拼出 `item-1`。教师只能对被分配学生发起 `directed`。

### 7.7 `GET /assessments/{id}`

- **网页**：`/s3` “Resume saved assessment”；从本机保存的 `AS-...` ID 组成 URL。**需求**：AR02/UC02。**Agent**：无新 Agent 调用，读取 Assessment Agent 已保存的 session。
- **输入**：例如 `GET /api/v1/assessments/AS-101`，无 JSON body。学生本人或已分配教师可读。
- **输出**：与 #6 相同的测评 session；例子展示答过一道题后的状态：

```json
{"id":"AS-101","student_id":"student-ivy","kind":"initial","focus":"","answered":1,"answered_items":["item-1"],"max_items":3,"status":"in_progress","current_item":"Explain how one piece of evidence supports that claim."}
```

- **目标差异**：拟议契约允许 `result` 为完整 ProficiencyRecord；当前 mock 完成后把记录写进工作区 `assessments[]`，session 本身不含 `result`。

### 7.8 `POST /assessments/{id}/answers`

- **网页**：`/s3` 学生填写文本答案并点“Submit answer”。当前页面用 `session.answered + 1` 拼 `item_id`；`answer` 来自文本框。
- **需求**：AR02、AR05；UC02、UC05。**Agent**：Assessment Agent；教师只审核低置信结果。**请求字段**：路径 `id` 为 session ID，body 的 `item_id:string`、`answer:string` 必填。

```json
{"item_id":"item-2","answer":"The cited observation supports the claim because it shows the effect in a real case."}
```

- **输出**：当前 mock 返回更新后的 session；未完成时 `answered` 增加并给下一题：

```json
{"id":"AS-101","student_id":"student-ivy","kind":"initial","focus":"","answered":2,"answered_items":["item-1","item-2"],"max_items":3,"status":"in_progress","current_item":"What would you improve in the argument?"}
```

- **完成/低置信**：第三题后响应 `status:"pending_review"`；随后的 `GET /workspace` 新增 `assessments[]` 的 `ProficiencyRecord` 以及教师 `reviews[]`。记录字段例子：

```json
{"id":"A-101","kind":"initial","status":"pending_review","created_at":"2026-10-11T01:00:00Z","level":"B1–B2","confidence":0.62,"strengths":["Academic reading"],"weaknesses":["Evidence links"],"goal_gap":"More reliable evidence needed","feedback":"Your result is provisional until teacher review.","review_note":null,"requested_focus":""}
```

- **幂等性**：同一 `item_id` 重复提交应保持原进度；当前 mock 已按 `answered_items` 检查，但正式后端还需按授权校验 session 归属。

### 7.9 `GET /reviews/{id}`

- **网页**：`/t4` 选择审核条目时自动加载详情；条目 ID 来自 Teacher 工作区 `reviews[]`。**需求**：AR02、AR03、AR07、AR13；UC03、UC06–UC08。**Agent**：无新任务，读取 Assessment/Consultant/Teaching Assistant 产生的待审对象；Human Teacher 决定。
- **输入**：`GET /api/v1/reviews/RV-A104`；无 JSON body，限已分配教师。
- **输出字段**：`review` 包含 `id,kind,student_id,subject_id,status,trigger,decision`；`subject` 根据 `kind` 为完整计划、测评或问答；`evidence` 当前为字符串。

```json
{"review":{"id":"RV-A104","kind":"assessment","student_id":"student-ivy","subject_id":"A-104","status":"pending","trigger":"Low-confidence assessment result","decision":null},"subject":{"id":"A-104","kind":"milestone","status":"pending_review","created_at":"2026-10-10T07:00:00Z","level":"B1–B2","confidence":0.62,"strengths":["Academic reading"],"weaknesses":["Explicit evidence links"],"goal_gap":"C1 academic argument and seminar fluency","feedback":"The current answers do not establish evidence-linking ability reliably.","review_note":null,"requested_focus":"Evidence-to-claim connections"},"evidence":"Low-confidence assessment result"}
```

### 7.10 `POST /reviews/{id}/decision`

- **网页**：`/t4` 教师填写决定说明，点击“Approve & activate”/“Confirm result”/“Answer question”/“Request changes”。**需求**：AR02、AR03、AR07、AR13；UC03、UC06–UC08。**Agent**：决定者是 Human Teacher；确认测评后 Consultant 可生成初始计划，问答由 Teaching Assistant 的升级流程继续。
- **请求字段**：路径 `id`；`action:"approve"|"request_changes"|"confirm_result"|"answer"`；`note:string` 为理由/教师答复，当前 mock 强制非空。拟议契约还可传 `corrected_level?:string`，当前页面没有相应控件。

```json
{"action":"confirm_result","note":"The evidence supports B1; I confirmed the provisional result."}
```

- **当前响应**：仅 `{review}`；`review.status` 变为 `decided`，`decision` 为 action。`GET /workspace` 刷新后才拿到改变的 Assessment/Plan/Interaction；当前页面另行重读 `GET /reviews/{id}`。

```json
{"review":{"id":"RV-A104","kind":"assessment","student_id":"student-ivy","subject_id":"A-104","status":"decided","trigger":"Low-confidence assessment result","decision":"confirm_result"}}
```

- **目标差异**：拟议契约响应另含 `updated_subject`，覆盖水平须传 `corrected_level` 并留依据；计划只经一次教师批准启用，不能因重复提交生成多个活跃版本。

### 7.11 `PATCH /students/{id}/observation`

- **网页**：`/t2` 教师选择学生，在观察文本框输入后点“Save observation”。**需求**：AR06/UC06。**Agent**：无；Human Teacher 记录，Consultant 之后可把它作为分析证据。
- **输入**：路径 `id` 是所选学生 ID；body 的 `note:string` 是文本框全文。

```json
{"note":"Ivy can identify a claim but needs a clearer evidence-to-claim explanation."}
```

- **输出字段**：`note:string` 保存后的内容，`updated_at:string` ISO 时间，`teacher_id:string` 操作者 ID。

```json
{"note":"Ivy can identify a claim but needs a clearer evidence-to-claim explanation.","updated_at":"2026-10-11T01:00:00Z","teacher_id":"teacher-emily"}
```

- **目标规则**：必须是已分配教师。当前 mock 的工作区还在 StudentRecord 中保留 `observation:string`，未保留完整观察记录历史。

### 7.12 `PATCH /teachers/me/availability`

- **网页**：`/t3` 教师修改一周可授课时段后点“Save availability”。**需求**：AR03/UC03、SM4。**Agent**：无直接 Agent；Coordinator 排课时使用已保存时段。
- **请求字段**：`timezone:string` IANA 时区；`availability:Availability[]`，每项 `{day:string,start:string,end:string}`，时间为当地 `HH:mm`。当前客户端固定传 `Australia/Sydney`。

```json
{"timezone":"Australia/Sydney","availability":[{"day":"Tue","start":"18:00","end":"20:00"},{"day":"Thu","start":"17:00","end":"19:00"}]}
```

- **响应**：同一教师的保存结果，字段与请求相同。

```json
{"timezone":"Australia/Sydney","availability":[{"day":"Tue","start":"18:00","end":"20:00"},{"day":"Thu","start":"17:00","end":"19:00"}]}
```

- **目标规则**：服务端应拒绝与现有已预订课时冲突的删除/缩短；当前 mock 直接替换数组，尚未做冲突检查。

### 7.13 `PATCH /lessons/{id}`

- **网页**：`/t3` 教师选择课程，在出席状态与课后反馈控件填写后保存。**需求**：AR05、AR06/UC05、UC06；SM4。**Agent**：无；Human Teacher 写课堂事实，Assessment/Consultant 后续可读。
- **请求字段**：路径 `id` 是 lesson ID；`attendance?:string`、`feedback?:string`。当前页面同时传两个字段，后端不应允许此接口改 `starts_at`/`ends_at`。

```json
{"attendance":"attended","feedback":"Ivy explained the claim well and should add one evidence link."}
```

- **响应**：完整更新后的 Lesson；各字段是 `id,student_id,title,starts_at,ends_at,teacher:{id,name},stage_index,status,classroom_url,attendance,feedback,material_ids[]`。

```json
{"id":"L-018","student_id":"student-ivy","title":"Building an academic argument","starts_at":"2026-10-13T07:00:00Z","ends_at":"2026-10-13T08:00:00Z","teacher":{"id":"teacher-emily","name":"Emily Walker"},"stage_index":1,"status":"completed","classroom_url":null,"attendance":"attended","feedback":"Ivy explained the claim well and should add one evidence link.","material_ids":["M-01","M-02"]}
```

- **目标规则**：只有该课程的教师能写；排课或换时段要通过 Coordinator 请求。当前 mock 一旦 PATCH 即设为 `completed`，正式后端应按课程状态与时间检查。

### 7.14 `GET /materials/{id}`

- **网页**：`/s5` 或 `/s6` 点击教材卡片打开正文；当前 Teacher `/t5` 从工作区直接显示正文，尚未调用此 GET。**需求**：AR04、AR08/UC04、UC08。**Agent**：无新任务；内容可能由 Teaching Assistant 起草并由 Teacher 批准。
- **输入**：例如 `GET /api/v1/materials/M-01`；路径 `id` 来自工作区教材引用，无 body。
- **输出字段**：`id,title,locator,status,lesson_id,content,source_refs[]`；`content` 是正文，`source_refs` 为引用来源。

```json
{"id":"M-01","title":"Academic Argument Guide","locator":"Unit 3 · pp. 14–18","status":"approved","lesson_id":"L-018","content":"A claim tells the reader what you think. Evidence gives an observation or example. Commentary explains why the evidence supports the claim.","source_refs":[]}
```

- **目标规则**：Student 只能看到与自己课程关联且已批准的材料；Teacher 可看本人课程草稿。当前 mock 仅检查是否登录，未完整实施这些权限。

### 7.15 `PATCH /materials/{id}`

- **网页**：`/t5` 教师编辑教材正文，点“Save draft”或“Approve material”。**需求**：AR08/UC08。**Agent**：无新 Agent 生成；Human Teacher 编辑/批准 Teaching Assistant 的草稿。
- **当前请求字段**：路径 `id` 为 Material ID；`content:string` 来自编辑框；`status:"draft"|"approved"` 由两个按钮选择。当前客户端发送的是 `status`，不是原始契约的 `action`。

```json
{"content":"Revised exercise: write one sentence linking evidence to the claim.","status":"approved"}
```

- **当前响应**：完整 Material，包含更新后的正文与状态。

```json
{"id":"M-201","title":"Evidence linking practice","locator":"Teacher draft","status":"approved","lesson_id":"L-018","content":"Revised exercise: write one sentence linking evidence to the claim.","source_refs":[]}
```

- **目标差异**：拟议契约请求为 `{"content":"...","action":"save"}` 或 `{"content":"...","action":"approve"}`；批准后才把 ID 加入 Lesson 的 `material_ids`。接真实后端前需统一前端与后端字段，不能让两个格式暗中并存。

### 7.16 `GET /cases/{id}`

- **网页**：`/f2` 选业务异常、`/f3` 选技术事故时加载详情。**需求**：AR09、AR10/UC09、UC10。**Agent**：无新任务；技术诊断数据由 Technical Manager 产生，业务异常可能由 Coordinator 升级；Founder 阅读。
- **输入**：例如 `GET /api/v1/cases/IN-014`；路径 ID 来自 Founder 工作区 `operations.cases[]`，无 body。
- **输出字段**：`id,kind,status,subject,trigger,diagnosis,evidence:[{ref,summary}],proposal_id,decision,verification`。

```json
{"id":"IN-014","kind":"technical","status":"awaiting_approval","subject":"Retrieval index mismatch","trigger":"Teaching Assistant could not retrieve a cited source reliably.","diagnosis":"The current index references a corpus snapshot that no longer matches.","evidence":[{"ref":"LG-04","summary":"Retrieval failed after one controlled retry."},{"ref":"CHECK-014","summary":"Source identifiers do not match the index snapshot."}],"proposal_id":"UP-08","decision":null,"verification":null}
```

- **权限**：当前 mock 仅 Founder 可读；拟议契约允许获准的 Technical Manager 读取相关 Case，但不因此让 Student/Teacher 读取运营日志。

### 7.17 `POST /cases/{id}/decision`

- **网页**：`/f2` Founder 写说明并点“Approve resolution”或“Request follow-up”。**需求**：AR09、AR13/UC09。**Agent**：决定者是 Founder；后续业务处理由 Coordinator/Teacher 执行。
- **当前请求字段**：路径 `id` 为 Case ID；`action:string` 目前按钮发 `approve_resolution` 或 `request_followup`；`note:string` 为说明。

```json
{"action":"request_followup","note":"Ask the assigned teacher to resolve the course-scope question."}
```

- **当前响应**：完整更新后的 Case；mock 把 `decision` 存为 `action: note` 文本、`status` 设为 `decided`。同时把一项 Audit 写入工作区；该 Audit 不在此响应体里，而在随后的 `GET /workspace` 里返回。

```json
{"id":"ES-13","kind":"business","status":"decided","subject":"A service question remains unresolved","trigger":"The assigned teacher could not resolve a service-level exception.","diagnosis":"The learner needs a human decision about the permitted course scope.","evidence":[{"ref":"ESC-13","summary":"Teacher escalation outcome recorded."}],"proposal_id":null,"decision":"request_followup: Ask the assigned teacher to resolve the course-scope question.","verification":null}
```

- **目标差异**：拟议契约允许 `widen_match | request_teacher | resolve`，而不是当前按钮的两个值；还要求直接响应或后续工作区可追到 Audit。真实后端必须先统一枚举。

### 7.18 `POST /agents/{id}/decision`

- **网页**：`/f3` Founder 在技术事故页输入纠正说明，点“Request correction”。当前页面把路径 ID 固定为 `technical`。**需求**：AR09/UC09。**Agent**：Founder 下决定；目标为 Technical Manager Agent，或将来其他异常 Agent。
- **当前请求字段**：路径 `id` 是 Agent ID；`action:"request_correction"`，`note:string`。拟议契约另外有 `pause` 和 `case_id?`，当前页面未发送。

```json
{"action":"request_correction","note":"Check the retrieval index against the approved corpus snapshot."}
```

- **当前响应字段**：`agent` 对象（`id,name,status,latest_task`）及外层 `status:"requested"`；Audit 随工作区刷新返回。

```json
{"agent":{"id":"technical","name":"Technical Manager","status":"active","latest_task":{"id":"TASK-014","status":"escalated","confidence":0.71,"output_summary":"Index mismatch needs controlled recovery"}},"status":"requested"}
```

- **目标差异**：正式请求可为 `{"action":"pause","note":"Unexpected output","case_id":"IN-014"}`；暂停应改变 Agent 状态并产生审计。当前 mock 只记 `request_correction`，不真正暂停 Agent。

### 7.19 `GET /proposals/{id}`

- **网页**：`/f4` Founder 选择提案时加载详情。**需求**：AR09、AR10、AR12/UC09、UC10。**Agent**：Technical Manager 生成/汇报提案；GET 不触发新 Agent 任务，Founder 阅读。
- **输入**：例如 `GET /api/v1/proposals/UP-08`，路径 ID 来自 `operations.proposals[]`，无 body。
- **输出字段**：`id,type,title,case_id,status,evidence[],before,after,validation,rollback,decision,execution:{status,verification}`。

```json
{"id":"UP-08","type":"recovery","title":"Rebuild the matching retrieval index","case_id":"IN-014","status":"pending","evidence":["One controlled retry failed.","The index and source snapshot do not match."],"before":"Index references the wrong corpus snapshot","after":"Rebuild the index from the approved corpus snapshot.","validation":"Verify source identifiers and retrieval consistency before closing IN-014.","rollback":"Restore the previous approved index snapshot.","decision":null,"execution":{"status":"not_started","verification":null}}
```

- **解释**：`before/after` 让 Founder 比较变更；`validation` 是验证步骤；`rollback` 是失败恢复方式；`execution` 在审批后仍须单独更新，不能因为 `status:"approved"` 就视为执行成功。

### 7.20 `POST /proposals/{id}/decision`

- **网页**：`/f4` Founder 阅读提案后输入说明，点“Approve change”或“Reject”。**需求**：AR09、AR10、AR12/UC09、UC10。**Agent**：Founder 审批；Technical Manager 仅在获批后执行并验证。
- **当前请求字段**：路径 `id` 为 Proposal ID；`action:"approve"|"reject"`；`note:string` 来自说明框。

```json
{"action":"approve","note":"Approved for the exact index snapshot in UP-08; verify source IDs before closure."}
```

- **当前响应**：完整 Proposal，`status` 变为 `approved` 或 `rejected`，`decision` 为文本；`execution` 仍 `not_started`。Audit 在随后工作区刷新中出现。

```json
{"id":"UP-08","type":"recovery","title":"Rebuild the matching retrieval index","case_id":"IN-014","status":"approved","evidence":["One controlled retry failed.","The index and source snapshot do not match."],"before":"Index references the wrong corpus snapshot","after":"Rebuild the index from the approved corpus snapshot.","validation":"Verify source identifiers and retrieval consistency before closing IN-014.","rollback":"Restore the previous approved index snapshot.","decision":"approve: Approved for the exact index snapshot in UP-08; verify source IDs before closure.","execution":{"status":"not_started","verification":null}}
```

- **目标规则**：审批必须绑定所看提案版本；执行、验证、关闭事故分别留审计记录。当前 mock 只演示审批及一条审计，没有真正的后端执行/验证流程。

## 8. `POST /requests` 的 15 种 `type`：逐动作完整请求/响应

所有例子都发送到 **`POST /api/v1/requests`**；每个代码块已经包含完整 JSON body 或完整 JSON 响应信封。`student_id`、`context_id` 只在实际需要时出现。**1–6、8–15 中的 14 种已在当前前端类型或 mock 中；第 7 种 `complete_material` 只属于拟议目标契约。** 相应的 AR/UC 就是提问所说的 UR 对照。示例结果是一个可能的成功分支；低置信、冲突和审核中分支按 `status/phase/error` 区分。

### 8.1 `collect_goal`：整理学习目标

- **页面数据**：`/s2` 的目标文本 `goal_text:string` 和所选技能 `focus_skills:string[]`；当前页面此时**没有**发送水平、周学时或时间。**UR**：AR01/UC01。**Agent**：Coordinator。

```json
{"type":"collect_goal","input":{"goal_text":"I want to write stronger academic arguments.","focus_skills":["Writing","Reading"]}}
```

```json
{"id":"RQ-201","type":"collect_goal","status":"completed","phase":"completed","result":{"summary":"I want to write stronger academic arguments.","focus_skills":["Writing","Reading"]}}
```

- **页面使用**：取 `result.summary` 显示待确认摘要；不会在这一步正式保存 Profile。拟议契约还允许把 `self_level,weekly_hours,timezone,availability` 一起送入此动作，当前页面没有这样做。

### 8.2 `confirm_goal`：确认并保存资料

- **页面数据**：`/s2` 的目标原文、整理摘要、技能、周学时、当前/目标级别。**UR**：AR01/UC01。**Agent**：Coordinator；资料服务保存。

```json
{"type":"confirm_goal","input":{"goal_text":"I want to write stronger academic arguments.","goal_summary":"Stronger academic arguments","focus_skills":["Writing","Reading"],"weekly_hours":4,"self_level":"B1","target_level":"B2"}}
```

```json
{"id":"RQ-202","type":"confirm_goal","status":"completed","phase":"completed","result":{"profile":{"goal_text":"I want to write stronger academic arguments.","goal_summary":"Stronger academic arguments","focus_skills":["Writing","Reading"],"target_level":"B2","self_level":"B1","weekly_hours":4,"timezone":"Australia/Sydney","availability":[]}}}
```

- **页面使用**：随后工作区显示保存后的 Profile，并开放初始测评。拟议契约原字段是 `summary_request_id,confirmed_summary`，当前实现用上例的完整资料字段；真实后端前需统一。

### 8.3 `explain`：解释问题

- **页面数据**：`/s6` 问题框 `question:string`。**UR**：AR04、AR11、AR13/UC04。**Agent**：Coordinator → Teaching Assistant；证据不足时 Human Teacher 审核。

```json
{"type":"explain","input":{"question":"How can I link evidence to a claim?"}}
```

```json
{"id":"RQ-203","type":"explain","status":"completed","phase":"completed","result":{"interaction":{"id":"RQ-203","student_id":"student-ivy","type":"explain","question":"How can I link evidence to a claim?","answer":"Use a short because bridge: state the evidence, explain what it shows, then connect it to your claim.","feedback":null,"status":"completed","confidence":0.89,"source_refs":[{"material_id":"M-01","title":"Academic Argument Guide","locator":"Unit 3 · pp. 14–18"}],"sent_at":"2026-10-11T01:00:00Z","escalation":null}}}
```

- **页面使用**：聊天列表展示 `question,answer,source_refs,status`；低置信时 `interaction.status:"escalated"`、`escalation:{trigger,status}`，并创建 Teacher Review，不能当成已确认解答。

### 8.4 `resources`：查学习资料

- **页面数据**：`/s6` 的问题框；可留空，页面会填默认问题。**UR**：AR04/UC04。**Agent**：Coordinator → Teaching Assistant。

```json
{"type":"resources","input":{"question":"Find learning resources for my current stage"}}
```

```json
{"id":"RQ-204","type":"resources","status":"completed","phase":"completed","result":{"interaction":{"id":"RQ-204","student_id":"student-ivy","type":"resources","question":"Find learning resources for my current stage","answer":"Start with the approved Academic Argument Guide and Evidence & Commentary. Each resource is linked to your current stage.","feedback":null,"status":"completed","confidence":0.89,"source_refs":[{"material_id":"M-01","title":"Academic Argument Guide","locator":"Unit 3 · pp. 14–18"}],"sent_at":"2026-10-11T01:01:00Z","escalation":null}}}
```

- **页面使用**：展示资源标题/定位信息，打开正文再调用 `GET /materials/{id}`。只允许返回该学生当前阶段可访问、已批准的材料。

### 8.5 `practice`：生成轻练习

- **页面数据**：`/s6` “Start practice”当前发送空 `input`；拟议契约可加 `focus?:string`。**UR**：AR05/UC05。**Agent**：Coordinator → Teaching Assistant。

```json
{"type":"practice","input":{}}
```

```json
{"id":"RQ-205","type":"practice","status":"completed","phase":"completed","result":{"question":"Write one sentence that explains how evidence supports your main claim.","source":"Academic Argument Guide"}}
```

- **页面使用**：把 `result.question` 放到练习区。目标契约应额外返回 `item_id` 供答题关联；当前 mock 没有此 ID。

### 8.6 `practice_answer`：提交练习答案

- **页面数据**：`/s6` 练习答案文本 `answer:string`。**UR**：AR05/UC05。**Agent**：Coordinator → Teaching Assistant。

```json
{"type":"practice_answer","input":{"answer":"This evidence supports the claim because it shows the same pattern in a real example."}}
```

```json
{"id":"RQ-206","type":"practice_answer","status":"completed","phase":"completed","result":{"feedback":"Good connection. You explained how the evidence supports the claim."}}
```

- **页面使用**：显示 `result.feedback`，不改变正式测评或活跃计划。目标契约要求 `practice_request_id,item_id,answer`，当前只发送 `answer`，因此真实后端前要补答题关联。

### 8.7 `complete_material`：记录教材完成（目标契约，当前未实现）

- **计划页面**：学生在 `/s5` 或 `/s6` 完成教材后可标记。**UR**：AR05/UC04。**Agent**：Coordinator 路由记录服务，无需让 Teaching Assistant 重新生成内容。

```json
{"type":"complete_material","input":{"material_id":"M-01"}}
```

```json
{"id":"RQ-207","type":"complete_material","status":"completed","phase":"completed","result":{"material":{"id":"M-01","title":"Academic Argument Guide","locator":"Unit 3 · pp. 14–18","completed_at":"2026-10-11T01:05:00Z"}}}
```

- **页面使用**：只更新该学生学习历史中的 `completed_at`。以上是**拟议响应例子**，当前 `RequestType`、MSW 和页面均未接入；不修改原教材内容、批准状态或其他学生的完成时间。

### 8.8 `review_progress`：教师查看学习进度分析

- **页面数据**：`/t2` 选择学生 `student_id`；当前放在外层，不在 `input` 内。**UR**：AR06/UC06。**Agent**：Coordinator → Consultant。目标契约要求分析以已确认测评为依据；当前 mock 简化为读取最新一条测评反馈，即使该条仍待审核。

```json
{"type":"review_progress","student_id":"student-ivy","input":{}}
```

```json
{"id":"RQ-208","type":"review_progress","status":"completed","phase":"completed","result":{"recommendation":"Review Postgraduate study in Philosophy, the latest assessment and the current plan before changing the teaching strategy.","evidence":"The current answers do not establish evidence-linking ability reliably."}}
```

- **页面使用**：向教师显示建议与依据；当前 mock 的输入没有把 `student_id` 复制到 `input`，由外层字段指定对象。真实后端需校验教师分配关系。

### 8.9 `recommend_plan`：提出计划/教学策略建议

- **页面数据**：`/t2` 所选学生 ID，放外层 `student_id`。**UR**：AR07/UC07。**Agent**：Coordinator → Consultant。

```json
{"type":"recommend_plan","student_id":"student-ivy","input":{}}
```

```json
{"id":"RQ-209","type":"recommend_plan","status":"completed","phase":"completed","result":{"recommendation":"Review Postgraduate study in Philosophy, the latest assessment and the current plan before changing the teaching strategy.","evidence":"The current answers do not establish evidence-linking ability reliably."}}
```

- **页面使用**：显示建议，不直接写 `plan`。当前 mock 使用与 `review_progress` 相同的生成模板，因此上述响应文本也相同，正式后端应返回具体建议及可追溯证据。

### 8.10 `revise_plan`：请求修订学习计划

- **页面数据**：`/s4` 学生填写 `reason:string`；当前页面不填 `requested_change`。**UR**：AR03、AR07/UC03、UC07。**Agent**：Coordinator → Consultant；Human Teacher 审核。

```json
{"type":"revise_plan","input":{"reason":"I need more writing practice before seminar work."}}
```

```json
{"id":"RQ-210","type":"revise_plan","status":"pending_review","phase":"pending_review","result":{"plan":{"id":"PL-019-v2","version":2,"status":"pending_review","stage_index":1,"teacher":{"id":"teacher-emily","name":"Emily Walker"},"weekly_hours":6,"stages":[{"title":"Applied writing","course_ref":"CORE-2","start_week":4,"end_week":6,"topics":["Evidence linking"],"milestone":"Explain evidence to claim","status":"upcoming"}],"reason":"I need more writing practice before seminar work.","review_id":"RV-210","approved_at":null},"review_id":"RV-210"}}
```

- **页面使用**：显示待审版本；旧版 `plan` 继续 active。目标契约还允许 `student_id?`、`requested_change`；当前表单只传 `reason`。若已有待审计划，当前 mock 返回 `400 {"message":"Wait for the current plan review before requesting another revision."}`。

### 8.11 `reschedule`：检查新课时

- **页面数据**：`/s5` 当前课程 ID 与 `datetime-local` 字符串 `slot`；外层 `context_id` 同课程 ID。**UR**：AR03/UC03；SM3、SM4。**Agent**：Coordinator。

```json
{"type":"reschedule","context_id":"L-018","input":{"lesson_id":"L-018","slot":"2026-10-15T18:00"}}
```

```json
{"id":"RQ-211","type":"reschedule","status":"awaiting_confirmation","phase":"awaiting_confirmation","result":{"lesson_id":"L-018","proposed_slot":"2026-10-15T18:00","message":"A proposed time is ready for student confirmation."}}
```

- **页面使用**：允许学生点“Confirm time”，此前旧预约保留。目标契约用 `requested_time`（带时区）并返回有稳定 `slot_id` 的时段提案；当前 mock 只回显文本，不是真实可用性检查。

### 8.12 `confirm_slot`：确认选定时段

- **页面数据**：`/s5` 同课程 ID、此前选择的本地 `slot`，以及浏览器转成 UTC 的 `starts_at`。**UR**：AR03；SM4。**Agent**：Coordinator 与排课服务。

```json
{"type":"confirm_slot","input":{"lesson_id":"L-018","slot":"2026-10-15T18:00","starts_at":"2026-10-15T07:00:00.000Z"}}
```

```json
{"id":"RQ-212","type":"confirm_slot","status":"completed","phase":"completed","result":{"lesson":{"id":"L-018","student_id":"student-ivy","title":"Building an academic argument","starts_at":"2026-10-15T07:00:00.000Z","ends_at":"2026-10-15T08:00:00.000Z","teacher":{"id":"teacher-emily","name":"Emily Walker"},"stage_index":1,"status":"confirmed","classroom_url":null,"attendance":"not_recorded","feedback":"","material_ids":["M-01","M-02"]}}}
```

- **页面使用**：重载工作区课程时间。目标契约应只收 `slot_request_id,slot_id`，服务端重新检查冲突并决定准确的 UTC 时间；当前 mock 依赖客户端送来的 `starts_at`，不能当作真实预约实现。

### 8.13 `replace_teacher`：提出更换教师（当前无页面按钮）

- **计划页面**：学生提出原因；**当前 `RequestType`/mock 有此动作，但 18 个页面没有触发控件**。**UR**：AR03/UC03；SM3。**Agent**：Coordinator，必要时 Consultant 匹配；无可用教师时 Founder 介入。

```json
{"type":"replace_teacher","input":{"reason":"I need a teacher available on Thursday evenings."}}
```

```json
{"id":"RQ-213","type":"replace_teacher","status":"pending_review","phase":"pending_review","result":{"plan":{"id":"PL-019-v2","version":2,"status":"pending_review","stage_index":1,"teacher":{"id":"teacher-emily","name":"Emily Walker"},"weekly_hours":6,"stages":[{"title":"Applied writing","course_ref":"CORE-2","start_week":4,"end_week":6,"topics":["Evidence linking"],"milestone":"Explain evidence to claim","status":"upcoming"}],"reason":"I need a teacher available on Thursday evenings.","review_id":"RV-213","approved_at":null},"review_id":"RV-213"}}
```

- **解释**：当前 mock 将它简化为待审计划，尚未真正找到新教师，因此例子里的 `teacher` 仍是原教师。目标契约要求返回匹配提案及无匹配时的 Founder 升级，不应把此 mock 结果误认为换师成功。

### 8.14 `lesson_briefing`：教师备课摘要

- **页面数据**：`/t5` 所选课程 ID；同时放进 `input.lesson_id` 和 `context_id`。**UR**：AR08/UC08。**Agent**：Coordinator → Teaching Assistant。

```json
{"type":"lesson_briefing","context_id":"L-018","input":{"lesson_id":"L-018"}}
```

```json
{"id":"RQ-214","type":"lesson_briefing","status":"completed","phase":"completed","result":{"briefing":"Focus on evidence-to-claim connections. The latest feedback asks for a clearer explanation of significance.","source_refs":["Academic Argument Guide","Evidence & Commentary"]}}
```

- **页面使用**：取 `result.briefing` 显示；正式服务应从已授权计划、确认测评、教师观察、问题和教材取证，并保留引用。

### 8.15 `generate_material`：生成教师可编辑教材草稿

- **页面数据**：`/t5` 的标题 `title` 与所选 `lesson_id`；`context_id` 同课程 ID。**UR**：AR08/UC08。**Agent**：Coordinator → Teaching Assistant；Human Teacher 编辑与批准。

```json
{"type":"generate_material","context_id":"L-018","input":{"title":"Evidence linking practice","lesson_id":"L-018"}}
```

```json
{"id":"RQ-215","type":"generate_material","status":"completed","phase":"completed","result":{"material":{"id":"M-215","title":"Evidence linking practice","locator":"Teacher draft","status":"draft","lesson_id":"L-018","content":"Model: The claim is supported by the evidence because the observation explains the underlying reason. Add a source citation before use.","source_refs":[]}}}
```

- **页面使用**：把新草稿 ID/正文装入编辑器；学生只有在教师 `PATCH /materials/{id}` 批准后才能使用。目标契约要求 `topic,level,type,guidance?` 等生成参数；当前表单只有 `title,lesson_id`，必须在接后端时明确如何补齐。

## 9. 页面控件到接口的完整索引

该表用于从网页反查“点这个按钮会发什么”。所有角色页面在初次登录、刷新或写操作成功后都复用 `GET /workspace`；表内只列页面额外触发的接口。`—` 表示目前只展示工作区数据或进行浏览器内操作，不会额外提交资料给后端。

| 页面 | 网页输入/动作 | 额外接口 | 后端返回给页面的关键字段 |
| --- | --- | --- | --- |
| `/p01` 登录 | 邮箱、密码 | `POST /auth/login` | `session,user`；然后 `GET /workspace`。 |
| `/p02` 注册 | 姓名、邮箱、密码 | `POST /auth/register` | `session,user`；然后 `GET /workspace`。 |
| `/s1` 学生首页 | 查看水平、计划、课程、目标 | — | `workspace.students[id].profile/assessments/plan`、`lessons`。 |
| `/s2` 目标 | 目标文本、技能、级别、周学时；整理/确认 | `POST /requests`（`collect_goal`,`confirm_goal`） | `result.summary`；确认后的 `result.profile`。 |
| `/s3` 测评 | 开始、恢复、文本答案 | `POST /assessments`、`GET /assessments/{id}`、`POST /assessments/{id}/answers` | session 进度、题目；完成后工作区 `assessments[]`。 |
| `/s4` 学习计划 | 修改理由 | `POST /requests`（`revise_plan`） | `result.plan,review_id`；工作区的 `pending_plan`。 |
| `/s5` 课程/时间 | 课程选择、日期时间、教材打开 | `POST /requests`（`reschedule`,`confirm_slot`）、`GET /materials/{id}` | 候选时段、确认后的 Lesson、教材正文。 |
| `/s6` 助手/练习 | 问题、资料查询、练习、答案、教材打开 | `POST /requests`（`explain`,`resources`,`practice`,`practice_answer`）、`GET /materials/{id}` | Interaction、资料引用、题目、反馈、教材正文。 |
| `/s8` 学习历程 | 查看历史 | — | 工作区的 `assessments,plan,lessons,interactions`。 |
| `/t1` 教师首页 | 查看学生、课程、审核队列 | — | 工作区 `students,lessons,reviews`。 |
| `/t2` 学生情况 | 学生选择、观察、进度分析、计划建议、定向测评 | `PATCH /students/{id}/observation`、`POST /requests`（`review_progress`,`recommend_plan`）、`POST /assessments` | 观察记录、分析/建议、测评 session。 |
| `/t3` 课程/时间 | 出席、反馈、可授课时段 | `PATCH /lessons/{id}`、`PATCH /teachers/me/availability` | Lesson 和可授课时段。 |
| `/t4` 审核 | 审核选择、决定及依据 | `GET /reviews/{id}`、`POST /reviews/{id}/decision` | `review,subject,evidence`，随后更新的 Review/工作区。 |
| `/t5` 备课/教材 | 课程选择、备课、生成标题、教材正文、保存/批准 | `POST /requests`（`lesson_briefing`,`generate_material`）、`PATCH /materials/{id}` | 摘要、Material 草稿或已批准 Material。 |
| `/f1` 运营概览 | 查看 Agent、服务、日志、警告 | — | `workspace.operations` 的运营摘要。 |
| `/f2` 业务异常 | Case 选择、决定说明与按钮 | `GET /cases/{id}`、`POST /cases/{id}/decision` | Case 证据/决定；Audit 经工作区刷新。 |
| `/f3` 技术事故 | Case 选择、纠正说明 | `GET /cases/{id}`、`POST /agents/{id}/decision` | 事故详情、Agent 纠正状态；Audit 经工作区刷新。 |
| `/f4` 提案/审计 | 提案选择、批准/拒绝说明 | `GET /proposals/{id}`、`POST /proposals/{id}/decision` | Proposal 状态；Audit 经工作区刷新。 |

**当前没有页面触发的已定义能力**：`GET /requests/{id}`、`replace_teacher` 和拟议中的 `complete_material`。这些接口/动作保留在设计中，不能写成“网页已经调用”。
