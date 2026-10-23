# 前端已知问题修复记录

对应 2026-10-22《前端已知问题.md》的 11 项问题。保留现有 Coordinator、审批、权限及离线演示流程；本次没有数据库模型变更，没有新增迁移，不需要清空数据库。

## 修复内容

| 编号 | 修复 | 验证方式 |
|---|---|---|
| 1 | 测评完成显示 Result confirmed；低置信显示 Pending teacher review；等待审核的结果定时刷新，也可手动刷新 | 浏览器覆盖正常完成、低置信后教师确认 |
| 2 | 统一检查 follow_up，区分排队、执行、失败、等待人工审批；失败显示后端原因，Founder 待审批提供 /f4 链接；批准后重新读取提案详情 | 单元测试和浏览器故障注入；后端已有真实执行/失败测试 |
| 3 | Founder agent 卡片提供 Pause / Resume，要求填写原因；继续支持原有 Request correction | 真后端浏览器及离线演示测试 |
| 4 | 普通请求和审批后续执行轮询 GET /requests/{id}；测评正确处理 202；排队答题不会返回旧题目；同步请求超时上限 180 秒，轮询最长等待 180 秒，超时提示先刷新而非重复提交 | inline / worker 两种模式的浏览器测试；异步接口回归测试 |
| 5 | inline-status 保留换行并允许长文本折行 | 浏览器实际检查多行建议与 white-space |
| 6 | 柱状图标签显示 ID 前 8 位，悬停显示事件和完整 ID；兼容无置信度记录 | 浏览器检查标签长度 |
| 7 | error 改为 {code,message}，material_records 改为对象数组；补充测评会话和决策响应类型 | TypeScript、后端响应结构和状态单元测试 |
| 8 | 复核详情返回 draft_answer / draft_source_refs；教师页标记 AI draft (not sent)，仍需教师填写并提交最终回答 | 权限测试与浏览器实际升级问答流程；学生工作区不包含草稿 |
| 9 | 学生工作区返回本人进行中的测评列表，提供继续定向测评入口；刷新/换浏览器依旧能恢复；提交实际 current_item_id | 跨角色、刷新、越权、重复答题回归测试 |
| 10 | 教师课程列表和详情复用工作区学生姓名 | 浏览器课程页验证 |
| 11 | 教师匹配异常提供 Widen teacher match；后端返回 available_actions 控制显示；候选查询覆盖所有有效教师，保留已有/接待教师优先级、专业匹配和时间校验 | 实际 Founder API 放宽后继续审批、教师不可用和候选发现测试；浏览器验证动作值 |

## 重要边界

- 决定保存成功不代表后续执行成功；失败不会被“已记录”提示覆盖。
- 放宽专业匹配不会绕过教师有效性、角色、排课冲突和人工审批。没有可用教师时仍会明确失败。
- 私有 AI 草稿只在已授权的复核详情中返回，学生仍先看到等待教师处理的提示。
- 原有角色权限、数据库历史、人工审批策略保持原有规则。新增教师查询修复候选遗漏，不自动激活计划。
- worker 模式仍需运行 worker；现有 `backend/run_demo.py` 会按 `.env` 配置启动它。本次没有修改用户的运行模式、模型密钥或数据库文件。
- 浏览器测试默认使用离线模型输出，HTTP、身份验证、任务处理和数据库是真实执行；Founder 失败/等待审批分支另外使用明确的网络响应注入，避免依赖不稳定的人工造故障。

## 本地验证

先准备后端 `.venv` 与前端依赖，前端首次浏览器测试运行 `npx playwright install chromium`。

在 backend 目录：

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python -m pytest
```

在 frontend 目录：

```bash
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
AGENT_TASK_EXECUTION=worker npm run test:e2e
npm run test:e2e:mock
```

浏览器测试使用 8101 / 5274 和独立临时 SQLite 数据库；离线演示测试使用 5275。不会占用日常使用的 8000 / 5173，不会读取实际 API key 或修改日常数据库。失败时截图和 trace 保留在 `frontend/test-results/`。

## 使用更新后的版本

保留原来的 `.env`，正常停止并重新启动前后端即可：在 Project 目录运行 `backend/.venv/bin/python backend/run_demo.py`，在 frontend 目录运行 `npm run dev`。新增的 Playwright 仅用于测试；需要运行测试时，先停止前端，再在 frontend 目录运行 `npm ci` 安装依赖。默认 inline 模式可继续使用；需要 worker 时在后端 `.env` 设置 `AGENT_TASK_EXECUTION=worker` 后重启后端。不要在未完成请求时切换模式。

## 本次验证结果（2026-10-23）

- 后端：207 项测试通过；Django 系统检查通过；没有待生成的数据库迁移。
- 前端：lint、类型检查、2 项状态反馈单元测试及生产构建通过。
- 浏览器：inline 模式 5 项、worker 模式 5 项、离线演示兼容性 1 项，全部通过。
- 上述验证在隔离副本及临时数据库中执行，模型使用 fake；没有验证外部 OpenAI 服务的实时可用性。
- 构建仍有单个 JavaScript 包超过 500 kB 的体积提示，不影响本次构建通过。
