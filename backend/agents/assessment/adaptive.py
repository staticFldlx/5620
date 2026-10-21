"""Adaptive assessment rules (UC02 steps 3-5, F2.7). Pure Python, no Django, so they are unit-tested directly.

Difficulty is a CEFR index (A1=0 ... C2=5). After each scored answer:
  * a staircase moves the next item's level up (score >= STEP_UP) or down (score < STEP_DOWN);
  * the answer gives an ability estimate = item level + 2 * (score - 0.5): a score of 0.5 means
    "exactly this level", a full score is evidence for the next level up.
The assessment stops when the last STABLE_WINDOW estimates are close together (level estimate is
stable) after MIN_ITEMS, or when MAX_ITEMS is reached (UC02 step 5). Reaching the limit while the
estimate is still moving gives low stability, so the result goes to a teacher.

Confidence (NFR-02) is not the model's self-report. It combines three signals we can explain:
  stability    how close the last estimates are
  consistency  agreement between the holistic score and the rubric points met for the same answer,
               and between the two scores when a borderline answer is scored twice
  coverage     how many items and planned skills the evidence covers
The threshold itself is the shared AGENT_CONFIDENCE_THRESHOLD; this module never defines one.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
DEFAULT_LEVEL = "B1"

# Skills that can be measured with a typed answer (the student page only has a text box).
TEXT_SKILLS = ("Reading", "Writing", "Grammar", "Vocabulary")
# Stage 1 skills (F2.7) that need audio; in text mode they are measured through a written proxy.
WRITTEN_PROXY = {"Speaking": "Writing", "Pronunciation": "Vocabulary", "Listening": "Reading"}
MIN_PLANNED_SKILLS = 3

MAX_ITEMS = 6
MIN_ITEMS = 4
STEP_UP = 0.75
STEP_DOWN = 0.4
STABLE_WINDOW = 3
STABLE_SPREAD = 0.75  # ability-estimate spread (in CEFR steps) still counted as stable
PLACEMENT_TOLERANCE = 0.25  # an estimate a quarter level below L still places at L
SECOND_OPINION_BAND = 0.08  # scores within this distance of STEP_UP / STEP_DOWN are scored twice
LEVEL_SCORE_STEP = 0.35  # score change per CEFR level between the answer's level and the item's level
UNSTABLE_SPREAD = 1.25  # spread at which stability reaches 0: the learner cannot be placed within one level

# Stability weighs most: it is the evidence that the level estimate has settled (UC02 step 5).
CONFIDENCE_WEIGHTS = {"stability": 0.5, "consistency": 0.25, "coverage": 0.25}

_LEVEL = re.compile(r"\b([ABC][12])\b", re.I)


def parse_level(text: str | None, default: str | None = DEFAULT_LEVEL) -> str | None:
    """First CEFR level in free text ("B1–B2" -> "B1", "c1" -> "C1")."""
    match = _LEVEL.search(text or "")
    return match.group(1).upper() if match else default


def level_index(level: str | None) -> int:
    return LEVELS.index(parse_level(level))


def level_name(index: float) -> str:
    return LEVELS[min(max(int(round(index)), 0), len(LEVELS) - 1)]


def plan_skills(focus_skills: Sequence[str], focus_text: str = "") -> tuple[list[str], list[str]]:
    """F2.7 skill selection: the learner's focus skills first, mapped to text skills, padded to MIN_PLANNED_SKILLS.

    Returns (skills, proxied) where proxied lists the audio skills measured through a written proxy.
    """
    skills: list[str] = []
    proxied: list[str] = []
    wanted = [s.strip().title() for s in focus_skills if s and s.strip()]
    words = set(re.findall(r"[a-z]+", (focus_text or "").lower()))
    wanted += [s for s in (*TEXT_SKILLS, *WRITTEN_PROXY) if s.lower() in words]
    for skill in wanted:
        if skill in WRITTEN_PROXY:
            proxied.append(skill)
            skill = WRITTEN_PROXY[skill]
        if skill in TEXT_SKILLS and skill not in skills:
            skills.append(skill)
    for skill in TEXT_SKILLS:
        if len(skills) >= MIN_PLANNED_SKILLS:
            break
        if skill not in skills:
            skills.append(skill)
    return skills, proxied


def skill_for(skills: Sequence[str], item_number: int) -> str:
    """Round-robin so every planned skill gets items (item_number starts at 1)."""
    return skills[(item_number - 1) % len(skills)]


def next_index(index: int, score: float) -> int:
    if score >= STEP_UP:
        index += 1
    elif score < STEP_DOWN:
        index -= 1
    return min(max(index, 0), len(LEVELS) - 1)


def estimate(index: int, score: float) -> float:
    return round(index + 2 * (score - 0.5), 3)


def is_stable(estimates: Sequence[float]) -> bool:
    window = list(estimates)[-STABLE_WINDOW:]
    # rounded: estimates have 3 decimals, and 1.1 - 0.35 is 0.7500000000000001 in floating point
    return len(window) == STABLE_WINDOW and round(max(window) - min(window), 3) <= STABLE_SPREAD


def stop_reason(estimates: Sequence[float], answered: int, max_items: int = MAX_ITEMS) -> str | None:
    """None while the assessment should continue; otherwise why it stops."""
    if answered >= max_items:
        return "item_limit_reached"
    if answered >= MIN_ITEMS and is_stable(estimates):
        return "level_stable"
    return None


def final_level(estimates: Sequence[float], default: str = DEFAULT_LEVEL) -> str:
    """The highest level the learner reliably shows: floor of the mean of the last estimates, with
    PLACEMENT_TOLERANCE for scoring noise. Good at B1 but weak at B2 places at B1, not B2.
    With no scored answer at all, the start level is kept (the result then goes to a teacher)."""
    window = list(estimates)[-STABLE_WINDOW:] or [float(level_index(default))]
    return level_name(math.floor(sum(window) / len(window) + PLACEMENT_TOLERANCE))


def needs_second_opinion(score: float) -> bool:
    """A score this close to a staircase threshold decides the next level, so it is scored twice."""
    return abs(score - STEP_UP) < SECOND_OPINION_BAND or abs(score - STEP_DOWN) < SECOND_OPINION_BAND


def confidence_signals(estimates: Sequence[float], consistency: Sequence[float], *, answered: int, max_items: int, skills_covered: int, skills_planned: int) -> dict[str, float]:
    window = list(estimates)[-STABLE_WINDOW:]
    if len(window) < 2:
        stability = 0.0
    else:
        stability = max(0.0, 1.0 - (max(window) - min(window)) / UNSTABLE_SPREAD)
    agreement = sum(consistency) / len(consistency) if consistency else 0.0
    coverage = 0.5 * min(answered / max_items, 1.0) + 0.5 * min(skills_covered / max(skills_planned, 1), 1.0)
    return {"stability": round(stability, 3), "consistency": round(agreement, 3), "coverage": round(coverage, 3)}


def level_score(item_level: str, demonstrated_level: str | None) -> float | None:
    """The scorer's CEFR judgement as a score on the same scale: same level 0.5, one level above 0.85, one below 0.15."""
    shown = parse_level(demonstrated_level, default=None)
    if shown is None:
        return None
    return round(min(max(0.5 + LEVEL_SCORE_STEP * (LEVELS.index(shown) - level_index(item_level)), 0.0), 1.0), 3)


def combine(item_level: str, rubric: float, demonstrated_level: str | None, met: int, expected: int, off_task: bool) -> tuple[float, float]:
    """Two views of one answer: the rubric score and the CEFR level the language shows. Their mean is the score;
    disagreement between them, or with the rubric points met, lowers the consistency (agreement) value."""
    if off_task:
        return 0.0, 1.0
    rubric = round(rubric, 3)
    agreement = points_agreement(rubric, met, expected)
    by_level = level_score(item_level, demonstrated_level)
    if by_level is None:
        return rubric, agreement
    return round((rubric + by_level) / 2, 3), round(min(agreement, 1.0 - abs(rubric - by_level)), 3)


def points_agreement(score: float, met: int, expected: int) -> float:
    """1 when the holistic score matches the share of rubric points met, 0 when they are opposite."""
    if expected <= 0:
        return 0.5  # no rubric to check against: neutral evidence
    return round(1.0 - abs(score - met / expected), 3)
