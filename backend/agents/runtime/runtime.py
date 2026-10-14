"""AgentRuntime (spec 4.2, Fig 6c): the only place that calls the LLM.

Pure Python. It never imports Django or domain models, so agent unit tests run without a
database. Configuration is injected by the Orchestrator through RuntimeConfig.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, TypeVar

import pydantic

from infrastructure.llm.base import LLMAdapter, LLMError, LLMResponse, Message

from .confidence import weighted_confidence
from .loop import LoopResult, LoopSpec, parse_json_object, run_tool_loop
from .tools import ToolRegistry, ToolSpec

T = TypeVar("T", bound=pydantic.BaseModel)

STRUCTURED_SUFFIX = "\n\nReply with only one JSON object that matches this JSON schema:\n{schema}"


@dataclass(frozen=True)
class RuntimeConfig:
    confidence_threshold: float
    models: dict[str, str] = field(default_factory=dict)  # tier -> model name, e.g. {"fast": ..., "default": ...}
    timeout_s: float = 30.0
    embedding_model: str = ""


class AgentRuntime:
    def __init__(self, adapter: LLMAdapter, config: RuntimeConfig, *, tools: ToolRegistry | None = None):
        self.adapter = adapter
        self.config = config
        self.tools = tools or ToolRegistry()
        self.trace: list[dict[str, Any]] = []  # copied into AgentTask.trace by the Orchestrator

    # --- LLM calls ---------------------------------------------------------
    def execute_prompt(
        self,
        system: str,
        messages: list[Message],
        *,
        tier: str = "default",
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
        json_schema: dict | None = None,
    ) -> LLMResponse:
        """One LLM call (Fig 6c executePrompt). Provider errors become stop='error', never exceptions."""
        model = self.config.models.get(tier) or self.config.models.get("default", "")
        started = time.monotonic()
        try:
            response = self.adapter.complete(
                system,
                list(messages),
                model=model,
                tools=[t.schema() for t in tools] if tools else None,
                json_schema=json_schema,
                max_tokens=max_tokens,
                timeout_s=self.config.timeout_s,
            )
        except LLMError as exc:
            response = LLMResponse(text="", stop="error", model=model)
            self._record("llm", tier=tier, model=model, stop="error", error=str(exc), latency_ms=_ms(started))
            return response
        self._record(
            "llm",
            tier=tier,
            model=response.model or model,
            stop=response.stop,
            usage=response.usage,
            tool_calls=[c.name for c in response.tool_calls],
            latency_ms=_ms(started),
        )
        return response

    def structured(self, system: str, messages: list[Message], schema: type[T], *, tier: str = "default", max_tokens: int = 1024) -> T | None:
        """Validated pydantic output, or None after one retry with the validation error (spec 4.2)."""
        json_schema = schema.model_json_schema()
        native = "json_schema" in self.adapter.capabilities
        prompt = system if native else system + STRUCTURED_SUFFIX.format(schema=json.dumps(json_schema))
        history = list(messages)
        for attempt in range(2):
            response = self.execute_prompt(prompt, history, tier=tier, max_tokens=max_tokens, json_schema=json_schema if native else None)
            if response.stop in ("error", "refused", "max_tokens"):
                return None
            data = parse_json_object(response.text)
            try:
                if data is None:
                    raise ValueError("no JSON object found in the reply")
                return schema.model_validate(data)
            except (pydantic.ValidationError, ValueError) as exc:
                self._record("validation_error", schema=schema.__name__, attempt=attempt, error=str(exc)[:500])
                history += [
                    Message(role="assistant", content=response.text),
                    Message(role="user", content=f"The reply was invalid: {str(exc)[:500]}. Reply again with only the corrected JSON object."),
                ]
        return None

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Vector retrieval tier only (spec section 7)."""
        if "embeddings" not in self.adapter.capabilities:
            raise NotImplementedError("the configured LLM adapter does not provide embeddings")
        return self.adapter.embed(texts, model=self.config.embedding_model, timeout_s=self.config.timeout_s)

    # --- tools -------------------------------------------------------------
    def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Run a registered tool (Fig 6c callTool). Errors are returned as data, never raised."""
        spec = self.tools.get(name)
        started = time.monotonic()
        if spec is None:
            result: dict[str, Any] = {"error": f"unknown tool: {name}"}
        else:
            try:
                parsed = spec.input_model.model_validate(args or {})
                result = spec.fn(**parsed.model_dump())
                if not isinstance(result, dict):
                    result = {"result": result}
            except pydantic.ValidationError as exc:
                result = {"error": f"invalid arguments: {exc.errors(include_url=False)}"}
            except Exception as exc:  # tool failures go back to the model as an error result
                result = {"error": f"{type(exc).__name__}: {exc}"}
        self._record("tool", name=name, args=args, ok="error" not in result, latency_ms=_ms(started))
        return result

    def run_tool_loop(self, spec: LoopSpec, messages: list[Message]) -> LoopResult:
        return run_tool_loop(self, spec, messages)

    # --- confidence --------------------------------------------------------
    def calculate_confidence(self, signals: dict[str, float], weights: dict[str, float] | None = None) -> float:
        return weighted_confidence(signals, weights)

    def is_low_confidence(self, confidence: float | None) -> bool:
        return confidence is not None and confidence < self.config.confidence_threshold

    # --- trace -------------------------------------------------------------
    def note(self, decision: str, **details: Any) -> None:
        """Let an agent record why it took a step (shown by GET /requests/{id}/trace)."""
        self._record("decision", decision=decision, **details)

    def _record(self, step: str, **data: Any) -> None:
        self.trace.append({"step": step, **data})


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
