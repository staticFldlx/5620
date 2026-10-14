"""Shared Agent Runtime Library (Fig 5, Fig 6c). Agents import only from here and domain selectors/services."""

from infrastructure.llm.base import Message

from .base import AgentResult, AgentStatus, AIAgent, RequestContext, TaskInput
from .loop import LoopResult, LoopSpec
from .runtime import AgentRuntime, RuntimeConfig
from .tools import ToolSpec

__all__ = [
    "AIAgent",
    "AgentResult",
    "AgentRuntime",
    "AgentStatus",
    "LoopResult",
    "LoopSpec",
    "Message",
    "RequestContext",
    "RuntimeConfig",
    "TaskInput",
    "ToolSpec",
]
