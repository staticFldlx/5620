"""LLM provider selection and the check_llm capability probe (T1)."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from infrastructure.llm import FakeAdapter, LLMError, build_adapter
from infrastructure.llm.diagnostics import probe, suggested_capabilities
from infrastructure.llm.fake_adapter import tool_call
from infrastructure.llm.school_adapter import SchoolAdapter


@pytest.mark.parametrize("provider", ["openai", "school"])
def test_openai_compatible_providers_share_one_adapter(provider):
    adapter = build_adapter(provider, base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key="k", capabilities=["tools"])
    assert isinstance(adapter, SchoolAdapter)
    assert adapter.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert adapter.capabilities == frozenset({"tools"})


def test_fake_and_unknown_providers():
    assert isinstance(build_adapter("fake"), FakeAdapter)
    with pytest.raises(LLMError):
        build_adapter("gemini")
    with pytest.raises(LLMError):
        build_adapter("openai", base_url="")  # base URL is required


def test_probe_reports_every_capability():
    adapter = FakeAdapter(["Hello there.", '{"answer": "4", "confidence": 0.9}', tool_call("get_local_time", {"city": "Sydney"})])
    results = probe(adapter, model="m", timeout_s=5)
    assert [(r.name, r.ok) for r in results] == [("text", True), ("json_schema", True), ("tools", True)]
    assert suggested_capabilities(results) == "json_schema,tools"
    assert adapter.calls[1]["json_schema"]["required"] == ["answer", "confidence"]
    assert adapter.calls[2]["tools"][0].name == "get_local_time"


def test_probe_marks_unsupported_capabilities():
    def rejects_schema(**_):
        raise LLMError("LLM HTTP 400: response_format is not supported")

    adapter = FakeAdapter(["Hello.", rejects_schema, "It is 3 pm."])  # no tool call made
    results = probe(adapter, model="m", timeout_s=5)
    assert [r.ok for r in results] == [True, False, False]
    assert "400" in results[1].detail and "no tool call" in results[2].detail
    assert suggested_capabilities(results) == ""


def test_probe_rejects_non_json_structured_reply():
    results = probe(FakeAdapter(["Hi.", "The answer is 4", "x"]), model="m", timeout_s=5)
    assert not results[1].ok and results[1].detail.startswith("not JSON")


def test_check_llm_command(settings, monkeypatch, capsys):
    settings.LLM_PROVIDER = "fake"
    call_command("check_llm")
    assert "no endpoint to check" in capsys.readouterr().out

    settings.LLM_PROVIDER = "openai"
    settings.LLM_BASE_URL = ""
    with pytest.raises(CommandError, match="LLM_BASE_URL"):
        call_command("check_llm")

    settings.LLM_BASE_URL, settings.LLM_API_KEY, settings.LLM_MODEL_DEFAULT, settings.LLM_MODEL_FAST = "https://x/v1", "k", "flash", ""
    script = FakeAdapter(["Hello.", '{"answer": "4", "confidence": 1}', "no tools here"])
    monkeypatch.setattr("orchestration.task_queue.management.commands.check_llm.build_adapter", lambda *a, **kw: script)
    call_command("check_llm")
    out = capsys.readouterr().out
    assert "model=flash" in out and "LLM_CAPABILITIES=json_schema" in out

    dead = FakeAdapter([lambda **_: (_ for _ in ()).throw(LLMError("connection refused"))] + ["", ""])
    monkeypatch.setattr("orchestration.task_queue.management.commands.check_llm.build_adapter", lambda *a, **kw: dead)
    with pytest.raises(CommandError, match="VPN"):
        call_command("check_llm")
