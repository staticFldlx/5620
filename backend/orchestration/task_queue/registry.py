"""Agent registry: AGENT_REGISTRY dotted paths -> classes, and one shared runtime per task."""

from __future__ import annotations

import importlib
from functools import lru_cache

from django.conf import settings

from agents.runtime import AgentRuntime, AIAgent, RuntimeConfig, TaskInput
from infrastructure.llm import FakeAdapter, LLMAdapter, build_adapter
from domain.governance import selectors as governance_selectors


class AgentNotImplemented(LookupError):
    pass


@lru_cache(maxsize=32)
def _import(path: str) -> type[AIAgent]:
    module_path, _, class_name = path.rpartition(".")
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        # Only "the agent module does not exist yet" counts as not implemented;
        # a broken import inside an existing module is a real error.
        if exc.name and module_path.startswith(exc.name):
            raise AgentNotImplemented(path) from exc
        raise
    agent_cls = getattr(module, class_name, None)
    if agent_cls is None:
        raise AgentNotImplemented(path)
    if not (isinstance(agent_cls, type) and issubclass(agent_cls, AIAgent)):
        raise TypeError(f"{path} must subclass agents.runtime.AIAgent")
    return agent_cls


def load_agent_class(agent_id: str) -> type[AIAgent]:
    path = settings.AGENT_REGISTRY.get(agent_id)
    if not path:
        raise AgentNotImplemented(agent_id)
    return _import(path)


def is_implemented(agent_id: str) -> bool:
    try:
        load_agent_class(agent_id)
        return True
    except (AgentNotImplemented, ImportError, TypeError):
        return False


_shared_adapter: LLMAdapter | None = None


def shared_adapter() -> LLMAdapter:
    global _shared_adapter
    if _shared_adapter is None:
        _shared_adapter = build_adapter(
            settings.LLM_PROVIDER,
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            capabilities=settings.LLM_CAPABILITIES,
        )
    return _shared_adapter



def runtime_config(
    agent_id: str | None = None,
) -> RuntimeConfig:
    """Build runtime config with optional agent-specific override."""

    models = {
        "fast": (
            settings.LLM_MODEL_FAST
            or settings.LLM_MODEL_DEFAULT
        ),
        "default": settings.LLM_MODEL_DEFAULT,
    }

    timeout = settings.LLM_TIMEOUT_SECONDS

    if agent_id is not None:
        override = governance_selectors.agent_timeout_override(
            agent_id
        )

        if override is not None:
            timeout = override

    return RuntimeConfig(
        confidence_threshold=settings.AGENT_CONFIDENCE_THRESHOLD,
        models=models,
        timeout_s=timeout,
    )



def build_runtime(agent_cls: type[AIAgent], task: TaskInput) -> AgentRuntime:
    """With LLM_PROVIDER=fake an agent may ship `fake_script(task)` for offline demos (spec 8.10)."""
    adapter = shared_adapter()
    script = getattr(agent_cls, "fake_script", None)
    if settings.LLM_PROVIDER == "fake" and callable(script):
        adapter = FakeAdapter(script(task), default="")
    return AgentRuntime(
        adapter,
        runtime_config(agent_cls.agent_id),
    )


def reset_caches() -> None:
    """For tests that swap AGENT_REGISTRY or LLM settings."""
    global _shared_adapter
    _import.cache_clear()
    _shared_adapter = None
