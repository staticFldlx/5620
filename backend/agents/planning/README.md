# Course Consultant (Planning Agent)

Implemented against `docs/shared-conventions.md` and the repository's runtime,
domain, dispatcher, escalation and frontend contracts. The Stage 1 report itself
is not in this checkout; figure-level conformance cannot be independently verified.
The supplied assignment describes UC03 and UC07 and informs the workflows below.

## Entry points

`agents.planning.agent.PlanningAgent` is already registered in settings. It handles:

| Task | Behaviour |
| --- | --- |
| `planning.generate_plan` | Consume the confirmed assessment and profile; retrieve courses/materials; ask the shared runtime for a structured, personalised draft; check budget, stage ordering and prerequisites; match a teacher and validate stage lesson times; persist a pending draft and request teacher approval. With an active plan, a new confirmed assessment triggers the existing replan workflow. When another draft is already awaiting teacher review, it completes with the current plan instead of failing the assessment request. |
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
  original task with a verified decision: `widen_match` relaxes subject matching
  (never availability, teacher eligibility or human approval), while an unchanged
  `request_teacher` search returns `teacher_catalogue_update_required` instead
  of endlessly opening identical cases. An inherited widening decision is recorded
  in draft history for later correction rounds.
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
   selector and an agreed capability contract. Available candidates are deduplicated,
   checked for an active teacher role and tried until a compatible multi-stage
   schedule is found. Tests expose the invisible-third-teacher limitation.
2. **Stage materials:** `create_plan` handles the courses M2M, but passes any
   `materials` key into `PlanStage.objects.create`, which Django rejects for an
   M2M. Materials are retrieved and available through stage courses; direct
   `PlanStage.materials` assignment needs a domain service extension. Planning
   deliberately does not bypass the write layer.
3. **Replacing existing bookings:** the domain has no service for cancelling or
   migrating all future lessons when superseding a plan or replacing a teacher.
   Replacement is now explicitly blocked before writes when the old teacher has
   future proposed/confirmed/rescheduling-required lessons, and checked again at
   activation. Replacement without future bookings works and is transactional.
   Migration of existing bookings requires an agreed shared service.
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
`planning_data_changed`, `teacher_reassignment_unavailable`,
`teacher_catalogue_update_required`, `no_available_slots`, `invalid_slot_request`,
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

## Review investigation (2026-10-21)

Only Planning implementation, this document and `tests/test_planning.py` were
changed. No shared components, other agents, contracts or migrations were edited.
The original implementation is preserved and patched rather than replaced.

| Finding | Verified against current code | Correction / regression evidence | Outcome |
| --- | --- | --- | --- |
| Escalation result double wrapping | Not present. `dispatcher.py:217` passes `result=payload` as a keyword to `transition_task`; it does not store the `record` dictionary as the result. `manager.py:61` correctly reads top-level controls. | `test_pending_review_contract_and_control_metadata_are_not_double_wrapped`; `test_teacher_review_api_runs_real_resumption` exercises both human actions through the API. No shared correction required. | Resolved verification |
| Paused frontend results | Review results must satisfy the contract before completion. `_pause` at `dispatcher.py:280` injects review IDs and validates; `_consolidate` at line 300 merges each nonfailed task's business `result`. | Pending review, initial-assessment/session preservation, revision, reschedule, confirm-slot and replacement tests assert real external contracts. Escalated revisions now retain their existing plan in the business result. | Fixed and tested |
| Teacher matching | Current/intake only; first suitable teacher previously ended the search without checking the next candidate's availability. No level field or all-teacher selector exists. | `_teachers` now checks all eligible candidates exposed by existing selectors; complete stage schedules are tried for each. `test_matching_skips_unavailable_current_teacher_and_tries_intake`; `test_extra_qualified_teacher_is_not_visible_without_shared_catalogue`. | Local defect fixed; full matching blocked by shared read interface |
| Unused / bypassed schemas | `RevisePlanTaskInput` was unused and duplicated the task envelope; `PlanResult` was not executed. | Removed duplicate envelope; `_review` executes `PlanResult`; dispatch validates business outputs with Planning-owned plan/slot/lesson/message schemas. Slot inputs and failures also have active validation. The final frontend record contract remains Orchestration-owned. | Fixed |
| Unsafe approval assumptions | Missing latest case and null stored decisions could cause exceptions; case freshness was not checked for correction requests. | Both decision paths validate case freshness, resolved decision, origin task, student/plan, active assigned teacher and plan version. Tests cover missing/latest/superseding cases, null decision, fabricated approval, unrelated teacher, outdated plan and duplicate activation. | Fixed |
| Teacher replacement bookings | New plan activation could leave old future bookings attached to the previous teacher. No shared reassignment operation exists. | Block before mutation when future bookings exist, recheck at activation. Tests cover success without future bookings, explicit blocked replacement preserving all bookings, and rollback on storage failure. | Safe local behaviour fixed; migration blocked by shared service |
| Scheduling granularity and preferences | Frontend displays stage week ranges and independent Lesson records (`student.tsx` Plan/Lessons panels). No weekly lesson frequency requirement is present. Later stages and old draft fallback could bypass changed student preferences. | Retain documented stage-start lesson policy; check every stage against current student preferences and shared teacher/student conflict rules. Only explicit alternative consent permits a recurring local-time override. Alternative lists are filtered against the full stage schedule. DST, later-stage conflicts, changed preferences and selection/resumption tests cover this. | Fixed; frequency remains a documented policy |
| All configured tasks / special statuses | Pipelines name the six registered Planning task types. `TRIGGER_REPLAN` is handled by `_insert_replan` and capped once per request. Reply slot IDs could lose to the original `slot` value. | Reply selection takes precedence, slot request references are ownership/lesson checked. Initial assessment and automatic replanning tests use actual Dispatcher, contracts and persisted confirmed assessment data. UC07 upstream recommendation/evidence now reaches the model and review. | Fixed and tested |
| Founder continuation | Previously reran identical criteria regardless of decision. | Validate the actual resolved Founder case; `widen_match` changes subject criteria, `request_teacher` uses updated shared data or reports the exact dependency once. Tests cover both changed and unchanged data, and widening. | Fixed within available shared data |
| Offline catalogue selection | Previously scheduled every course and could exceed the 104-week schema bound. | Choose relevant goal/skill courses below supported target levels, include prerequisite closure, reject cycles/missing prerequisites, cap at 52 two-week stages. Empty/unsuitable catalogues yield no fabricated stages; both structured-output attempts are scripted. Relevant-course, empty/unsuitable/cyclic/large-catalogue tests verify it. | Fixed; remains offline-only |

### Exact shared interface requests and reproductions

- **LearningDomain teacher read interface:** `domain/learning/selectors.py:75`
  provides only `current_teacher`; `domain/governance/selectors.py:151` looks up
  one configured email. `access_control/identity/models.py:20` stores subject areas
  and timezone, but no teaching-level field. Minimum shared correction: expose
  all authorised active teachers with verified profile/availability information
  through a LearningDomain selector. Agree how teaching-level capability is
  represented before implementing level filtering. Planning must not query
  identity models or inspect teacher accounts with direct ORM queries.
  Reproduce with `pytest tests/test_planning.py -k extra_qualified_teacher`.
  Full UC03 teacher search and replacement when the only eligible new teacher is
  outside the exposed selectors remain blocked.
- **LearningDomain reassignment write interface:**
  `domain/learning/services.py:167` creates a lesson, and line 172 moves its time
  while retaining teacher/student/stage. There is no operation to migrate/cancel
  all future old-teacher bookings. Minimum shared correction: an authorised atomic
  reassignment operation that validates all affected slots, preserves completed
  lesson history, migrates or cancels future bookings according to an agreed
  policy, records audits, and rolls back plan/lesson changes together on failure.
  Reproduce with `pytest tests/test_planning.py -k replacement_with_existing_future`.
  Planning currently fails safely with `teacher_reassignment_unavailable`.
- **Materials and production concurrency:** the existing service gaps described
  above remain unchanged. No upward imports or direct model mutation were added
  to work around them.

### UC03 / UC07 coverage and limits

UC03 profile/confirmed assessment consumption, competency-oriented stages,
catalogue/material retrieval, prerequisites, study budget, stage milestones,
available-teacher matching, conflict checks, alternatives, teacher review,
correction and postapproval activation have executable coverage. Full catalogue
teacher matching/level matching is still blocked as above. Stage materials remain
accessible through real courses rather than the unsupported stage-material write.

UC07 supports assigned-teacher manual changes without a Teaching Assistant
recommendation, upstream recommendations/evidence where provided by the shared
workflow, corrections followed by another review, and safe version replacement.
Tests cover a corrected revision becoming active and database failures retaining
the old active plan. It does not replace Teaching Assistant recommendation logic
or invent milestone scores. Migrating existing bookings across teachers remains
blocked; no claim of full UC03/UC07 completion is made for those shared gaps.

The initial-assessment integration tests enter at the real Planning boundary with
a persisted confirmed assessment and a recorded upstream assessment task; they do
not claim to retest AssessmentAgent's internal evaluation logic. API review tests
exercise actual authentication, review endpoint, manager and Dispatcher resumption.

Verification executed for this review: **60 Planning tests**, **3 architecture
tests**, **93 tests in the focused Planning/layers/pipeline/API run**, and
**181 tests in the complete backend suite**, all passed. `git diff --check` passed.
No external LLM calls were used. The invisible-teacher and existing-booking tests
assert and document shared blockers; their passing does not mean the missing
shared capabilities have been implemented.
