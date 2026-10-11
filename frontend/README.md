# LingoPath frontend

Stage One 的可运行前端原型。包含 **18 个产品页面**：登录/注册 2 页、学生 7 页、教师 5 页、Founder 4 页；`/` 是额外的演示入口（因此总共可访问 19 个路由页面）。现在没有真实后端。默认使用 MSW 在浏览器内模拟 `/api/v1`，模拟记录会存入本机 `localStorage`。

## 运行

要求 Node.js 22.12+ 和 npm。在 `frontend` 目录运行：

```bash
npm install
npm run dev
```

打开终端显示的本地地址，通常是 `http://localhost:5173/`。构建与检查：

```bash
npm run build
npm run lint
npm run preview
```

演示账户（密码均为 `demo1238`）：

| 角色 | 邮箱 | 首页 |
| --- | --- | --- |
| Student | `ivy.lin@example.com` | `/s1` |
| Teacher | `emily.walker@example.com` | `/t1` |
| Founder | `alex.hu@example.com` | `/f1` |

登录页可一键填入演示账户。注册只创建 Student 模拟账户。清除浏览器的 `lingopath-mock-v1` 和 `lingopath-session` 可重置演示记录和登录状态。日夜主题与动效开关分别使用 `lingopath-theme`、`lingopath-motion` 保存；系统“减少动态效果”设置会关闭动画。

## 技术栈与代码位置

- React 19 + TypeScript 6 + Vite 8
- React Router：页面路由与角色入口
- Tailwind CSS 4 + 现有 shadcn/ui 组件：基础样式、按钮、输入框
- Axios：统一 HTTP 客户端，见 `src/api/client.ts`
- React Context + Hooks：会话、工作区、请求状态，见 `src/app-context.tsx`
- MSW：无后端时模拟 HTTP，见 `src/mocks/handlers.ts`；初始数据在 `src/mocks/fixture.json`
- Motion + CSS：局部 AI 视觉动效、页面反馈与日夜主题

`src/pages/` 按 public、student、teacher、founder 拆分；页面组件不包含 API 地址，也不直接读写模拟数据库。API 类型在 `src/api/types.ts`；完整的 Stage One 拟议接口原始契约在 `src/api/contract.json`。视觉和交互参考来自用户提供的 `LingoPath_Core_Data_Preview_Pack.zip`，其 18 个页面代码为 P01/P02、S1–S6/S8、T1–T5、F1–F4。

## 页面

| 角色 | 路由和页面 |
| --- | --- |
| Public | `/p01` 登录；`/p02` 注册 |
| Student | `/s1` 首页；`/s2` 学习目标；`/s3` 测评；`/s4` 学习计划；`/s5` 课程与时间；`/s6` 学习助手与练习；`/s8` 学习历程 |
| Teacher | `/t1` 首页；`/t2` 学生学习情况；`/t3` 课程与可授课时间；`/t4` 审核与升级问题；`/t5` 教学准备与教材 |
| Founder | `/f1` 运行概览；`/f2` 业务异常；`/f3` 技术事故；`/f4` 审批与审计 |

未登录访问角色页会转到登录页；登录其他角色会转到该角色首页。演示入口 `/` 不是产品功能页。

## API 边界

默认 `VITE_USE_MOCK_API` 为启用状态，MSW 拦截 `/api/v1`。接入真实后端时，创建 `.env.local`：

```dotenv
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=https://your-server.example/api/v1
```

之后由真实后端实现相同响应结构和权限校验。Axios 自动把 `lingopath-session` 作为 Bearer token 发送。生产接入时还需要后端会话管理、严格角色授权、数据持久化与真实 AI/测评/恢复服务；目前的前端模拟结果只用于演示流程，不代表这些服务已实现。页面中所有计数、排序、日历与阶段展示都由已取得的基本记录计算，不需要额外 dashboard、通知、作业、支付、成本或搜索接口。

目前拟议的 20 个 HTTP 操作：

| 领域 | 方法与路径 | 页面用途 |
| --- | --- | --- |
| 认证 | `POST /auth/register`, `POST /auth/login` | Student 注册；按角色登录 |
| 工作区 | `GET /workspace` | 按角色取得最小工作区记录；教师可带 `student_id` |
| Coordinator 请求 | `POST /requests`, `GET /requests/{id}` | 目标、计划、时段、学习助手、练习、建议、备课与教材草稿 |
| 测评 | `POST /assessments`, `GET /assessments/{id}`, `POST /assessments/{id}/answers` | 开始、恢复、提交自适应测评 |
| 教师审核 | `GET /reviews/{id}`, `POST /reviews/{id}/decision` | 计划、低置信结果、升级问题的人工决定 |
| 教学记录 | `PATCH /students/{id}/observation`, `PATCH /teachers/me/availability`, `PATCH /lessons/{id}` | 教师观察、时间、出席与反馈 |
| 教材 | `GET /materials/{id}`, `PATCH /materials/{id}` | 打开正文、编辑与批准 |
| 运营 | `GET /cases/{id}`, `POST /cases/{id}/decision`, `POST /agents/{id}/decision` | 异常详情、Founder 决定、纠正请求 |
| 变更审批 | `GET /proposals/{id}`, `POST /proposals/{id}/decision` | 变更对照、审批与审计 |

`POST /requests` 当前前端已接入 14 种请求：`collect_goal`, `confirm_goal`, `revise_plan`, `reschedule`, `confirm_slot`, `replace_teacher`, `explain`, `resources`, `practice`, `practice_answer`, `review_progress`, `recommend_plan`, `lesson_briefing`, `generate_material`。页面通过 `api.request(type, input, studentId?, contextId?)` 调用，不为每张卡片增加接口。

原始拟议契约共有 15 种动作；第 15 种 `complete_material` 尚未接入当前前端。20 个接口逐项的网页输入、请求 JSON、后端响应 JSON、AR/UC 需求与 Agent，以及 15 种请求动作和页面索引，见 [API 逐接口对接说明](./API_UR_Agent_Design.md)。

## 当前模拟范围

- MSW 以固定初始记录演示审核门槛：新学生确认目标后参加测评，暂停后可恢复；低置信结果经教师确认后生成待审初始计划；计划需教师一次批准才启用；课程新时段单独确认；教材由教师编辑批准；Founder 审批与执行/验证分开。
- 模拟问答与练习使用确定性的示例回复，没有连接 LLM、课程平台或真实教室。
- 注册、登录、数据修改仅保存在当前浏览器。不要把演示密码和浏览器存储方案用于真实部署。
- GitHub Actions 暂未配置，按此前约定留到后续阶段。
