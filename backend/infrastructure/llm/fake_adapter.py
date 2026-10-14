"""Scripted adapter for tests and offline demos: CI never calls a real LLM."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any, ClassVar

from .base import LLMAdapter, LLMError, LLMResponse, Message, ToolCall, ToolSchema

Step = LLMResponse | str | dict | Callable[..., LLMResponse]


class FakeAdapter(LLMAdapter):
    """Returns scripted responses in order.

    A script step may be an LLMResponse, plain text, a dict (returned as JSON text),
    or a callable receiving the call kwargs. When the script runs out, `default` is used;
    without a default, LLMError is raised so tests notice unexpected calls.
    """

    capabilities: ClassVar[frozenset[str]] = frozenset({"tools", "json_schema"})

    def __init__(self, script: Iterable[Step] = (), *, default: Step | None = None, capabilities: Iterable[str] | None = None):
        self.script = list(script)
        self.default = default
        self.calls: list[dict[str, Any]] = []
        if capabilities is not None:
            self.capabilities = frozenset(capabilities)

    def complete(self, system, messages, *, model, tools=None, json_schema=None, max_tokens, timeout_s) -> LLMResponse:
        call = {"system": system, "messages": list(messages), "model": model, "tools": tools, "json_schema": json_schema}
        self.calls.append(call)
        if self.script:
            step = self.script.pop(0)
        elif self.default is not None:
            step = self.default
        else:
            raise LLMError("FakeAdapter script exhausted")
        return self._to_response(step, call)

    @staticmethod
    def _to_response(step: Step, call: dict) -> LLMResponse:
        if callable(step):
            step = step(**call)
        if isinstance(step, LLMResponse):
            return step
        if isinstance(step, dict):
            return LLMResponse(text=json.dumps(step), usage={"input_tokens": 0, "output_tokens": 0}, model="fake")
        return LLMResponse(text=str(step), usage={"input_tokens": 0, "output_tokens": 0}, model="fake")


def tool_call(name: str, args: dict | None = None, call_id: str | None = None) -> LLMResponse:
    """Script step: the model asks for one tool."""
    return LLMResponse(text="", tool_calls=[ToolCall(id=call_id or f"call_{name}", name=name, args=args or {})], stop="tool_calls", model="fake")


__all__ = ["FakeAdapter", "tool_call", "Message", "ToolSchema"]
