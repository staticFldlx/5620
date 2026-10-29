# LingoPath Backend

An API service built with Python + Django + django-ninja. It contains the five AI agents, task orchestration, human review and approval, auditing and access control. The frontend calls it through `/api/v1`.

## 1. Running

Requires Python 3.11 or later (CI uses 3.12). In the `backend` directory:

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env
.venv\Scripts\python run_demo.py
```

On macOS / Linux replace `.venv\Scripts\` with `.venv/bin/` and `copy` with `cp`.

`run_demo.py` runs `migrate`, then `load_demo_data` (skipped when the database already contains demo data), and then starts the server on `127.0.0.1:8000`; when `AGENT_TASK_EXECUTION=worker` it also starts `run_agent_worker`. Use `--host` and `--port` to change the address.

- API docs (OpenAPI): http://127.0.0.1:8000/api/v1/docs
- `.env.example` defaults to `LLM_PROVIDER=fake`: no API key is needed, each agent uses its own offline script, and every flow works end to end.
- Reset demo data: `python manage.py load_demo_data --reset` (clears the database and imports again).
- For connecting the frontend to this service, see [frontend/README.md](../frontend/README.md).

Every demo account uses the password `demo1238`:

| Role | Email |
|---|---|
| Student | `ivy.lin@example.com`, `sophia.chen@example.com` |
| Teacher | `emily.walker@example.com` |
| Founder | `alex.hu@example.com` |

## 2. Configuration

All configuration comes from environment variables. `backend/.env` is loaded automatically (variables already set in the process take precedence); `.env` is not committed and is not included in the source package uploaded to Canvas.

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | An insecure default is used automatically in development | Must be set when `DJANGO_DEBUG=false` |
| `DJANGO_DEBUG` | `true` | Set to `false` for deployment |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | |
| `DATABASE_PATH` | `db.sqlite3` | SQLite file; setting `DATABASE_URL=postgresql://…` switches to PostgreSQL (requires installing `psycopg` separately) |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Address of the frontend dev server; add the new one if you change the port |
| `INTAKE_TEACHER_EMAIL` | `emily.walker@example.com` | Learning-related reviews go to this teacher while the student has no teacher yet |
| `LLM_PROVIDER` | `fake` | `openai` (any OpenAI-compatible API; `school` is an alias) or `fake` |
| `LLM_BASE_URL`, `LLM_API_KEY` | | Required for `openai` |
| `LLM_MODEL_DEFAULT`, `LLM_MODEL_FAST` | | The `fast` tier is used for low-latency calls such as scoring; falls back to the default model when unset |
| `LLM_TIMEOUT_SECONDS` | `30` | Timeout per LLM call; the Technical Manager can override it per agent (see 5.5) |
| `LLM_CAPABILITIES` | `tools,json_schema` | Capabilities supported by the API; fill in from the output of `check_llm` |
| `AGENT_TASK_EXECUTION` | `inline` | `inline`: runs to completion inside the HTTP request; `worker`: only enqueues, and `run_agent_worker` executes it |
| `TASK_TIMEOUT_SECONDS`, `TASK_MAX_ATTEMPTS` | `120`, `2` | Task timeout, and the maximum number of times a timed-out task is requeued |
| `AGENT_CONFIDENCE_THRESHOLD` | `0.70` | The single confidence threshold used across the whole system |
| `TEACHING_SUPPORT_EXPLAIN_MODE` | `single` | Teaching Assistant Q&A: `single` (one structured call) or `loop` (looks up resources with tools first) |
| `TEACHING_SUPPORT_LOOP_BUDGET_SECONDS` | `6` | In `loop` mode, the model is no longer called once this time is exceeded |
| `RETRIEVAL_BACKEND` | `none` | Only `none` is currently implemented |

### Switching the LLM provider

Agents call the LLM only through the shared runtime, so switching providers only changes `.env`, not the code. `.env.example` contains two sample setups:

- **Google Gemini**: a free AI Studio key, using Gemini's OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai`), reachable from anywhere. The free tier allows very few requests per model per day, so use `fake` for development and testing.
- **ELEC5620 course proxy** (`campus-qwen`): you must connect to the USYD VPN first; it is not reachable from cloud hosts.

After changing it, run `python manage.py check_llm`: it tests plain text, JSON schema output and tool calling one by one, and prints the value to use for `LLM_CAPABILITIES`. For capabilities the API does not support, the runtime automatically falls back to requesting JSON output in the prompt.

**Outbound data**: only the fields required to complete the task are sent to external APIs; names, emails and user ids are never sent. Student input is placed only inside tags in the user message, and the model is instructed to treat it as data. Input sent to the Gemini free tier may be used by Google to improve its products.

## 3. Common commands

| Command | Purpose |
|---|---|
| `python -m pytest` | Full test suite (no real LLM calls, no API key needed) |
| `python manage.py load_demo_data [--reset]` | Import demo data; `--reset` clears the database first |
| `python manage.py check_llm [--model …]` | Test which capabilities the current LLM API supports |
| `python manage.py monitor_agents [--once] [--interval 60]` | Technical Manager monitoring: detects anomalies and diagnoses new incidents (see 5.5) |
| `python manage.py run_agent_worker [--once]` | Serial worker for `AGENT_TASK_EXECUTION=worker` |
| `python manage.py ingest_materials` | Import the retrieval corpus (does nothing when `RETRIEVAL_BACKEND=none`) |
| `python manage.py makemigrations --check` | Check that every model change has a migration |

## 4. Architecture

### 4.1 Layers and directories

```
config/            settings (environment variables), urls, wsgi/asgi
access_control/    gateway: API routes, authentication, errors, CORS, workspace assembly
                   identity: users, roles, permissions, load_demo_data
orchestration/     task_queue: dispatcher, pipeline table, result contracts, management commands
                   escalation: EscalationManager (review and approval)
                   audit: audit entry point
                   coordinator: AI Course Coordinator
agents/            runtime: shared Agent Runtime (LLM calls, structured output, tool loop, confidence, trace)
                   assessment / planning / teaching_support / tech_operations: the other four agents
domain/            learning (learning data), governance (tasks, reviews, audit, incidents, proposals)
                   each package is split into models / selectors (read-only) / services (writes) / views (frontend JSON)
infrastructure/    llm (OpenAI-compatible adapter, offline FakeAdapter), retrieval, scheduling, monitoring
fixtures/          demo_*.json demo data
tests/             pytest
```

Dependencies may only point downward: `access_control → orchestration → agents → domain`. Agents may not import each other, `agents.runtime` does not depend on Django or domain, and only `infrastructure` may access the network. `tests/test_layers.py` enforces these rules.

All data writes go through `domain/*/services.py`: each model declares which agents or roles may write to it (`WRITERS`), and every write is checked and audited automatically.

### 4.2 How a request flows

1. **Gateway** (`access_control/gateway`): Bearer token authentication (signed tokens, valid for 7 days by default), role checks, access checks on student data, and input validation against `contracts.py`.
2. **Dispatcher** (`orchestration/task_queue/dispatcher.py`): creates a ServiceRequest and the first AgentTask according to the pipeline table (`pipelines.py`); returns 409 when a precondition check fails.
3. **Agent execution**: the dispatcher loads the agent from `settings.AGENT_REGISTRY`, gives it a shared runtime, and then handles the returned `AgentStatus`:

| Agent returns | Request status (seen by the frontend) | Dispatcher action |
|---|---|---|
| `OK` | `completed` | Runs the next pipeline step; if there is none, merges the step results and validates them against the contract. An OK below the confidence threshold is treated as needing review |
| `TRIGGER_REPLAN` | `completed` | Inserts `planning.revise_plan` as the next step (at most once per request) |
| `NEEDS_INPUT` | `awaiting_confirmation` | Waits for the user's answer; once the user replies with the `context_id`, hands back to the same task_type to continue |
| `NEEDS_ESCALATION` | `escalated` | Opens a review case and assigns it to a teacher or the Founder |
| `AWAITING_APPROVAL` | `pending_review` | Opens an approval case; no change is executed before approval |
| `FAILED` | `failed` (HTTP 422) | The request fails; the error code is the agent's reason code |

Safeguards: at most 6 agent handoffs per request; an uncaught exception from an agent is recorded as `unhandled_exception`; timed-out tasks are requeued according to `TASK_MAX_ATTEMPTS`.

### 4.3 Review and approval (EscalationManager)

All escalations and approvals go through `orchestration/escalation/manager.py`, with one threshold and one set of assignment rules for the whole system:

- Assessment results, learning plans and student questions go to the student's current teacher (or the teacher on the pending plan); when the student has no teacher yet, they go to `INTAKE_TEACHER_EMAIL`.
- Business exceptions and change proposals go to the Founder.
- Teacher actions: for plans, `approve` / `request_changes`; for assessments, `confirm_result` / `request_changes` (optionally with a corrected level); for questions, `answer` / `request_changes`. Every decision must include a note.
- After a decision, the dispatcher continues the original flow with the `resume` task recorded on the case (for example, it runs `planning.activate_plan` once a plan is approved).
- Proposal approvals are bound to a version number; a rejection must include a reason; once approved, the Technical Manager executes and verifies the change.

### 4.4 Audit and trace

- Every write, every request and task status change, and every human decision produces an append-only audit entry (AuditLog cannot be modified or deleted), which is also written to stdout as one line of JSON.
- Agents record their decision rationale with `runtime.note()`, and the model, tokens and latency of every LLM call are recorded automatically. The Founder and the requester can view every step via `GET /api/v1/requests/{id}/trace`.

## 5. The five agents

Every agent inherits from `agents.runtime.AIAgent` and declares the tasks it handles with `task_types`. When `LLM_PROVIDER=fake`, the dispatcher uses the agent's own `fake_script()`, so offline results are reproducible.

### 5.1 AI Course Coordinator (`orchestration/coordinator/`)

The student's first point of contact: turns the learning goal into a structured goal and saves the learner profile (UC01).

| task_type | What it does |
|---|---|
| `coordinator.collect_goal` | Reads the original goal text, the selected skills, the existing profile and earlier Q&A, and uses one structured call to decide whether there is enough information: it needs the learning purpose and weekly availability for lessons. If not, it asks one follow-up question (at most 2 times, `NEEDS_INPUT`, `phase=follow_up_question`); if so, it produces a summary (starting with Academic English / Workplace English / Exam preparation / Everyday English, which the Consultant uses to match a teacher). This step does not write to the database |
| `coordinator.confirm_goal` | Saves the goal, summary, skills, weekly hours and level confirmed by the student; the lesson availability and learning needs gathered from follow-up questions are saved as well, and when the student selected no skills, the skills suggested by the Coordinator are used. When there is no confirmed assessment yet, it returns `phase=initial_assessment_next` to prompt the student to take the initial assessment |
| `coordinator.record_material_completion` | Records a material completion in the learning history (a repeated submission is not recorded twice) |

When the model is unavailable, the summary falls back to the student's original text, so the request does not fail. Reason codes: `invalid_goal`, `student_not_found`, `material_not_found`. Routing itself is decided by the pipeline table based on the request type (every frontend button sends an explicit type); no LLM classification is used.

### 5.2 AI Assessment Agent (`agents/assessment/`)

Adaptive assessment (UC02 initial assessment, UC05 milestone assessment, UC06 teacher-directed assessment).

| task_type | What it does |
|---|---|
| `assessment.conduct_assessment` | Returns `NEEDS_INPUT` for every item; after the student answers (`POST /assessments/{id}/answers`), control returns to the same task. At the end it either publishes the result (`OK`, handed to the Consultant) or sends it to a teacher for review |
| `assessment.apply_review` | Publishes the result after the teacher confirms / corrects the level; when the teacher asks for a reassessment, it ends with `FAILED assessment_changes_requested` and the result does not feed into planning |

- **Skills and starting point**: the student's focus skills take priority; the frontend only has text boxes, so listening, speaking and pronunciation are assessed through written proxies (writing, reading, vocabulary). Starting level: the self-reported level for initial assessments, the most recently confirmed level for milestone / directed assessments, and B1 when neither exists.
- **Item generation and scoring**: one item is generated at a time. The LLM scores each answer from two angles (a rubric score plus a judgement of the CEFR level the answer shows) and averages them; when a score is close to a promotion or demotion threshold, it is scored again independently. Blank or off-topic answers, and answers that try to instruct the model, score 0. When item generation fails, the built-in item bank is used instead, so the assessment is not interrupted.
- **Difficulty and stopping**: a score ≥ 0.75 moves up one level and < 0.4 moves down one level; the assessment stops after at least 4 items once the last 3 ability estimates differ by no more than 0.75 of a level, with a maximum of 6 items.
- **Level and confidence**: the level is computed by rules; the LLM only writes strengths, weaknesses and feedback. Confidence is not self-reported by the model but weighted from three signals: stability 0.5, scoring agreement 0.25, coverage 0.25. When it is below the threshold (`low_confidence`), or more than half of the answers are blank / off-topic (`insufficient_evidence`), the result goes to a teacher for review.
- Prompts are versioned (`assessment.generate_item.v1`, `assessment.score_answer.v2`, `assessment.report.v1`).

### 5.3 AI Course Consultant (`agents/planning/`)

Generates and adjusts personalised learning plans, matches teachers and schedules lessons (UC03, UC07).

| task_type | What it does |
|---|---|
| `planning.generate_plan` | Runs automatically after an assessment is confirmed. Drafts an initial plan when there is none; when a plan already exists, the new assessment result triggers re-planning (`TRIGGER_REPLAN`); when a draft is already awaiting approval, it completes without drafting another |
| `planning.revise_plan` | Drafts a new version after the student or teacher gives a reason (or an assessment result arrives); the current plan stays in effect |
| `planning.activate_plan` | Activates the plan after teacher approval and books one lesson in the first week of each stage; when the teacher requests changes, it produces a revised version and resubmits it for review |
| `planning.match_teacher` | Prepares a new plan for a teacher change; hands over to the Founder when no suitable teacher is found |
| `planning.propose_slot` / `planning.book_slot` | Student rescheduling: checks for conflicts, offers alternative times when there is one, and only makes the change after the student confirms |

- **Drafting**: one structured call whose input is the student profile, confirmed assessments, the course catalogue (read through read-only tools), the previous plan version and the reason for revision, and whose output is a staged plan. The code then validates that weekly hours stay within budget, stages are consecutive, every course actually exists, and prerequisites sit in earlier stages.
- **Teacher matching**: prefers the student's current teacher, then the intake teacher, then other available teachers. The demo environment has only one teacher, so a goal text that does not exactly match the teacher's `subject_areas` does not stop the plan from being submitted for review; the Founder is involved (`teacher_unavailable`) only when there really is no available teacher.
- **Scheduling**: first looks for times when both the student and the teacher are available and checks conflicts with `check_lesson_slot` (NFR-03). When there is no overlap, it schedules into the teacher's free slots over the next 90 days and sends the plan for teacher review; after the teacher approves, the student can request a reschedule in Lessons. It returns `no_available_slots` only when there is truly no conflict-free teacher slot.
- A plan is first saved as `pending_review` and only takes effect once a teacher approves it (`AWAITING_APPROVAL`).

### 5.4 AI Teaching Assistant (`agents/teaching_support/`)

Q&A, resources, practice, analysis for teachers and lesson preparation (UC04–UC08). There is no vector retrieval: the resources are the approved materials in the current stage of the student's plan, and their full text is placed directly in the prompt.

| task_type | Frontend entry point | What it does |
|---|---|---|
| `answer_question` | `/s6` Ask | Answers at the student's level and cites materials; sends the question to the teacher when unsure |
| `retrieve_material` | `/s6` Find resources | Ranks the current stage's materials against the question and writes a short usage guide; records a `corpus_gap` audit when there are no materials |
| `generate_practice` / `give_feedback` | `/s6` Practice | Generates a short exercise based on the current stage and weak areas, with instant feedback after submission; does not change assessments or plans |
| `analyze_progress` / `recommend_adjustments` | `/t2` | Progress analysis for teachers (lists missing data and suggests a directed assessment when needed) and 2–4 plan adjustment recommendations |
| `lesson_briefing` / `generate_material` | `/t5` | Pre-lesson briefing; generates material drafts that students can only see after teacher approval |

- **Q&A confidence** = model self-rating 0.5 + whether the provided materials are cited 0.3 + whether the question is within the learning scope 0.2. Only material ids that were actually given to the model count.
- **Sent to the teacher**: sensitive questions (licensing, copyright, academic integrity), out-of-scope questions, confidence below the threshold, the model being unavailable, or invalid output twice in a row. The student first sees "the teacher will reply", which is replaced automatically once the teacher answers on `/t4`.
- **Two modes**: `single` makes one call; `loop` first lets the model use 4 read-only tools to look up the student's situation and materials, and falls back to `single` when it exceeds the step limit or the time budget.
- Student names that appear in teacher observations, post-lesson feedback and questions are replaced with "the learner".

### 5.5 AI Technical Manager (`agents/tech_operations/`)

System monitoring, diagnosis and controlled updates (UC09, UC10). Every task accepts only requests initiated by the Founder or the system.

| task_type | What it does |
|---|---|
| `tech_operations.apply_correction` | The Founder submits a correction request (free text) on `/f3`. The LLM turns it into a change proposal: adjusting an agent's LLM timeout (5–120 seconds) produces an executable configuration proposal, and any other request produces a manual-handling proposal. Returns `AWAITING_APPROVAL`; after approval it executes within the same request |
| `tech_operations.execute_proposal` | Executes an approved proposal: configuration updates and rollbacks (writes and verifies the timeout override, which `registry.runtime_config` picks up immediately); the recovery type `resume_agent` (resumes a paused agent and verifies it); `retry_request` is only recorded; other types are recorded as `manual_review` and completed by a human |
| `tech_operations.detect_anomalies` | Triggered by the `monitor_agents` command as the internal request `system_monitoring`: computes each agent's task stats over the last 7 days (at least 5 tasks, failure rate ≥ 30% or average latency > 10 seconds) → creates an incident record → runs an LLM diagnosis on new incidents → when recovery is needed, generates a recovery proposal that waits for Founder approval |
| Others | `monitor_agents`, `diagnose_incident`, `generate_report`, `check_student_records`, `check_plan_versions`, used by the code and by the operations endpoints below |

Diagnosis only uses operational data (task counts, failure rate, latency, agent status) and never reads student content. A diagnosis can only recommend one of `retry_request`, `resume_agent`, `request_founder_review` or `no_action`, and all of them require Founder approval before execution.

## 6. API

### 6.1 Endpoints

The 20 endpoints used by the frontend:

| Endpoint | Caller | Description |
|---|---|---|
| `POST /auth/register`, `POST /auth/login` | Visitor | Registration can only create students; login returns a `session` token |
| `GET /workspace` | All three roles | Returns the workspace for the role; teachers may pass `student_id` |
| `POST /requests`, `GET /requests/{id}` | Student, teacher | Starts an agent request (types in 6.2); include the original request's `context_id` when answering a follow-up question |
| `POST /assessments`, `GET /assessments/{id}`, `POST /assessments/{id}/answers` | Student, teacher | Students start initial / milestone assessments; teachers start directed assessments |
| `GET /reviews/{id}`, `POST /reviews/{id}/decision` | Review owner | Human decisions on plans, assessments and questions |
| `PATCH /students/{id}/observation`, `PATCH /teachers/me/availability`, `PATCH /lessons/{id}` | Teacher | Teacher observations, teaching availability, attendance and post-lesson feedback |
| `GET /materials/{id}`, `PATCH /materials/{id}` | Student (approved materials only), teacher | Open, edit and approve materials |
| `GET /cases/{id}`, `POST /cases/{id}/decision` | Founder | Business exceptions and technical incidents |
| `POST /agents/{id}/decision` | Founder | `pause`, `resume`, `request_correction` |
| `GET /proposals/{id}`, `POST /proposals/{id}/decision` | Founder | Viewing and approving change proposals |

There is also `GET /requests/{id}/trace` (the decision process), plus the Technical Manager's operations endpoints for the Founder: `GET /agents/health`, `GET /operations/audit-logs`, `GET /operations/incidents/{id}/timeline`, `GET /operations/maintenance-report`, `GET /operations/students/{id}/record-health`, `GET /operations/students/{id}/archive-eligibility`, `POST /operations/configuration/{id}/execute`, `POST /operations/configuration/{id}/rollback`. The public agent ids are `coordinator`, `assessment`, `consultant`, `assistant` and `technical`.

### 6.2 Request types and pipelines

The `type` of `POST /requests` decides which agents handle the request and in what order (`orchestration/task_queue/pipelines.py`):

| type | Initiator | Pipeline | Main result fields |
|---|---|---|---|
| `collect_goal` | Student | `coordinator.collect_goal` | `summary`, `focus_skills`, or a follow-up `question` |
| `confirm_goal` | Student | `coordinator.confirm_goal` | `profile` |
| `complete_material` | Student | `coordinator.record_material_completion` | `material` |
| `explain` / `resources` | Student | `teaching_support.answer_question` / `retrieve_material` | `interaction` |
| `practice` / `practice_answer` | Student | `teaching_support.generate_practice` / `give_feedback` | `question` / `feedback` |
| `revise_plan` | Student, teacher | `planning.revise_plan` → teacher approval → `planning.activate_plan` | `plan`, `review_id` |
| `reschedule` / `confirm_slot` | Student | `planning.propose_slot` / `planning.book_slot` | `slots` / `lesson` |
| `replace_teacher` | Student | `planning.match_teacher` | `plan` or `message` |
| `review_progress` / `recommend_plan` | Teacher | `teaching_support.analyze_progress` / `recommend_adjustments` | `recommendation`, `evidence` |
| `lesson_briefing` / `generate_material` | Teacher | `teaching_support.lesson_briefing` / `generate_material` | `briefing` / `material` |
| `start_assessment` (`POST /assessments`) | Student, teacher | `assessment.conduct_assessment` → `planning.generate_plan` | `session_id` |
| `agent_correction` (internal) | Founder | `tech_operations.apply_correction` → approval → `execute_proposal` | Proposal |
| `system_monitoring` (internal) | System | `tech_operations.detect_anomalies` | Detection and diagnosis results |
| `decision_follow_up` (internal) | Teacher, Founder | The resume task after a human decision | Varies |

### 6.3 Errors

Every error body has the form `{"message": "…", "error": {"code": "…", "message": "…", "request_id": "…"}}`. Status codes: 400 invalid input, 401 not signed in, 403 forbidden, 404 not found, 409 state conflict (for example, a plan is already pending review), 422 the request ran but failed (the body also carries a `request` envelope), 500 unexpected error.

## 7. Demo data

`load_demo_data` imports `fixtures/demo_*.json` in filename order; each record's `key` is converted to a fixed uuid5, so the ids are identical on every import.

| File | Contents |
|---|---|
| `demo_01_accounts.json` | Four accounts; Emily teaches Academic English and Workplace English and is available on Tuesdays and Thursdays 18:00–20:00 and Saturdays 17:00–18:00 (Sydney time) |
| `demo_02_catalogue.json` | Two course tracks (academic CAT-01–04, workplace WORK-1–4, with prerequisites) and two materials |
| `demo_03_students.json` | Ivy: B2, with an active plan v1 and a pending v2, a milestone assessment awaiting review, an escalated question and two approved materials. Sophia: B1, with an initial plan pending review |
| `demo_04_operations.json` | Operation logs, four pending reviews (RV-019-v2, RV-021, RV-A104, RV-Q09), two business exceptions (ES-12, ES-13), two technical incidents (IN-014, IN-012) and three change proposals (UP-07 corpus, UP-08 recovery, UP-09 configuration) |

## 8. Tests

`python -m pytest` runs the full suite of 202 tests, using the fake LLM, so no API key is needed:

- `test_layers.py`: layering rules; `test_runtime.py`, `test_domain.py`, `test_pipeline.py`, `test_api.py`: the shared layers.
- `test_coordinator.py`, `test_assessment.py`, `test_planning.py`, `test_teaching_support.py`, `test_tech_operations.py`: the five agents, including the full intake flow from registration to plan activation.
- To replace a single agent only, register a test double with the `stubs` fixture from `tests/stub_agents.py`.

GitHub Actions (`.github/workflows/ci.yml`) runs the migration check and the full test suite on every push and PR.

## 9. Deployment

The only runtime dependencies are Django and django-ninja, plus gunicorn in the cloud (`Procfile`); Docker is not needed.

- **Cloud Run**: deploy with `gcloud run deploy --source backend` (buildpacks). In production, set `DJANGO_DEBUG=false`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`.
- **SQLite does not persist on Cloud Run**: after an instance restarts the data goes back to the demo data, and it is not shared between instances, so the maximum instance count must be set to 1. Set `DATABASE_URL` to use PostgreSQL when you need persistence.


### Students withdrawing a plan revision request

`pending_plan.revision_request` in `GET /workspace` contains the student's submitted `reason`,
`submitted_at` and `can_withdraw`. The student page shows the original request and the proposed plan, and hides the duplicate submission form while it is pending review.
`POST /api/v1/plans/{id}/withdraw` only lets a student withdraw their own pending revision request; initial plans, teacher-initiated requests and versions that have already been decided cannot be withdrawn.
Withdrawing keeps the current active plan, existing lessons and history, and closes the review flow for that request. A teacher who opens the old review page can no longer approve it.
A new version can be submitted afterwards; version numbers keep increasing, and a withdrawn version number is never reused. No database migration is needed.


### Lesson rescheduling slot check

On the student side, `Check slot` can be left empty to list up to 5 recommended slots within the next 28 days; when a time is entered, it checks whether the full lesson at that time falls within the teacher's weekly availability window and has no lesson conflicts for either the teacher or the student.
It returns `requested_available`, `slots`, `message`, `teacher_availability` and `teacher_timezone`. When the time is unavailable, the reason is kept and alternatives are offered; when there are no alternatives, the student is prompted to contact the teacher.
After the student picks a returned slot, they confirm it with `confirm_slot` using `slot_request_id` and `slot_id`, and the backend checks for conflicts again. The frontend clears the previous check result when the input is edited or a different lesson is selected.

### UC05: Stage progress and automatic milestone assessments

The new migration `learning.0002` only adds the link between assessments and stages, a snapshot of the level/target taken when an assessment starts, and the link to the request that published the stage assessment; it does not clear or backfill existing business records.

- After a teacher saves a lesson record, if every non-cancelled lesson in the current stage is completed with attendance `attended`, a milestone assessment linked to that stage is published automatically, once. It is not triggered when the stage has no lessons, has an absence or unfinished lessons, or is not the current stage.
- Within the same stage, an assessment that is in progress / awaiting review is reused, so saving feedback repeatedly does not create duplicate assessments. After a teacher asks for a reassessment, the student starts a new round by clicking start assessment again.
- Only confirmed results are used for progress decisions. When the level drops by at least one CEFR level compared with the start of the assessment, or a stage-completion assessment does not reach the stage target, a plan revision is proposed; the original plan stays in effect until the new version is approved.
- The stage target is taken first from an explicit CEFR level in the milestone; otherwise from the highest level among the linked courses, and then from the confirmed level the plan was based on. The target is saved when the assessment is published and shown on the student's plan page. It defaults to B1 when no valid level information exists.
- Target met with no level regression: the stage is marked `completed` and the next stage `current`, and the plan version stays the same; once the last stage is met, the plan is marked `completed`, and the completion record remains visible in the student workspace.
- Mid-stage and teacher-directed assessments in an ordinary stage can detect level regression, but they do not replace the stage-completion assessment linked to the current stage. Late results for older versions or completed stages do not advance the current stage.
- Progress decisions are written to the learning history as `progress_decision`. Automatic requests share the dispatch flow with existing assessments, low-confidence reviews and plan approvals, and support both inline and worker modes.

Regression tests: `pytest tests/test_learning_progress.py tests/test_planning.py`. The tests use an isolated test database and an offline model.
