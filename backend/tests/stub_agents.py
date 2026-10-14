"""Test doubles for the five agents. They are registered only inside tests (see conftest.stubs).

Each stub accepts every task type with its prefix and delegates to BEHAVIOUR[task_type],
a callable (task, runtime) -> AgentResult set by the test.
"""

from collections.abc import Callable

from agents.runtime import AgentResult, AgentRuntime, AgentStatus, AIAgent, TaskInput

BEHAVIOUR: dict[str, Callable[[TaskInput, AgentRuntime], AgentResult]] = {}


class _Prefix(tuple):
    """task_types container accepting any '<agent_id>.*' task type."""

    def __new__(cls, prefix: str):
        obj = super().__new__(cls, ())
        obj.prefix = prefix
        return obj

    def __contains__(self, item):
        return isinstance(item, str) and item.startswith(self.prefix + ".")


class _Stub(AIAgent):
    def execute_task(self, task: TaskInput) -> AgentResult:
        handler = BEHAVIOUR.get(task.task_type)
        if handler is None:
            return AgentResult(AgentStatus.FAILED, {"message": f"no stub for {task.task_type}"}, reason="no_stub")
        return handler(task, self.runtime)


def _make(agent_id: str) -> type[AIAgent]:
    name = "".join(part.title() for part in agent_id.split("_")) + "Stub"
    return type(name, (_Stub,), {"agent_id": agent_id, "task_types": _Prefix(agent_id)})


CoordinatorStub = _make("coordinator")
AssessmentStub = _make("assessment")
PlanningStub = _make("planning")
TeachingSupportStub = _make("teaching_support")
TechOperationsStub = _make("tech_operations")

STUBS = {
    "coordinator": CoordinatorStub,
    "assessment": AssessmentStub,
    "planning": PlanningStub,
    "teaching_support": TeachingSupportStub,
    "tech_operations": TechOperationsStub,
}
