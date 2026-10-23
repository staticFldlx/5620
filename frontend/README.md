# LingoPath 前端

LingoPath 的网页端：**18 个产品页面**（登录 / 注册 2 页、学生 7 页、教师 5 页、Founder 4 页），另有演示入口 `/`。默认连接 [后端](../backend/README.md) 的 `/api/v1`；没有后端时也可以切到浏览器内的离线演示模式。

## 运行

需要 Node.js 22.12+ 和 npm。在 `frontend` 目录：

```bash
npm install
npm run dev
```

打开终端显示的地址，通常是 http://localhost:5173/ 。

### 连接后端

先按后端 README 启动后端（默认 `http://127.0.0.1:8000`），再在 `frontend/.env.local` 写入（这个文件不提交）：

```dotenv
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

修改 `.env.local` 后要重启 `npm run dev`。

- **CORS**：后端默认只允许 `http://localhost:5173` 和 `http://127.0.0.1:5173`。Vite 换了端口时，在 `backend/.env` 的 `CORS_ALLOWED_ORIGINS` 里加上新地址。
- **出错时**：后端的错误体带 `message`，页面右下角的提示框直接显示它；请求执行失败时 HTTP 状态码为 422。

### 离线演示模式（不需要后端）

不创建 `.env.local`，或设置 `VITE_USE_MOCK_API=true` 时，MSW 在浏览器里模拟 `/api/v1`（`src/mocks/handlers.ts`，初始数据 `src/mocks/fixture.json`），修改保存在本机 `localStorage`。这种模式只用于演示页面流程，问答和练习都是固定的示例回复，不经过任何 agent。

### 构建与检查

```bash
npm run build      # tsc -b 类型检查 + vite 构建
npm run lint
npm run typecheck
npm run preview
```

GitHub Actions（`.github/workflows/ci.yml`）在每次 push 和 PR 时运行 `npm ci` 和 `npm run build`。

## 演示账号

密码都是 `demo1238`，登录页可以一键填入。

| 角色 | 邮箱 | 首页 |
| --- | --- | --- |
| Student | `ivy.lin@example.com`（另有 `sophia.chen@example.com`） | `/s1` |
| Teacher | `emily.walker@example.com` | `/t1` |
| Founder | `alex.hu@example.com` | `/f1` |

注册只能创建学生账号。

## 页面

| 角色 | 路由和页面 |
| --- | --- |
| Public | `/p01` 登录；`/p02` 注册 |
| Student | `/s1` 首页；`/s2` 学习目标；`/s3` 测评；`/s4` 学习计划；`/s5` 课程与时间；`/s6` 学习助手与练习；`/s8` 学习历程 |
| Teacher | `/t1` 首页；`/t2` 学生学习情况；`/t3` 课程与可授课时间；`/t4` 审核与升级问题；`/t5` 教学准备与教材 |
| Founder | `/f1` 运行概览；`/f2` 业务异常；`/f3` 技术事故；`/f4` 审批与审计 |

未登录访问角色页会转到登录页；用其他角色登录会转到该角色的首页。演示入口 `/` 不是产品功能页。

几个与 agent 交互的地方：

- **`/s2` 学习目标**：点 “Organise my goal” 后，Coordinator 可能先追问（例如学习目的、每周可上课时间），右侧面板显示问题和 “Answer” 按钮，回答会发回同一个请求；得到摘要后点 “Confirm goal” 保存，还没有测评时会出现去 `/s3` 做入学测评的链接。
- **`/s3` 测评**：每题提交后由 Assessment Agent 出下一题；结束后结果交给 Course Consultant 起草计划，计划等教师在 `/t4` 批准。
- **`/s6` 学习助手**：提问、找资料、练习和反馈都由 Teaching Assistant 处理；需要老师决定的问题会显示 “Teacher review”。
- **`/t4` 审核**：计划、低置信测评、升级问题的人工决定；**`/f4` 审批**：变更提案的批准、拒绝和审计记录。

## 技术栈与代码位置

- React 19 + TypeScript 6 + Vite 8
- React Router：页面路由与角色入口
- Tailwind CSS 4 + shadcn/ui 组件：基础样式、按钮、输入框
- Axios：统一的 HTTP 客户端，见 `src/api/client.ts`（自动把登录得到的 token 作为 Bearer 发送）
- React Context + Hooks：会话、工作区、请求状态，见 `src/app-context.tsx`
- MSW：离线演示模式，见 `src/mocks/`
- Motion + CSS：AI 视觉动效、页面反馈与日夜主题

`src/pages/` 按 auth、student、teacher、founder 拆分，页面组件不包含 API 地址。接口类型在 `src/api/types.ts`。所有 agent 请求都通过 `api.request(type, input, studentId?, contextId?)`（`POST /requests`）发出，请求类型和接口列表见后端 README 第 6 节。

## 本地存储

| 键 | 用途 |
| --- | --- |
| `lingopath-session` | 登录 token；清除后需要重新登录 |
| `lingopath-mock-v1` | 离线演示模式的数据；清除后恢复初始演示数据 |
| `lingopath-theme`、`lingopath-motion` | 日夜主题和动效开关；系统设置了“减少动态效果”时会关闭动画 |

连接真实后端时，演示数据保存在后端数据库，用后端的 `python manage.py load_demo_data --reset` 重置。

## 已知问题修复与回归测试

2026-10-23 已修复测评状态、定向测评恢复、Founder 后续执行提示/暂停恢复/放宽匹配、教师私有草稿和显示问题。详见 [修复内容与验证方法](docs/known-issues-fixes.md)。`npm test` 运行请求状态单元测试；`npm run test:e2e` 使用临时后端验证真实页面流程，`AGENT_TASK_EXECUTION=worker npm run test:e2e` 验证异步模式；`npm run test:e2e:mock` 检查离线演示兼容性。

## 新增：教师调整计划、纠正测评、阶段推进

以下操作使用真实后端（`VITE_USE_MOCK_API=false`）。先完成后端迁移，再刷新前端。

### 1. 老师主动修改学习计划（UC07）

1. 老师登录，点击 **My students**，选择目标学生。
2. 在 **Request a plan revision** 的 **Requested plan changes** 填写修改要求与理由。
3. 点击 **Submit plan revision**；当前版本继续生效，新版本显示等待审核，不能重复提交。
4. 点击 **Open reviews**，选择该学生的待审 plan，核对新内容并填写审核备注。
5. 点击 **Approve & activate**。学生刷新 **My learning plan**，应看到新版本；未批准前看到原版本和待审修改。

### 2. 老师纠正待审核测评等级（UC02、UC05）

1. 老师点击 **Reviews & questions** → **assessment**，选择状态为 pending 的测评。
2. 在 **Confirmed level (CEFR)** 选择 A1–C2；保留默认选项则不改 AI 等级。
3. 在 **Decision note and supporting evidence** 写明依据。
4. 点击 **Confirm corrected result**（保持原等级时是 **Confirm result**）。
5. 学生在 **Assessments** 点击 **Refresh result** 或刷新页面，记录应显示 confirmed 及老师确认的等级；首页 Current level 同步更新。

仅待审核记录能在此纠正；已决定的旧记录不会重新开放审核。定向测评入口仍在 **My students → AI progress support → Directed assessment**。

### 3. 自动发布里程碑测评（UC05）

1. 学生在 **My learning plan** 查看 `current` 阶段及 **Milestone target**。
2. 老师进入 **Lessons & availability**，选择这个学生、这个阶段的课程。
3. 上课时间已到后，选择 **Attendance → Attended**，填写 **Lesson observation**，点击 **Save lesson record**。
4. 当前阶段所有未取消课程都按上述记录出席后，系统自动准备一份 milestone assessment。
5. 学生刷新 **Assessments**，点击 **Continue milestone assessment**；无需老师再点 Request assessment。
6. 重复保存同一节课反馈，不应出现重复测评。若 worker 模式，准备需要等待 worker 执行后刷新。

未来课程不能提前记出席；缺席不会算通过。已有历史课程不会因为升级代码而自动改写或发布测评；如当前阶段已经上完，可重新保存该阶段最后一节课的记录以触发检查。

### 4. 阶段推进和最终完成（UC05）

1. 完成第 3 项发布的测评，逐题点 **Submit answer**。
2. 若显示 **Pending teacher review**，先由老师按第 2 项确认等级；此时学生阶段应保持原样。
3. 已确认等级达到 **Milestone target** 且不低于测评开始时等级，学生刷新 **My learning plan**：当前阶段变 completed、下一阶段变 current、版本号不变。
4. 对下一阶段重复“完成课程 → 里程碑测评 → 确认结果”。
5. 最后一个阶段通过后，页面显示 **Your learning plan is complete**，所有阶段 completed，首页 Learning stage 显示 Completed，原计划与结果仍可查看。

### 5. 正常进度保留计划，偏离时申请修改（UC05）

- **正常路径**：按第 4 项完成达标测评；确认计划版本不变，没有新 pending plan。
- **偏离路径**：选另一个有 active 计划的测试学生，完成其阶段测评。若正式结果低于开始时等级或阶段目标，应保留原计划/阶段，同时生成一个待审核的新版本。
- 示例：开始等级 B2、阶段目标 B2，正式确认 B2 则推进；正式确认 B1 则提议修改，等老师在 **Reviews & questions** 批准后才启用。仅在测试账号使用人为构造的等级；真实学生按证据确认。
- 已有待审版本时不会再堆叠新版本；老师也可以主动发起第 1 项的修改。

### 自动化复验

在 frontend 目录执行：

```sh
npm run typecheck
npm run lint
npm test
npm run build
npm run test:e2e
npx playwright test --config playwright.progress.config.ts
AGENT_TASK_EXECUTION=worker npx playwright test --config playwright.progress.config.ts
```

新增浏览器测试使用 8101/5274 端口、临时数据库、离线模型及仅存在于临时库的测试账号，退出后清理，不改变日常开发数据库。测试脚本内的 `progress@test.example` 等账号不是正常 demo 账号。
