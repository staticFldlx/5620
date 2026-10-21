"""Offline-only scripted model response, selected by the shared fake-provider hook."""
import json
import re


def script(task):
    def respond(**call):
        context = json.loads(call["messages"][0].content)
        courses = {c["code"]: c for c in context["catalogue"]["courses"]}
        profile, assessment = context["profile"], context["assessment"]
        skills = {s.lower() for s in profile["focus_skills"] + assessment["weaknesses"]}
        goal_words = set(re.findall(r"[a-z]+", (profile["goal_summary"] + " " + profile["goal_text"]).lower()))
        goal_words -= {"english", "learning", "learn", "the", "and", "to", "a", "improve"}
        levels = ("A1", "A2", "B1", "B2", "C1", "C2")
        ceiling = profile.get("target_level") or assessment["level"]
        selected, ordered = set(), []

        def path(code, visiting):
            if code in selected:
                return []
            if code in visiting or code not in courses:
                raise ValueError("Missing or cyclic prerequisites")
            prerequisites = []
            for prerequisite in courses[code]["prerequisites"]:
                prerequisites.extend(path(prerequisite, visiting | {code}))
            return list(dict.fromkeys([*prerequisites, code]))

        for course in sorted(courses.values(), key=lambda c: c["code"]):
            words = set(re.findall(r"[a-z]+", course["title"].lower()))
            if course["skill"].lower() not in skills and not words.intersection(goal_words):
                continue
            if course["level"] in levels and ceiling in levels and levels.index(course["level"]) > levels.index(ceiling):
                continue
            try:
                additions = path(course["code"], set())
            except ValueError:
                continue
            if len(ordered) + len(additions) > 52:
                continue
            ordered.extend(additions)
            selected.update(additions)
        stages = []
        for code in ordered:
            course = courses[code]
            week = len(stages) * 2 + 1
            stages.append({"title": course["title"], "topics": [course["skill"] or course["title"]],
                "milestone": "Demonstrate " + course["title"] + " through an assessed exercise.",
                "start_week": week, "end_week": week + 1, "course_codes": [course["code"]]})
        return {"weekly_hours": context["profile"]["weekly_hours"], "stages": stages,
            "rationale": "Offline demo: address " + context["assessment"]["gap"] + " towards " + context["profile"]["goal_summary"]}
    # Empty/unsuitable catalogues deliberately fail draft validation; never fabricate
    # a successful plan. The second response supports the runtime's validation retry.
    return [respond, respond]
