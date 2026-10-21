# Course Consultant (Planning Agent)

Implemented against `docs/shared-conventions.md` and the repository's runtime,
domain, dispatcher, escalation and frontend contracts. The Stage 1 report itself
is not in this checkout; figure-level conformance cannot be independently verified.
The supplied assignment describes UC03 and UC07 and informs the workflows below.

## Entry points

`agents.planning.agent.PlanningAgent` is already registered in settings. It handles:

| Task | Behaviour |
| --- | --- |
| `planning.generate_plan` | Consume the confirmed assessment and profile; retrieve courses/materials; ask the shared runtime for a structured, personalised draft; check budget, stage ordering and prerequisites; match a teacher and validate stage lesson times; persist a pending draft and request teacher approval. With an active plan, a new confirmed assessment triggers the existing replan workflow. |
| `planning.revise_plan` | Use a manual reason/change request or upstream progress evidence; keep the active version intact while preparing its replacement for review. |
| `planning.activate_plan` | Verify a resolved, matching teacher approval case, revalidate the persisted curriculum and schedule, activate through the domain service, and book each stage's introductory lesson atomically. A request for changes produces a corrected version and another approval case. |
| `planning.match_teacher` | Prepare a replacement-teacher plan for review, or escalate to the Founder when no verified candidate is available. |
| `planning.propose_slot` | Check the requested time, propose alternatives on conflict, and wait for confirmation. |
| `planning.book_slot` | Interpret local times in the learner's timezone and move the lesson only after the shared domain service checks conflicts again. |

The planning policy uses contiguous stages, distinct courses, prerequisites in
strictly earlier stages, and a maximum two-year horizon. One supervised session
(at most one hour, capped by the weekly budget) is allocated at each stage start;
the remaining weekly hours are independent study. This is an implementation
policy, not a claim that Stage 1 mandates this lesson frequency.

## Boundaries and state

- LLM calls use `AgentRuntime.structured`; catalogue access is registered as a
  read-only `ToolSpec`. Database writes use LearningDomain services exclusively.
- No imports from other agents, Orchestration or AccessControl. No new models,
  migrations, providers, dispatchers, authentication or approval systems.
- Frontend records use `plan_view` and `lesson_view`. Review control keys are at
  the top of `AgentResult.payload`, separate from `payload['result']`.
- Drafts remain `pending_review`; corrections leave the reviewed draft
  `changes_requested`. Only a resolved teacher approval permits activation.
  Replacing an active version makes it `superseded` through the existing service.
- History records contain task/version links, proposed times, assessment evidence
  and the human decision rationale. Domain writes automatically use shared audit.
- Retrying a draft task reuses its version. Replaying an approval for an already
  active version does not book duplicate lessons. Database failures roll back
  plan/stage/lesson changes; runtime trace records the failure.
- An alternative-time confirmation returns through the existing reply mechanism.
  No plan is activated by a student confirmation. Founder cases resume the
  original task after the shared teacher/catalogue data has been updated.
- Model prompts omit account names/emails and use a restricted set of learning
  history kinds. Student ownership and assigned-teacher access are checked.
- `fake.py` is an offline demo hook, invoked only by the shared fake-provider
  selection; normal execution always uses the configured runtime adapter.

## Shared dependencies still requiring their owners

These are limitations, not completed Stage 1 features:

1. **Teacher catalogue and level matching:** available selectors expose only the
   assigned teacher and the configured intake teacher. Matching compares verified
   subject-area words with the objective and focus skills. TeacherProfile has no
   English proficiency/teaching-level field. Searching all teachers, widening
   matching criteria and level-based ranking need a shared teacher catalogue
   selector and an agreed capability contract. Founder decisions currently resume
   against updated shared data; they do not invent a teacher or qualification.
2. **Stage materials:** `create_plan` handles the courses M2M, but passes any
   `materials` key into `PlanStage.objects.create`, which Django rejects for an
   M2M. Materials are retrieved and available through stage courses; direct
   `PlanStage.materials` assignment needs a domain service extension. Planning
   deliberately does not bypass the write layer.
3. **Replacing existing bookings:** the domain has no service for cancelling or
   migrating all future lessons when superseding a plan or replacing a teacher.
   Existing bookings are preserved and treated as conflicts. Their migration
   requires an agreed shared service, not direct ORM changes in this agent.
4. **Concurrent scheduling:** `book_lesson` checks availability/conflicts but
   does not lock a shared student/teacher scheduling resource. Planning's writes
   are transactional and suitable for the documented serial worker/SQLite demo;
   a production concurrent-booking guarantee belongs in the shared domain service.
5. **Progress evidence contract:** the assessment schema has confirmed level,
   strengths, weaknesses and goal gap, but no structured per-milestone deviation
   score. A new assessment conservatively requests replanning; milestone-specific
   automatic decisions need an agreed shared assessment/progress contract.

## Status and reason codes

`AWAITING_APPROVAL`: `teacher_approval_required`.
`NEEDS_ESCALATION`: `teacher_unavailable`, `catalogue_insufficient` (Founder).
`NEEDS_INPUT`: `no_overlapping_availability`, or a slot confirmation.
`TRIGGER_REPLAN`: `new_assessment`.
`FAILED`: `unknown_task_type`, `student_not_found`, `forbidden`, `invalid_input`,
`profile_missing`, `assessment_missing`, `invalid_study_budget`, `reason_required`,
`plan_not_found`, `lesson_not_found`, `review_pending`, `invalid_curriculum`,
`invalid_llm_output`, `llm_unavailable`, `invalid_human_decision`,
`invalid_plan_state`, `invalid_lesson_state`, `stale_plan`, `plan_update_failed`,
plus the shared scheduling error codes (`slot_conflict`,
`outside_teacher_availability`, `invalid_slot`, `slot_required`,
`invalid_slot_selection`).

## Verification

From `backend`, using the repository virtual environment:

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_planning.py tests/test_layers.py -q -p no:cacheprovider
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

The tests use real LearningDomain persistence, the shared runtime/FakeAdapter,
dispatcher, central EscalationManager, audit, and contract validation. They cover
generation, invalid curricula/output, missing data, Founder routing/resumption,
teacher corrections, review/activation, idempotence, rollback, revision safety,
alternative-time continuation, ownership, scheduling conflicts and offline mode.
