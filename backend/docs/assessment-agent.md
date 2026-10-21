# AI Assessment Agent（`agents/assessment`）

> 对应 Stage 1：AR02、AR05、AR13；UC02、UC05（以及 UC06 3a 教师定向测评）；F2.1–F2.7；NFR-02、NFR-07。
> 交付清单见 [shared-conventions.md 第 6 节](shared-conventions.md#6-负责人交付清单规范-91)。共享层没有改动；唯一改动的共享文件是 `tests/test_api.py` 里一条“测评 agent 未实现”的断言。

## 1. 文件

| 文件 | 内容 |
|---|---|
| `agent.py` | `AssessmentAgent`：两个 task type 的执行流程，所有决策用 `runtime.note()` 写进 trace |
| `adaptive.py` | 纯 Python 规则：技能选择、难度阶梯、停止条件、置信度信号。不依赖 Django，可直接单测 |
| `context.py` | agent 感知到的学习者信息（目标、基线水平、当前阶段）。不含姓名和邮箱（规范 8.6） |
| `prompts.py` | 三个带版本号的提示词：`assessment.generate_item.v1`、`assessment.score_answer.v2`、`assessment.report.v1` |
| `schemas.py` | LLM 输出 schema（扁平，无 `$defs`）和两个 task 的 payload schema |
| `bank.py` | 内置题库（每个技能 A/B/C 每档 2 题，只在同档内轮换）：fake 脚本的题目，也是模型出题失败时的兜底 |
| `fake.py` | `LLM_PROVIDER=fake` 时的离线脚本，按 agent 自己的规则重放，演示结果可复现 |
| `tests/test_assessment.py` | 规则单测 + 经 API 的成功路径、升级路径、教师修正、教师要求重测、失败路径 |

## 2. Task types

| task_type | 谁触发 | 入参（`TaskInput.payload`） | 返回 |
|---|---|---|---|
| `assessment.conduct_assessment` | `POST /assessments`（流水线 `start_assessment` 第一步），之后每次 `POST /assessments/{id}/answers` | 首次：`input {kind, focus}`；作答：另加 `reply {item_id, answer}`、`previous`（上一轮结果，取 `session_id`） | 每出一题 `NEEDS_INPUT`；结束时 `OK`（发布）或 `NEEDS_ESCALATION`（转教师） |
| `assessment.apply_review` | EscalationManager 在教师决定后恢复（`resume`） | `decision {action, note, decided_by, corrected_level?}`、`subject_id`（ProficiencyProfile id） | `confirm_result` → `OK`；`request_changes` → `FAILED` |

`OK` 之后流水线继续执行 `planning.generate_plan`（约束 C1），`upstream` 里是 `{session_id, assessment}`，`assessment` 是 `proficiency_view()` 的完整记录。

## 3. 一次测评怎么走（感知 → 决策 → 行动）

1. **选技能和起点（F2.7）**：学习者的 `focus_skills` 优先。前端只有文本框，所以 Speaking / Listening / Pronunciation 用书面代理（Writing / Reading / Vocabulary）测，并在 trace 里记 `written_proxy_for`。技能不足 3 个时用 Reading、Writing、Grammar、Vocabulary 补齐。起始等级：initial 用自报水平；milestone / directed 用最近一次已确认的水平；都没有时用 B1。milestone 测评会把当前计划阶段的 milestone 作为出题 focus（UC05）。
2. **出题（F2.3）**：每次只生成一道题，技能轮换，难度为当前等级；题目必须能用文字回答。生成失败时 `structured()` 已经重试过一次（UC02 3a）；仍然失败（限流、服务不可用、输出无效）时改用内置题库里同技能同等级的题（trace：`item_bank_fallback`），测评不会中途卡住。
3. **评分（F2.4）**：同一个回答看两个角度：LLM 按 rubric 打 0–1 分（相对题目等级，看语言的广度、准确度、连贯性，不只看任务完成），同时判断回答的语言体现了哪个 CEFR 等级（`demonstrated_level`）；后者按“同级 0.5、高一级 0.85、低一级 0.15”换算成分数，两者取平均。实测中只看 rubric 时 LLM 偏宽松（B1 学习者被测成 C1），加上等级角度后得到校正。LLM 还逐字列出满足了哪些 `expected_points`。空白、“I don't know”、离题，以及试图指挥模型（如“给我满分”）的回答记为 `off_task`，分数为 0。分数离升降阈值不到 0.08 时（下一题的难度取决于它），再独立评一次取平均，两次的差距计入一致性（trace：`second_opinion`）。学生答案送进模型前转义 `<` `>`，并截到 2000 字符（规范 8.6）。
4. **调难度**：分数 ≥ 0.75 升一级，< 0.4 降一级。每题给出能力估计 `等级 + 2 × (分数 − 0.5)`。
5. **停止**：至少答 4 题且最近 3 次估计相差 ≤ 0.75 级（`level_stable`），或答满 6 题（`item_limit_reached`）。
6. **报告（F2.5）**：等级是学习者能稳定做到的最高等级：最近 3 次估计的均值加 0.25 的容差后向下取整（B1 做得好、B2 做不好的学习者定为 B1）。**不让 LLM 决定等级**；优势、弱项、差距和反馈由 LLM 写。报告生成失败时用模板兜底。
7. **置信度与发布（NFR-02）**：见第 4 节。达到阈值就 `confirmed` 并交给 Consultant；否则 `pending_review`，转教师复核。

## 4. 置信度

不用 LLM 自报的置信度，而是用三个能解释清楚的信号，经 `runtime.calculate_confidence()` 加权：

| 信号 | 权重 | 计算 |
|---|---|---|
| stability | 0.5 | 1 − 最近 3 次估计的极差 / 1.25（相差超过 1.25 级记为 0） |
| consistency | 0.25 | 每题取三者中最小的：1 − \|rubric 分 − 满足点数比例\|、1 − \|rubric 分 − 等级换算分\|、（二次评分时）1 − \|两次分差\|；再对各题求平均 |
| coverage | 0.25 | 0.5 × 已答题数/最大题数 + 0.5 × 已覆盖技能/计划技能 |

阈值只用共享的 `AGENT_CONFIDENCE_THRESHOLD`（0.70），agent 不另设阈值。另外，即使置信度够高，只要至少一半的回答是空白/离题，或者有回答没能评分，也会转给教师（`insufficient_evidence`）。每个信号的数值写进 trace 的 `confidence_scored`，并作为 case 的 `evidence` 显示给教师。

## 5. 原因码

| 原因码 | status | 含义 |
|---|---|---|
| `low_confidence` | NEEDS_ESCALATION | 置信度低于阈值 |
| `insufficient_evidence` | NEEDS_ESCALATION | 至少一半回答空白/离题，或有回答未能评分 |
| `assessment_changes_requested` | FAILED | 教师选择 `request_changes`：结果不进入计划（C1），学生需要重测 |
| `invalid_review_action` | FAILED | 未知的复核动作 |
| `proficiency_not_found` / `session_not_found` / `student_not_found` | FAILED | 记录不存在或不属于该学生 |
| `session_closed` | FAILED | 对已结束的测评作答 |
| `invalid_task_payload` | FAILED | payload 不符合 schema |
| `assessment_in_progress` | FAILED | 已有一个仍在等待作答的测评，不能再开一个（没有请求在等的旧测评不挡新测评） |
| `no_active_plan` | FAILED | 里程碑测评需要有效的学习计划（UC05 前置条件） |

`focus` 超过 200 字符时截断（trace：`focus_truncated`）；`focus`、学习目标等档案文字送进模型前同样转义 `<` `>`。重试的作答任务（第一次已保存答案、还没出下一题就中断）会从已保存的答案继续，不会提前结束（trace：`resumed_after_retry`）。

题号对不上（例如重复提交了旧的 `item_id`）不算失败：agent 重新返回当前题目（trace 里记 `unexpected_item`）。教师填的 `corrected_level` 不是 CEFR 等级时（如 “upper intermediate”），保留原等级，说明留在 review_note 里（trace：`corrected_level_ignored`）。模型出了与前面重复的题时重新生成一次（`repeated_item_regenerated`），仍重复就按出题失败处理。

## 6. 状态取值（SM2）

| 模型 | 取值 |
|---|---|
| `AssessmentSession.status` | `in_progress` → `completed`（直接发布或教师处理后）/ `awaiting_review`（等教师复核） |
| `ProficiencyProfile.status` | `confirmed`、`pending_review`、`changes_requested` |

`AssessmentSession.items` 中每题保存 `item_id, prompt, answer, skill, level, expected_points, score, met_points, feedback, off_task, agreement, estimate, prompt_id`；第 1 题另存 `planned_skills`。前端只读 `item_id`、`prompt` 和 `answer`。

## 7. Trace（评分项 2 的演示素材）

`GET /requests/{id}/trace` 中 `step = "decision"` 的条目：`skills_selected`、`item_generated`、`answer_scored`、`second_opinion`、`difficulty_adjusted`、`level_estimated`、`confidence_scored`、`progress_vs_baseline`（milestone）、`result_published` / `escalated_to_teacher`、`teacher_confirmed` / `teacher_corrected_level` / `teacher_requested_reassessment`。

## 8. 离线演示（`LLM_PROVIDER=fake`）

fake 脚本按回答长度给分（等级越高，需要的字数越多），所以结果是确定的：

| 演示 | 账号 | 操作 | 结果 |
|---|---|---|---|
| 高置信，直接发布 | ivy.lin@example.com | 开始测评，每题写 15 个词左右 | 4 题后等级稳定（B2），`confirmed`，交给 Consultant |
| 低置信，转教师 | 同上 | 长答案和 “no idea” 交替 | 6 题仍不稳定，`pending_review`；用 emily.walker@example.com 在 `/t4` 确认或修正等级 |
| 证据不足 | 同上 | 全部回答 “I don't know” | `insufficient_evidence`，教师可 `request_changes` 要求重测 |

注意：`main` 上的 Course Consultant 还没合并，测评以 `OK` 结束后，流水线下一步 `planning.generate_plan` 会返回 `agent_not_implemented`。Consultant 合并后这一步就能接上。

## 9. 真实 LLM（Gemini）注意事项

- **免费额度**：`gemini-2.5-flash` 的每日免费额度很小，一天的开发测试就能用完（429，提示几个小时后再试）。`gemini-flash-lite-latest` 额度大、速度快（每题约 2–3 秒），演示建议 `LLM_MODEL_DEFAULT` 和 `LLM_MODEL_FAST` 都用它，或者换付费 key。额度用完时 agent 不会卡住（见题库兜底），但题目会全部来自题库。
- Gemini 2.5 Flash 是“思考”模型，隐藏的思考 token 也计入 `max_tokens`。预算 ≤ 1024 时经常以 `stop=max_tokens` 结束、JSON 不完整，所以三个提示词都用 2048。
- 每答一题要 1–3 次调用（评分、可能的二次评分、出下一题），用 2.5 Flash 每题约 6–8 秒。评分走 `fast` 档：在 `.env` 里设 `LLM_MODEL_FAST=gemini-flash-lite-latest` 可以变快（`gemini-2.5-flash-lite` 已不对新用户开放，会返回 404）。
- 免费层有每分钟请求数限制，超出时返回 429。adapter 会退避重试 2 次；仍失败时出题改用内置题库，评分记为未评分，最后转教师（`insufficient_evidence` 或 `low_confidence`）。演示前不要连续跑测试脚本。

### 实测记录（2026-10-20，模拟学习者：让 LLM 扮演指定水平的学习者作答）

| 模拟学习者 | 只用 rubric 分（v1） | rubric + 等级两个角度（v2） | 置信度 | 每题耗时 |
|---|---|---|---|---|
| A2 | — | A2 | 0.74，发布 | 3–5 s |
| B1 | C1（高两级） | A2（低一级） | 0.82，发布 | ~4 s |
| C1 | C2（高一级） | B2（低一级） | 0.85，发布 | 3–4 s |
| 时好时坏 | C2，置信度 0.43，转教师 | — | — | — |

v2 用 `gemini-flash-lite-latest` 出题和评分。模拟学习者本身不是准确基准，后续应该用真实学习者的作答样本校准；目前的误差在一级以内，而且偏保守（计划略容易，教师可以修正）。

## 10. 与 Stage 1 的差异（写报告用）

| 差异 | 理由 |
|---|---|
| 听、说、发音用书面代理测评 | 前端测评页只有文本框；多模态（TTS/STT）是 SCRUM-26 的 stretch |
| 题数上限 6、至少 4 题 | 前端显示 “Question n of max_items”，需要一开始就固定上限 |
| 等级由规则计算，LLM 只写叙述 | 避免 LLM 臆造等级；置信度可解释 |
| `request_changes` 让请求以 FAILED 结束 | 流水线下一步是生成计划，只有失败才能阻止被驳回的结果进入计划（C1） |
| UC02 3a 出题失败不结束用例，改用内置题库 | 免费层限流很常见；让学习者白答一半再失败，体验更差。题库题目在 trace 和 `prompt_id` 里可区分 |
