"""Offline-only scripted model response, selected by the shared fake-provider hook."""
import json


def script(task):
    def respond(**call):
        context = json.loads(call["messages"][0].content)
        courses = context["catalogue"]["courses"]
        stages, completed = [], set()
        remaining = list(courses)
        while remaining:
            ready = [c for c in remaining if set(c["prerequisites"]) <= completed]
            if not ready:
                break
            for course in ready:
                week = len(stages) * 2 + 1
                stages.append({"title": course["title"], "topics": [course["skill"] or course["title"]],
                    "milestone": "Demonstrate " + course["title"] + " through an assessed exercise.",
                    "start_week": week, "end_week": week + 1, "course_codes": [course["code"]]})
                completed.add(course["code"])
                remaining.remove(course)
        return {"weekly_hours": context["profile"]["weekly_hours"], "stages": stages,
            "rationale": "Offline demo: address " + context["assessment"]["gap"] + " towards " + context["profile"]["goal_summary"]}
    return [respond]
