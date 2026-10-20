"""Built-in item bank: the fake script's items, and the fallback when the model cannot produce an item.

With the bank the assessment never stops halfway because the LLM is rate-limited or down: the
learner gets a bank item at the same skill and level (trace: item_bank_fallback). Two items per
skill and CEFR band (A, B, C); a skill's later items rotate within the band, never into an easier one.
"""

from __future__ import annotations

from . import adaptive

PROMPT_ID = "assessment.item_bank.v1"

Item = tuple[str, list[str]]

BANK: dict[str, dict[str, list[Item]]] = {
    "Reading": {
        "A": [
            (
                "Read: \"The library is open from 9 am to 5 pm. It is closed on Sundays. You can borrow three books for two weeks.\" "
                "When can you not visit the library, and how many books can you borrow?",
                ["Says it is closed on Sundays", "Says three books", "Answers in a full sentence"],
            ),
            (
                "Read: \"Tom takes the bus to work because his car is broken. The bus is slow, so he leaves home at 7 am.\" "
                "Why does Tom take the bus, and why does he leave early?",
                ["Car is broken", "The bus is slow", "Connects the two reasons"],
            ),
        ],
        "B": [
            (
                "Read: \"Remote work saves commuting time, yet some employees say they feel less connected to their team.\" "
                "Explain the trade-off the writer describes and give one example of your own.",
                ["Identifies the trade-off", "Mentions feeling less connected", "Gives a relevant own example"],
            ),
            (
                "Read: \"Many cities now close their centres to cars on Sundays. Shops first worried about losing customers, "
                "but most report more visitors on foot.\" What was the shops' first concern, what actually happened, and what does this suggest?",
                ["Names the concern about losing customers", "States that visitors on foot increased", "Draws a reasonable conclusion"],
            ),
        ],
        "C": [
            (
                "Read: \"Although the study was small, its findings challenge the assumption that bilingual children learn to read later.\" "
                "What assumption is challenged, and why should the reader treat the result with caution?",
                ["States the assumption about bilingual children", "Notes the small study size", "Explains why caution is needed"],
            ),
            (
                "Read: \"Proponents frame the levy as a public-health measure; critics counter that it is regressive, falling hardest on "
                "low-income households.\" Paraphrase both positions and explain what 'regressive' means here.",
                ["Paraphrases the public-health position", "Paraphrases the critics' position", "Explains regressive correctly"],
            ),
        ],
    },
    "Writing": {
        "A": [
            (
                "Write 2-3 sentences to a friend inviting them to your birthday party. Say the day and the place.",
                ["Clear invitation", "Gives the day", "Gives the place"],
            ),
            (
                "Write 2-3 sentences describing your favourite place in your city and why you like it.",
                ["Names the place", "Gives a reason", "Connected sentences"],
            ),
        ],
        "B": [
            (
                "Write 3-4 sentences to a colleague asking to move tomorrow's meeting to Friday. Give a reason and suggest a time.",
                ["Clear request to move the meeting", "Gives a reason", "Suggests a time", "Polite tone"],
            ),
            (
                "Write a short paragraph (4-5 sentences) arguing whether students should learn a second language at school. "
                "State your claim and support it with one piece of evidence.",
                ["States a clear claim", "Supports it with evidence", "Explains how the evidence supports the claim"],
            ),
        ],
        "C": [
            (
                "Write a short paragraph that presents one counter-argument to your own view on online exams and then rebuts it.",
                ["Presents a counter-argument fairly", "Rebuts it convincingly", "Uses cohesive devices"],
            ),
            (
                "Write 4-5 sentences for a formal report recommending one change to your organisation's hiring process, "
                "acknowledging a possible drawback.",
                ["Makes a specific recommendation", "Acknowledges a drawback", "Formal register throughout"],
            ),
        ],
    },
    "Grammar": {
        "A": [
            (
                "Correct the mistakes and rewrite the sentences: \"Yesterday I go to the market and buyed some apple. It were very cheap.\"",
                ["Uses past tense went/bought", "Plural apples", "Was or they were instead of it were"],
            ),
            (
                "Write two sentences about your weekend: one about what you did last weekend and one about what you are going to do next weekend.",
                ["Correct past simple", "Correct going to future", "Two complete sentences"],
            ),
        ],
        "B": [
            (
                "Combine into one sentence using a relative clause: \"The report was late. My manager wrote the report.\" "
                "Then write one sentence of your own using 'which' to add extra information about a place.",
                ["Correct relative clause", "Own non-defining clause with which and commas"],
            ),
            (
                "Complete the sentence in two different ways, one real and one unreal condition: \"If I ... , I ... .\" "
                "Explain the difference in meaning.",
                ["Correct first conditional", "Correct second conditional", "Explains real vs unreal"],
            ),
        ],
        "C": [
            (
                "Rewrite in the passive and explain when the passive is the better choice: \"The committee will announce the results next week.\"",
                ["Correct future passive", "Explains focus on the action or result"],
            ),
            (
                "Rewrite using inversion for emphasis, then explain the effect: \"I have never seen such a well-organised event.\"",
                ["Correct inversion: Never have I seen", "Explains the emphatic or formal effect"],
            ),
        ],
    },
    "Vocabulary": {
        "A": [
            (
                "Use each of these words in a sentence about your daily life: 'breakfast', 'busy', 'weekend'.",
                ["Uses breakfast correctly", "Uses busy correctly", "Uses weekend correctly"],
            ),
            (
                "Write the opposite of each word and use one of them in a sentence: 'cheap', 'early', 'noisy'.",
                ["Expensive", "Late", "Quiet, with one sentence"],
            ),
        ],
        "B": [
            (
                "Use each of these words in a sentence about work or study: 'schedule', 'deadline', 'improve'.",
                ["Uses schedule correctly", "Uses deadline correctly", "Uses improve correctly"],
            ),
            (
                "Explain the difference between 'affect' and 'effect' and write one example sentence for each.",
                ["Explains affect as a verb", "Explains effect as a noun", "Two correct example sentences"],
            ),
        ],
        "C": [
            (
                "Replace the informal words with academic ones and explain your choices: \"Lots of people think this idea is really bad.\"",
                ["Uses many or numerous", "Uses argue or consider", "Uses a precise evaluative word"],
            ),
            (
                "Explain the nuance between 'imply' and 'infer', then use 'mitigate' and 'exacerbate' in one sentence about a policy.",
                ["Distinguishes imply and infer correctly", "Uses mitigate correctly", "Uses exacerbate correctly"],
            ),
        ],
    },
}


def item(skill: str, level: str, number: int, planned: int) -> dict:
    """{prompt, expected_points} at this skill and level; repeat visits to a skill rotate within the CEFR band."""
    band = "ABC"[min(adaptive.level_index(level) // 2, 2)]
    options = BANK[skill][band]
    repeat = (number - 1) // max(planned, 1)
    prompt, points = options[repeat % len(options)]
    return {"prompt": prompt, "expected_points": list(points)}
