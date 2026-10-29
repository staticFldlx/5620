# LingoPath

ELEC5620 Model-Based Software Engineering · Wed 14-16 Group 3

LingoPath is a personalised English education service driven by LLM agents and run by a single founder. Five AI roles handle the consulting, assessment, planning, teaching-assistant and operations work of a language school; human teachers deliver the lessons and make the final academic judgements, while the Founder supervises and approves. Any result the AI is not confident about is handed to a human to decide.

## The five AI roles

| Agent | Requirements | Main capabilities | Human oversight |
|---|---|---|---|
| AI Course Coordinator | AR01, AR11; UC01 | Turns a student's learning goal into a structured goal, asks follow-up questions when information is missing, and saves the learner profile | Saved only after the student confirms |
| AI Assessment Agent | AR02, AR05, AR13; UC02, UC05 | Adaptive assessment: adjusts difficulty item by item, rule-based levelling, explainable confidence | Low-confidence results are confirmed or corrected by a teacher |
| AI Course Consultant | AR03, AR07; UC03, UC07 | Drafts a staged plan from the profile and assessment results, matches a teacher, and schedules lessons within both parties' availability | A plan takes effect only after teacher approval; handed to the Founder when no teacher is available |
| AI Teaching Assistant | AR04–AR08; UC04–UC08 | Q&A (citing materials), finding resources, practice and feedback, teacher-side progress analysis, lesson briefings, material drafts | Sensitive or uncertain questions go to the teacher; material drafts require teacher approval |
| AI Technical Manager | AR09, AR10, AR12; UC09, UC10 | Monitors agents, diagnoses incidents, and turns the Founder's correction requests into change proposals and executes them | All changes and recoveries require Founder approval |

The student intake loop: the Coordinator builds the profile → the Assessment Agent runs the assessment → the Course Consultant drafts a plan → the teacher approves → the plan takes effect and lessons are scheduled → the Teaching Assistant provides day-to-day support → re-planning after milestone assessments.

## Repository structure

| Directory | Contents |
|---|---|
| [`backend/`](backend/README.md) | Python + Django + django-ninja: API, the five agents, task orchestration, review and approval, audit, permissions, demo data and tests |
| [`frontend/`](frontend/README.md) | React + TypeScript + Vite: 18 pages for three roles (student, teacher, Founder) |
| `.github/workflows/ci.yml` | GitHub Actions: frontend build, backend migration check and the full test suite (no real LLM calls) |

## Quick start

Requires Python 3.11+ and Node.js 22.12+. The commands below are for Windows; on macOS / Linux replace `.venv\Scripts\` with `.venv/bin/` and `copy` with `cp`.

**1. Backend** (terminal 1)

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env
.venv\Scripts\python run_demo.py
```

The default is `LLM_PROVIDER=fake`, so the whole flow works without an API key. To connect a real model (Gemini or the course proxy), see section 2 of the backend README.

**2. Frontend** (terminal 2)

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```dotenv
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

Then run `npm run dev` and open http://localhost:5173/ .

**3. Sign in**: every demo account uses the password `demo1238`, and the login page can fill them in with one click.

| Role | Email | Home page |
|---|---|---|
| Student | `ivy.lin@example.com`, `sophia.chen@example.com` | `/s1` |
| Teacher | `emily.walker@example.com` | `/t1` |
| Founder | `alex.hu@example.com` | `/f1` |

You can also register a new student account on the login page and go through the full intake flow, starting from setting a learning goal.

**Reset demo data**: in the `backend` directory, run `.venv\Scripts\python manage.py load_demo_data --reset`.

## More information

- [Backend README](backend/README.md): configuration, commands, architecture, how the five agents work, API, demo data, tests and deployment.
- [Frontend README](frontend/README.md): running it, connecting to the backend, offline demo mode, page list.
- [Render deployment guide](docs/render-deployment.md): a single Web Service serves both the frontend and the API, connected to persistent PostgreSQL.
