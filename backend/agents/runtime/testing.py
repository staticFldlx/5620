"""Helpers for agent unit tests: a runtime backed by a scripted FakeAdapter, no database."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from infrastructure.llm.base import LLMResponse
from infrastructure.llm.fake_adapter import FakeAdapter, tool_call

from .base import RequestContext, TaskInput
from .runtime import AgentRuntime, RuntimeConfig


def make_runtime(script: Iterable[Any] = (), *, threshold: float = 0.70, capabilities: Iterable[str] | None = None, default: Any = None) -> AgentRuntime:
    adapter = FakeAdapter(script, default=default, capabilities=capabilities)
    return AgentRuntime(adapter, RuntimeConfig(confidence_threshold=threshold, models={"fast": "fake-fast", "default": "fake"}))


def make_task(task_type: str, payload: dict | None = None, *, student_id: str | None = "student-1", actor_role: str = "student") -> TaskInput:
    return TaskInput(
        task_id="task-1",
        task_type=task_type,
        student_id=student_id,
        payload=payload or {},
        ctx=RequestContext(request_id="request-1", actor_id=student_id or "system", actor_role=actor_role),
    )


__all__ = ["make_runtime", "make_task", "tool_call", "LLMResponse", "FakeAdapter"]
