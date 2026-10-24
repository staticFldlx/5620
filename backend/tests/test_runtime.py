"""Agent runtime unit tests: FakeAdapter only, no database (spec 8.9)."""

import json

import pydantic
import pytest

from agents.runtime import LoopSpec, Message, ToolSpec
from agents.runtime.testing import make_runtime, tool_call
from infrastructure.llm import LLMError, LLMResponse
from infrastructure.llm.school_adapter import SchoolAdapter


class Level(pydantic.BaseModel):
    level: str
    confidence: float


class Query(pydantic.BaseModel):
    skill: str


def courses_tool(calls: list | None = None) -> ToolSpec:
    def find(skill: str) -> dict:
        if calls is not None:
            calls.append(skill)
        return {"courses": [f"{skill} 101"]}

    return ToolSpec(name="query_courses", description="Find courses by skill", input_model=Query, fn=find, kind="db")


def user(text: str) -> list[Message]:
    return [Message(role="user", content=text)]


def test_execute_prompt_records_trace_and_uses_tier_model():
    runtime = make_runtime(["hello"])
    response = runtime.execute_prompt("sys", user("hi"), tier="fast")
    assert response.text == "hello"
    assert runtime.adapter.calls[0]["model"] == "fake-fast"
    assert runtime.trace[0]["step"] == "llm" and runtime.trace[0]["tier"] == "fast"


def test_execute_prompt_turns_provider_errors_into_stop_error():
    def boom(**_):
        raise LLMError("down")

    runtime = make_runtime([boom])
    assert runtime.execute_prompt("sys", user("hi")).stop == "error"
    assert runtime.trace[-1]["error"] == "down"


def test_structured_validates_and_retries_once_with_the_error():
    runtime = make_runtime(['{"level": "B2"}', '```json\n{"level": "B2", "confidence": 0.8}\n```'])
    result = runtime.structured("sys", user("assess"), Level)
    assert result == Level(level="B2", confidence=0.8)
    retry_messages = runtime.adapter.calls[1]["messages"]
    assert "invalid" in retry_messages[-1].content


def test_structured_returns_none_after_two_invalid_replies():
    runtime = make_runtime(["not json", "still not json"])
    assert runtime.structured("sys", user("assess"), Level) is None


def test_structured_degrades_to_prompted_json_without_native_support():
    runtime = make_runtime(['{"level": "C1", "confidence": 0.9}'], capabilities=[])
    assert runtime.structured("sys", user("assess"), Level).level == "C1"
    call = runtime.adapter.calls[0]
    assert call["json_schema"] is None and "JSON schema" in call["system"]


def test_call_tool_returns_errors_as_data():
    runtime = make_runtime()

    def broken(skill: str) -> dict:
        raise RuntimeError("db offline")

    runtime.tools.register(ToolSpec(name="broken", description="x", input_model=Query, fn=broken, kind="db"))
    assert runtime.call_tool("broken", {"skill": "SQL"}) == {"error": "RuntimeError: db offline"}
    assert "invalid arguments" in runtime.call_tool("broken", {})["error"]
    assert runtime.call_tool("missing", {})["error"] == "unknown tool: missing"


def test_tool_loop_runs_tools_dedupes_repeats_and_ends():
    calls: list = []
    runtime = make_runtime([tool_call("query_courses", {"skill": "SQL"}), tool_call("query_courses", {"skill": "SQL"}), "plan ready"])
    result = runtime.run_tool_loop(LoopSpec(system="plan", tools=(courses_tool(calls),)), user("data analyst"))
    assert result.stopped == "end" and result.final_text == "plan ready"
    assert calls == ["SQL"]  # the identical second call was not executed again
    assert len(result.tool_results) == 1


def test_tool_loop_stops_at_max_steps():
    runtime = make_runtime(default=tool_call("query_courses", {"skill": "SQL"}))
    result = runtime.run_tool_loop(LoopSpec(system="plan", tools=(courses_tool(),), max_steps=3), user("x"))
    assert result.stopped == "max_steps"
    assert len(runtime.adapter.calls) == 3


def test_tool_loop_degraded_mode_parses_json_tool_requests():
    script = ['{"tool": "query_courses", "args": {"skill": "Writing"}}', '{"final": "done"}']
    runtime = make_runtime(script, capabilities=[])
    result = runtime.run_tool_loop(LoopSpec(system="plan", tools=(courses_tool(),)), user("x"))
    assert result.final_text == "done"
    assert result.tool_results[0]["result"] == {"courses": ["Writing 101"]}
    assert runtime.adapter.calls[0]["tools"] is None


def test_confidence_and_single_threshold():
    runtime = make_runtime(threshold=0.7)
    assert runtime.calculate_confidence({"retrieval": 0.5, "answer": 1.0}, {"retrieval": 3}) == 0.625
    assert runtime.is_low_confidence(0.69) and not runtime.is_low_confidence(0.7)
    assert not runtime.is_low_confidence(None)
    with pytest.raises(ValueError):
        runtime.calculate_confidence({})


def test_tool_names_must_be_snake_case():
    with pytest.raises(ValueError):
        ToolSpec(name="QueryCourses", description="x", input_model=Query, fn=lambda **_: {}, kind="db")


def test_school_adapter_maps_openai_compatible_payloads(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self, data):
            self.data = data

        def read(self):
            return json.dumps(self.data).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["auth"] = request.headers["Authorization"]
        return FakeResponse(
            {
                "model": "school-model",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {"content": None, "tool_calls": [{"id": "c1", "function": {"name": "query_courses", "arguments": '{"skill": "SQL"}'}}]},
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = SchoolAdapter("https://llm.example.edu/v1/", "secret")
    response = adapter.complete("sys", user("hi"), model="m", tools=[courses_tool().schema()], max_tokens=50, timeout_s=5)
    assert captured["auth"] == "Bearer secret"
    assert captured["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert captured["body"]["max_tokens"] == 50
    assert captured["body"]["tools"][0]["function"]["name"] == "query_courses"
    assert response.stop == "tool_calls" and response.tool_calls[0].args == {"skill": "SQL"}
    assert response.usage == {"input_tokens": 12, "output_tokens": 3}


def test_official_openai_uses_max_completion_tokens(monkeypatch):
    captured = {}

    class FakeResponse:
        def read(self):
            return b'{"choices":[{"finish_reason":"stop","message":{"content":"hello"}}]}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    response = SchoolAdapter("https://api.openai.com/v1", "secret").complete(
        "sys", user("hi"), model="gpt-5.4-mini", max_tokens=50, timeout_s=5
    )
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["body"]["max_completion_tokens"] == 50
    assert "max_tokens" not in captured["body"]
    assert response.text == "hello"


def test_school_adapter_retries_then_fails(monkeypatch):
    import urllib.error

    attempts = []

    def failing(request, timeout):
        attempts.append(1)
        raise urllib.error.URLError("timeout")

    monkeypatch.setattr("urllib.request.urlopen", failing)
    monkeypatch.setattr("time.sleep", lambda _: None)
    with pytest.raises(LLMError):
        SchoolAdapter("https://x", "k").complete("s", [], model="m", max_tokens=5, timeout_s=1)
    assert len(attempts) == 3  # first try + 2 retries


def test_fake_adapter_without_script_raises():
    runtime = make_runtime()
    assert runtime.execute_prompt("s", user("x")).stop == "error"
    assert isinstance(LLMResponse(text=""), LLMResponse)


def test_tool_loop_stops_when_time_budget_is_used(monkeypatch):
    ticks = iter([0.0, 0.5, 2.0])  # loop start, before call 1, before call 2
    monkeypatch.setattr("agents.runtime.loop._clock", lambda: next(ticks))
    runtime = make_runtime(default=tool_call("query_courses", {"skill": "SQL"}))
    result = runtime.run_tool_loop(LoopSpec(system="plan", tools=(courses_tool(),), max_steps=5, time_budget_s=1.0), user("x"))
    assert result.stopped == "time_budget"
    assert len(runtime.adapter.calls) == 1 and len(result.tool_results) == 1
    assert runtime.trace[-1] == {"step": "decision", "decision": "time_budget_reached", "budget_s": 1.0, "steps": 1}


def _http_429(headers=None, body=b""):
    import email.message
    import io
    import urllib.error

    message = email.message.Message()
    for name, value in (headers or {}).items():
        message[name] = value
    return urllib.error.HTTPError("https://x/v1/chat/completions", 429, "Too Many Requests", message, io.BytesIO(body))


def test_school_adapter_fails_fast_on_a_long_quota_wait(monkeypatch):
    attempts, sleeps = [], []
    body = b'[{"error": {"code": 429, "details": [{"retryDelay": "69824s"}]}}]'

    def quota(request, timeout):
        attempts.append(1)
        raise _http_429(body=body)

    monkeypatch.setattr("urllib.request.urlopen", quota)
    monkeypatch.setattr("time.sleep", sleeps.append)
    with pytest.raises(LLMError, match="quota"):
        SchoolAdapter("https://x", "k").complete("s", [], model="m", max_tokens=5, timeout_s=1)
    assert len(attempts) == 1 and sleeps == []


def test_school_adapter_waits_out_a_short_rate_limit(monkeypatch):
    responses = iter([_http_429(headers={"Retry-After": "1"}), None])
    sleeps = []

    class Ok:
        def read(self):
            return json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "hi"}}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def flaky(request, timeout):
        error = next(responses)
        if error is not None:
            raise error
        return Ok()

    monkeypatch.setattr("urllib.request.urlopen", flaky)
    monkeypatch.setattr("time.sleep", sleeps.append)
    assert SchoolAdapter("https://x", "k").complete("s", [], model="m", max_tokens=5, timeout_s=1).text == "hi"
    assert sleeps == [1.0]
