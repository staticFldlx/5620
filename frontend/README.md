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
