"""LLM adapter interface (spec 4.3). Vendor-neutral and free of Django imports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

Role = Literal["system", "user", "assistant", "tool"]
StopReason = Literal["end", "tool_calls", "max_tokens", "refused", "error"]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()  # assistant messages that requested tools
    tool_call_id: str | None = None  # tool result messages


@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop: StopReason = "end"
    usage: dict[str, int] = field(default_factory=dict)  # input_tokens / output_tokens
    model: str = ""


class LLMError(Exception):
    """Raised when the provider cannot produce a usable response after retries."""


class LLMAdapter(ABC):
    capabilities: ClassVar[frozenset[str]] = frozenset()  # subset of {"tools", "json_schema", "embeddings"}

    @abstractmethod
    def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        model: str,
        tools: list[ToolSchema] | None = None,
        json_schema: dict | None = None,
        max_tokens: int,
        timeout_s: float,
    ) -> LLMResponse: ...

    def embed(self, texts: list[str], *, model: str, timeout_s: float) -> list[list[float]]:
        raise NotImplementedError("this adapter does not provide embeddings")
