"""Capability probe behind `manage.py check_llm`.

Runs three small calls against an adapter that claims every capability, so the endpoint's
real support is measured: plain text, JSON-schema structured output, and tool calling.
The passing capabilities are what LLM_CAPABILITIES should contain.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from .base import LLMAdapter, LLMError, Message, ToolSchema

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "confidence": {"type": "number"}},
    "required": ["answer", "confidence"],
}
TIME_TOOL = ToolSchema(
    name="get_local_time",
    description="Returns the current local time for a city.",
    input_schema={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)


@dataclass(frozen=True)
class Probe:
    name: str
    capability: str | None  # the LLM_CAPABILITIES entry this check decides, if any
    ok: bool
    detail: str
    latency_ms: int


def _call(adapter: LLMAdapter, *, model: str, timeout_s: float, **kwargs):
    started = time.monotonic()
    try:
        response = adapter.complete(model=model, timeout_s=timeout_s, max_tokens=200, **kwargs)
        return response, None, int((time.monotonic() - started) * 1000)
    except (LLMError, OSError, ValueError) as exc:
        return None, str(exc)[:300], int((time.monotonic() - started) * 1000)


def probe(adapter: LLMAdapter, *, model: str, timeout_s: float) -> list[Probe]:
    results = []

    response, error, ms = _call(
        adapter, model=model, timeout_s=timeout_s, system="Reply with one short sentence.", messages=[Message(role="user", content="Say hello.")]
    )
    ok = response is not None and response.stop == "end" and bool(response.text.strip())
    results.append(Probe("text", None, ok, error or (response.text.strip()[:80] if ok else f"stop={response.stop}"), ms))

    response, error, ms = _call(
        adapter,
        model=model,
        timeout_s=timeout_s,
        system="Answer in JSON.",
        messages=[Message(role="user", content="What is 2 + 2? Give the answer and your confidence between 0 and 1.")],
        json_schema=ANSWER_SCHEMA,
    )
    detail = error or ""
    ok = False
    if response is not None:
        try:
            data = json.loads(response.text)
            ok = isinstance(data, dict) and {"answer", "confidence"} <= set(data)
            detail = response.text.strip()[:80] if ok else f"missing keys in {response.text[:80]!r}"
        except json.JSONDecodeError:
            detail = f"not JSON: {response.text[:80]!r}"
    results.append(Probe("json_schema", "json_schema", ok, detail, ms))

    response, error, ms = _call(
        adapter,
        model=model,
        timeout_s=timeout_s,
        system="Use the provided tool when it helps.",
        messages=[Message(role="user", content="What time is it in Sydney right now? Use the tool.")],
        tools=[TIME_TOOL],
    )
    calls = response.tool_calls if response is not None else []
    ok = any(call.name == TIME_TOOL.name for call in calls)
    detail = error or (f"called {calls[0].name}({calls[0].args})" if ok else f"no tool call (stop={response.stop})")
    results.append(Probe("tools", "tools", ok, detail, ms))
    return results


def suggested_capabilities(results: list[Probe]) -> str:
    return ",".join(p.capability for p in results if p.capability and p.ok)
