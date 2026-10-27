
"""Offline scripted model replies (LLM_PROVIDER=fake), selected by the shared fake-provider hook."""

import json
import re

# Words in a Founder note -> agent id (first match wins).
AGENT_WORDS = (
    ("assistant", "teaching_support"),
    ("teaching", "teaching_support"),
    ("assessment", "assessment"),
    ("consultant", "planning"),
    ("planning", "planning"),
    ("coordinator", "coordinator"),
)


def script(task) -> list:
    if task.task_type == "tech_operations.apply_correction":
        return [_correction] * 2  # second reply covers the runtime's validation retry
    if task.task_type == "tech_operations.detect_anomalies":
        return [_diagnosis] * 20  # one diagnosis per new incident
    return []


def _content(call) -> str:
    return call["messages"][0].content


def _correction(**call) -> dict:
    note = re.sub(r"</?note>", "", _content(call)).strip()
    lower = note.lower()
    agent = next((agent_id for word, agent_id in AGENT_WORDS if word in lower), "")
    number = re.search(r"\b(\d{1,3})\b", note)

    if agent and number and "timeout" in lower:
        seconds = int(number.group(1))
        return {
            "kind": "timeout",
            "agent_id": agent,
            "new_value": seconds,
            "title": f"Set the {agent} LLM timeout to {seconds} s",
            "before": "The current timeout setting",
            "after": f"LLM calls may take up to {seconds} s",
            "validation": "Check the saved override and that new answers complete.",
            "rollback": "Restore the previous timeout through a rollback proposal.",
        }

    return {
        "kind": "manual",
        "agent_id": "",
        "new_value": 0,
        "title": f"Correction: {note[:80]}",
        "before": "The behaviour described in the Founder's note.",
        "after": note[:300] or "The requested correction.",
        "validation": "The Founder checks the result after the change is made.",
        "rollback": "Restore the previous state manually.",
    }


def _diagnosis(**call) -> dict:
    data = json.loads(_content(call))
    paused = [agent for agent, status in (data.get("agent_status") or {}).items() if status == "paused"]

    if not paused and any(e.get("summary") in ("llm_unavailable", "task_timeout", "provider_timeout", "transient_timeout") for e in data.get("evidence", [])):
        return {"probable_cause": "A task reported a transient provider failure.",
                "explanation": "The recorded failure code supports a controlled retry, subject to the execution policy.",
                "confidence": 0.85, "recommended_action": "retry_request", "risk_level": "low"}
    if paused:
        return {
            "probable_cause": f"{paused[0]} is paused, so each of its tasks fails with agent_paused.",
            "explanation": "The failure rate matches the period the agent has been paused.",
            "confidence": 0.85,
            "recommended_action": "resume_agent",
            "risk_level": "low",
        }

    return {
        "probable_cause": "Undetermined from the available evidence.",
        "explanation": "The metrics show the symptom but not its cause; further investigation is required.",
        "confidence": 0.5,
        "recommended_action": "request_founder_review",
        "risk_level": "unknown",
    }
