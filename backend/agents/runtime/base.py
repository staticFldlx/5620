"""Agent base types (spec 4.1, Fig 6a AIAgent). Pure Python: no Django imports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar, Literal

if TYPE_CHECKING:
    from .runtime import AgentRuntime


class AgentStatus(str, Enum):
    OK = "ok"
    NEEDS_INPUT = "needs_input"  # ask the user: UC01 3a follow-up, next assessment item
    NEEDS_ESCALATION = "needs_escalation"  # human review afterwards (Fig 8a)
    AWAITING_APPROVAL = "awaiting_approval"  # human approval first (Fig 8b, UC03 step 8)
    TRIGGER_REPLAN = "trigger_replan"  # ask the Orchestrator to append planning.revise_plan once
    FAILED = "failed"


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    actor_id: str
    actor_role: Literal["student", "teacher", "founder", "system"]
    hops: int = 0


@dataclass(frozen=True)
class TaskInput:
    """Built by the Orchestrator from an AgentTask row."""

    task_id: str
    task_type: str  # "<agent_id>.<verb_noun>", e.g. "teaching_support.answer_question"
    student_id: str | None
    payload: dict[str, Any]
    ctx: RequestContext


@dataclass
class AgentResult:
    status: AgentStatus
    payload: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None  # required for any result that involves judgement
    reason: str | None = None  # snake_case reason code, required for escalation / failure
    trace: list[dict[str, Any]] = field(default_factory=list)


class AIAgent(ABC):
    agent_id: ClassVar[str]
    task_types: ClassVar[tuple[str, ...]]  # task types this agent accepts

    def __init__(self, runtime: "AgentRuntime"):
        self.runtime = runtime

    @abstractmethod
    def execute_task(self, task: TaskInput) -> AgentResult: ...

    def score_confidence(self, signals: dict[str, float], weights: dict[str, float] | None = None) -> float:
        return self.runtime.calculate_confidence(signals, weights)
