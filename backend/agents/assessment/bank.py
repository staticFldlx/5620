"""Built-in item bank: the fake script's items, and the fallback when the model cannot produce an item.

With the bank the assessment never stops halfway because the LLM is rate-limited or down: the
learner gets a bank item at the same skill and level (trace: item_bank_fallback). Three items per
skill, one per CEFR band (A, B, C).
"""

from __future__ import annotations

from . import adaptive

PROMPT_ID = "assessment.item_bank.v1"

BANK: dict[str, list[tuple[str, list[str]]]] = {
    "Reading": [
        (
            "Read: \"Many cities now close their centres to cars on Sundays. Shops first worried about losing customers, "
            "but most report more visitors on foot.\" What was the shops' first concern, and what actually happened?",
            ["Names the concern about losing customers", "States that visitors on foot increased", "Uses own words"],
        ),
        (
            "Read: \"Remote work saves commuting time, yet some employees say they feel less connected to their team.\" "
            "Explain the trade-off the writer describes and give one example of your own.",
            ["Identifies the trade-off", "Mentions feeling less connected", "Gives a relevant own example"],
        ),
        (
            "Read: \"Although the study was small, its findings challenge the assumption that bilingual children learn to read later.\" "
            "What assumption is challenged, and why should the reader be careful with the result?",
            ["States the assumption about bilingual children", "Notes the small study size", "Explains the need for caution"],
        ),
    ],
    "Writing": [
        (
            "Write 3-4 sentences to a colleague asking to move tomorrow's meeting to Friday. Give a reason and suggest a time.",
            ["Clear request to move the meeting", "Gives a reason", "Suggests a time", "Polite tone"],
        ),
        (
            "Write a short paragraph (4-5 sentences) arguing whether students should learn a second language at school. "
            "State your claim and support it with one piece of evidence.",
            ["States a clear claim", "Supports it with evidence", "Explains how the evidence supports the claim"],
        ),
        (
            "Write a short paragraph that presents one counter-argument to your own view on online exams and then responds to it.",
            ["Presents a counter-argument fairly", "Responds to it", "Uses linking words"],
        ),
    ],
    "Grammar": [
        (
            "Correct the mistakes and rewrite the sentences: \"Yesterday I go to the market and buyed some apple. It were very cheap.\"",
            ["Uses past tense went/bought", "Plural apples", "Was instead of were"],
        ),
        (
            "Combine into one sentence using a relative clause: \"The report was late. My manager wrote the report.\" "
            "Then write one sentence of your own with 'which'.",
            ["Correct relative clause", "Own sentence uses which correctly"],
        ),
        (
            "Rewrite in the passive and explain when the passive is a better choice: \"The committee will announce the results next week.\"",
            ["Correct future passive", "Explains focus on the action or result"],
        ),
    ],
    "Vocabulary": [
        (
            "Use each of these words in a sentence about your daily life: 'schedule', 'deadline', 'improve'.",
            ["Uses schedule correctly", "Uses deadline correctly", "Uses improve correctly"],
        ),
        (
            "Explain the difference between 'affect' and 'effect' and write one example sentence for each.",
            ["Explains affect as a verb", "Explains effect as a noun", "Two correct example sentences"],
        ),
        (
            "Replace the informal words in this sentence with academic ones and explain your choices: \"Lots of people think this idea is really bad.\"",
            ["Uses many or numerous", "Uses argue or consider", "Uses a precise evaluative word"],
        ),
    ],
}


def item(skill: str, level: str, number: int, planned: int) -> dict:
    """{prompt, expected_points} for this skill and level; a skill's second item uses the next prompt."""
    options = BANK[skill]
    band = min(adaptive.level_index(level) // 2, len(options) - 1)  # A -> 0, B -> 1, C -> 2
    repeat = (number - 1) // max(planned, 1)
    prompt, points = options[(band + repeat) % len(options)]
    return {"prompt": f"[{level} {skill}] {prompt}", "expected_points": list(points)}
