# Assessment Agent integration

The browser calls the shared REST gateway; the agent does not call a frontend API.
The gateway and task queue invoke `assessment.conduct_assessment` and `assessment.apply_review`.
The shared architecture and deployment instructions are in `backend/README.md`.

## Existing frontend contract

All paths below use the `/api/v1` prefix and the authenticated Bearer session.

| Frontend method (`frontend/src/api/client.ts`) | HTTP request | Behaviour |
| --- | --- | --- |
| `startAssessment(studentId, kind, focus)` | `POST /assessments` with `student_id`, `kind`, optional `focus` | Student: initial/milestone; assigned teacher: directed |
| `getAssessment(id)` | `GET /assessments/{id}` | Resume a session or view saved answers/result; a proficiency record ID also resolves to its session |
| `answerAssessment(id, itemId, answer)` | `POST /assessments/{id}/answers` with `item_id`, `answer` | Advance one item or return the completed/provisional result |
| `getReview(id)` | `GET /reviews/{id}` | Teacher reads review evidence |
| `decideReview(...)` | `POST /reviews/{id}/decision` with `action`, `note`, optional `corrected_level` | `confirm_result` publishes; `request_changes` stops planning and requires reassessment |
| `getRequest(id)` | `GET /requests/{id}` | Poll queued/running work; `GET /requests/{id}/trace` exposes agent decisions |

The student UI is `/s3`, teacher-directed assessments are on `/t2`, and reviews are on `/t4`.
`200` returns an assessment session with `current_item_id`, `current_item`, `answered`, `max_items`, `responses`, `result`, and `follow_up`.
In worker mode `202` returns a request envelope; the existing client polls it and fetches its `result.session_id`.
Use `VITE_USE_MOCK_API=false` to exercise the real backend.

A confirmed assessment continues to the real `planning.generate_plan` agent. Low-confidence or insufficient evidence pauses for teacher review. A rejected result never feeds planning.
Automatic milestones retain the shared stage validation and persisted `milestone_stage`, `baseline_level`, and `milestone_target_level` fields. The shared milestone publisher owns automatic triggering; the assessment agent owns evaluation.

## Recovery and safeguards

- A saved answer resumes scoring and next-item generation, rather than prematurely finishing.
- The fake LLM script reconstructs only the remaining calls and preserves already saved scores, including unavailable scores.
- If a worker stops after saving a proficiency record or final session, an unfinished matching task restores the result handoff and session status without rescoring or duplicating the profile.
- Teacher-rejected results remain rejected even if an old task is retried.
- An existing session with an awaiting-input, queued or running request blocks a second assessment. Orphan sessions with no live request do not block new work. This guard is not a database-level guarantee against two simultaneous first starts before either creates a session.
- Focus text is capped at 200 characters; learner text sent to prompts is escaped. Stability uses rounded spread at the 0.75 boundary; skill names use word matching; an entirely unscored assessment retains its starting level for teacher review.

## Validation (2026-10-24)

Based on main `05bc1f8`, incorporating the previously unmerged acceptance fixes from `07d1e27`.
Backend: `python -m pytest -p no:logging` from `backend` ? **311 passed**.
Migration check: `python manage.py makemigrations --check --dry-run` ? no changes.
The 50 restored acceptance tests and 10 additional retry tests cover the recovery paths above.
Frontend typecheck and production build passed; no frontend application code was changed.
Tests use isolated databases and `LLM_PROVIDER=fake`; they validate real application integration, not live-provider score quality or availability.

For browser verification use the existing Playwright regression, assessment-history and progress suites. Keep the progress seed data isolated: the history test assumes Ivy is the default student after a teacher-page reload. On Windows the backend Python executable in the Playwright webServer command must be quoted (an unquoted `../backend/...` command fails under cmd.exe).

Browser results: six selected inline workflows passed, plus teacher-directed assessment and teacher confirmation in worker mode (two passed). The history workflow passed with its original fixture after isolation from progress-only seed data.
