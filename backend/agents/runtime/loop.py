"""Generic ReAct-style tool loop (spec 4.4). Identical behaviour for every agent."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from infrastructure.llm.base import Message, ToolCall

from .tools import ToolSpec

if TYPE_CHECKING:
    from .runtime import AgentRuntime


@dataclass(frozen=True)
class LoopSpec:
    system: str
    tools: tuple[ToolSpec, ...]
    max_steps: int = 6
    tier: str = "default"
    max_tokens: int = 1024
    time_budget_s: float | None = None  # stop before the next model call once this many seconds have passed


@dataclass
class LoopResult:
    final_text: str
    stopped: Literal["end", "max_steps", "time_budget", "error"]
    messages: list[Message]
    tool_results: list[dict[str, Any]] = field(default_factory=list)  # [{name, args, result}]


DEGRADED_TOOL_PROMPT = (
    "\n\nYou can use these tools. To call one, reply with only a JSON object "
    '{{"tool": "<name>", "args": {{...}}}}. When you are done, reply with only '
    '{{"final": "<answer>"}}.\nTools:\n{tools}'
)


_clock = time.monotonic  # replaced in tests


def _call_key(call: ToolCall) -> str:
    return call.name + ":" + json.dumps(call.args, sort_keys=True, default=str)


def parse_json_object(text: str) -> dict | None:
    """Extract the first JSON object from model text (handles ```json fences)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    try:
        value = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def run_tool_loop(runtime: "AgentRuntime", spec: LoopSpec, messages: list[Message]) -> LoopResult:
    for tool in spec.tools:
        runtime.tools.register(tool)
    native = "tools" in runtime.adapter.capabilities
    system = spec.system
    if not native:
        listing = "\n".join(f"- {t.name}: {t.description} input schema {json.dumps(t.input_model.model_json_schema())}" for t in spec.tools)
        system += DEGRADED_TOOL_PROMPT.format(tools=listing)
    history = list(messages)
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    started = _clock()
    for _ in range(spec.max_steps):
        if spec.time_budget_s is not None and _clock() - started >= spec.time_budget_s:
            runtime.note("time_budget_reached", budget_s=spec.time_budget_s, steps=len(results))
            return LoopResult("", "time_budget", history, results)
        response = runtime.execute_prompt(system, history, tier=spec.tier, tools=list(spec.tools) if native else None, max_tokens=spec.max_tokens)
        if response.stop in ("error", "refused", "max_tokens"):
            return LoopResult(response.text, "error", history, results)
        calls = list(response.tool_calls)
        final_text = response.text
        if not native:
            parsed = parse_json_object(response.text) or {}
            if "tool" in parsed:
                calls = [ToolCall(id=f"degraded_{len(results)}", name=str(parsed["tool"]), args=dict(parsed.get("args") or {}))]
            else:
                final_text = str(parsed.get("final", response.text))
        if not calls:
            return LoopResult(final_text, "end", history, results)
        history.append(Message(role="assistant", content=response.text, tool_calls=tuple(calls)))
        for call in calls:
            key = _call_key(call)
            if key in seen:
                result: dict[str, Any] = {"note": "already called with the same arguments; reuse the earlier result"}
            else:
                seen.add(key)
                result = runtime.call_tool(call.name, call.args)
                results.append({"name": call.name, "args": call.args, "result": result})
            content = json.dumps(result, default=str)
            if native:
                history.append(Message(role="tool", content=content, tool_call_id=call.id))
            else:
                history.append(Message(role="user", content=f"Tool {call.name} returned: {content}"))
    return LoopResult("", "max_steps", history, results)
