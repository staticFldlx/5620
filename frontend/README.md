# LingoPath Frontend

The LingoPath web client: **18 product pages** (2 sign-in / registration pages, 7 student pages, 5 teacher pages, 4 Founder pages), plus a demo entry page at `/`. By default it connects to the [backend](../backend/README.md) at `/api/v1`; without a backend you can switch to an in-browser offline demo mode.

## Running

Requires Node.js 22.12+ and npm. In the `frontend` directory:

```bash
npm install
npm run dev
```

Open the address shown in the terminal, usually http://localhost:5173/ .

### Connecting to the backend

Start the backend first as described in the backend README (default `http://127.0.0.1:8000`), then put the following in `frontend/.env.local` (this file is not committed):

```dotenv
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

Restart `npm run dev` after changing `.env.local`.

- **CORS**: by default the backend only allows `http://localhost:5173` and `http://127.0.0.1:5173`. If Vite picks a different port, add the new address to `CORS_ALLOWED_ORIGINS` in `backend/.env`.
- **Errors**: backend error bodies include a `message`, which the toast in the bottom-right corner of the page shows as is; when a request fails during execution, the HTTP status code is 422.

### Offline demo mode (no backend needed)

When there is no `.env.local`, or `VITE_USE_MOCK_API=true` is set, MSW mocks `/api/v1` in the browser (`src/mocks/handlers.ts`, initial data in `src/mocks/fixture.json`), and changes are saved in the browser's `localStorage`. This mode is only for demonstrating page flows: Q&A and practice return fixed sample replies and never go through an agent.

### Build and checks

```bash
npm run build      # tsc -b type check + vite build
npm run lint
npm run typecheck
npm run preview
```

GitHub Actions (`.github/workflows/ci.yml`) runs `npm ci` and `npm run build` on every push and PR.

## Demo accounts

Every account uses the password `demo1238`, and the login page can fill them in with one click.

| Role | Email | Home page |
| --- | --- | --- |
| Student | `ivy.lin@example.com` (also `sophia.chen@example.com`) | `/s1` |
| Teacher | `emily.walker@example.com` | `/t1` |
| Founder | `alex.hu@example.com` | `/f1` |

Registration can only create student accounts.

## Pages

| Role | Routes and pages |
| --- | --- |
| Public | `/p01` Sign in; `/p02` Register |
| Student | `/s1` Overview; `/s2` Learning goal; `/s3` Assessments; `/s4` My learning plan; `/s5` Lessons; `/s6` Learning assistant and practice; `/s8` Learning record |
| Teacher | `/t1` Overview; `/t2` My students; `/t3` Lessons & availability; `/t4` Reviews & questions; `/t5` Teaching preparation and materials |
| Founder | `/f1` Operations overview; `/f2` Service exceptions; `/f3` Technical incidents; `/f4` Approvals & audit |

Visiting a role page without signing in redirects to the sign-in page; signing in as a different role redirects to that role's home page. The demo entry page `/` is not a product page.

Where the pages interact with agents:

- **`/s2` Learning goal**: after you click "Organise my goal", the Coordinator may first ask a follow-up question (for example about the learning purpose or weekly availability for lessons). The right-hand panel shows the question and an "Answer" button, and the answer is sent back to the same request. Once a summary is ready, click "Confirm goal" to save it; if there is no assessment yet, a link to take the initial assessment on `/s3` appears.
- **`/s3` Assessments**: after each item is submitted, the Assessment Agent generates the next one; at the end, the result goes to the Course Consultant, which drafts a plan that waits for teacher approval on `/t4`.
- **`/s6` Learning assistant**: questions, resources, practice and feedback are all handled by the Teaching Assistant; questions that need a teacher's decision show "Teacher review".
- **`/t4` Reviews**: human decisions on plans, low-confidence assessments and escalated questions; **`/f4` Approvals**: approving and rejecting change proposals, plus the audit records.

## Tech stack and code layout

- React 19 + TypeScript 6 + Vite 8
- React Router: page routing and role entry points
- Tailwind CSS 4 + shadcn/ui components: base styles, buttons, inputs
- Axios: the shared HTTP client, see `src/api/client.ts` (automatically sends the token obtained at sign-in as a Bearer token)
- React Context + Hooks: session, workspace and request state, see `src/app-context.tsx`
- MSW: offline demo mode, see `src/mocks/`
- Motion + CSS: AI visual effects, page feedback and the light/dark theme

`src/pages/` is split into auth, student, teacher and founder; page components contain no API addresses. API types live in `src/api/types.ts`. Every agent request is sent through `api.request(type, input, studentId?, contextId?)` (`POST /requests`); see section 6 of the backend README for the request types and the endpoint list.

## Local storage

| Key | Purpose |
| --- | --- |
| `lingopath-session` | Sign-in token; clearing it means you have to sign in again |
| `lingopath-mock-v1` | Data for the offline demo mode; clearing it restores the initial demo data |
| `lingopath-theme`, `lingopath-motion` | Light/dark theme and motion toggle; animations are turned off when the system "reduce motion" setting is on |

When connected to the real backend, the demo data lives in the backend database; reset it with the backend's `python manage.py load_demo_data --reset`.

## Known issue fixes and regression tests

On 2026-10-23 the following were fixed: assessment status, recovery of directed assessments, Founder follow-up execution hints / pause and resume / relaxed matching, private teacher drafts, and display issues. See [Fixes and how to verify them](docs/known-issues-fixes.md). `npm test` runs the request-status unit tests; `npm run test:e2e` verifies the real page flows against a temporary backend, and `AGENT_TASK_EXECUTION=worker npm run test:e2e` verifies the asynchronous mode; `npm run test:e2e:mock` checks compatibility with the offline demo.

## New: teacher plan revisions, assessment corrections, stage progression

The steps below use the real backend (`VITE_USE_MOCK_API=false`). Run the backend migrations first, then refresh the frontend.

### 1. Teacher-initiated learning plan revision (UC07)

1. Sign in as the teacher, click **My students** and select the student.
2. Under **Request a plan revision**, enter the changes and the reason in **Requested plan changes**.
3. Click **Submit plan revision**. The current version stays in effect, the new version shows as awaiting review, and it cannot be submitted twice.
4. Click **Open reviews**, select the student's pending plan, check the new content and enter a review note.
5. Click **Approve & activate**. When the student refreshes **My learning plan**, they should see the new version; before approval they see the original version together with the pending revision.

### 2. Teacher correcting a pending assessment level (UC02, UC05)

1. As the teacher, click **Reviews & questions** → **assessment** and select an assessment whose status is pending.
2. Choose A1–C2 in **Confirmed level (CEFR)**; leaving the default option keeps the AI level.
3. Write the justification in **Decision note and supporting evidence**.
4. Click **Confirm corrected result** (or **Confirm result** when keeping the original level).
5. The student clicks **Refresh result** in **Assessments** or refreshes the page. The record should show confirmed with the level the teacher confirmed, and Current level on the overview page updates to match.

Only pending records can be corrected here; records that have already been decided are not reopened for review. The directed assessment entry point is still **My students → AI progress support → Directed assessment**.

### 3. Automatically published milestone assessments (UC05)

1. As the student, check the `current` stage and its **Milestone target** in **My learning plan**.
2. As the teacher, open **Lessons & availability** and select this student's lesson in this stage.
3. Once the lesson time has passed, choose **Attendance → Attended**, fill in **Lesson observation** and click **Save lesson record**.
4. Once every non-cancelled lesson in the current stage has been recorded as attended this way, the system automatically prepares a milestone assessment.
5. The student refreshes **Assessments** and clicks **Continue milestone assessment**; the teacher does not need to click Request assessment.
6. Saving the same lesson feedback again should not create a duplicate assessment. In worker mode, wait for the worker to run before refreshing.

Future lessons cannot be marked as attended in advance, and an absence does not count as a pass. Existing past lessons are not rewritten, and no assessments are published for them, just because the code was upgraded; if the current stage has already been completed, save the record of the stage's last lesson again to trigger the check.

### 4. Stage progression and final completion (UC05)

1. Complete the assessment published in section 3, clicking **Submit answer** for each item.
2. If **Pending teacher review** appears, the teacher first confirms the level as in section 2; the student's stage should stay unchanged at this point.
3. When the confirmed level reaches the **Milestone target** and is not lower than the level at the start of the assessment, the student refreshes **My learning plan**: the current stage becomes completed, the next stage becomes current, and the version number stays the same.
4. Repeat "finish the lessons → milestone assessment → confirm the result" for the next stage.
5. After the last stage is passed, the page shows **Your learning plan is complete**, every stage is completed, Learning stage on the overview page shows Completed, and the original plan and results remain viewable.

### 5. Normal progress keeps the plan; deviation requests a revision (UC05)

- **Normal path**: complete a passing assessment as in section 4, then confirm that the plan version is unchanged and there is no new pending plan.
- **Deviation path**: pick another test student with an active plan and complete their stage assessment. If the official result is below the starting level or the stage target, the original plan/stage should be kept, and a new version awaiting review is created alongside it.
- Example: with a starting level of B2 and a stage target of B2, an officially confirmed B2 advances the stage, while an officially confirmed B1 proposes a revision that only takes effect after the teacher approves it in **Reviews & questions**. Only use artificially constructed levels on test accounts; real students' levels should be confirmed from evidence.
- When a pending version already exists, no further version is stacked on top of it; teachers can also start a revision themselves as in section 1.

### Automated re-verification

In the `frontend` directory, run:

```sh
npm run typecheck
npm run lint
npm test
npm run build
npm run test:e2e
npx playwright test --config playwright.progress.config.ts
AGENT_TASK_EXECUTION=worker npx playwright test --config playwright.progress.config.ts
```

The new browser tests use ports 8101/5274, a temporary database, an offline model and test accounts that exist only in the temporary database; everything is cleaned up on exit, and the everyday development database is not changed. Accounts such as `progress@test.example` in the test scripts are not regular demo accounts.
