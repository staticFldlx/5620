from .base import LLMAdapter, LLMError, LLMResponse, Message, ToolCall, ToolSchema
from .fake_adapter import FakeAdapter


def build_adapter(provider: str, *, base_url: str = "", api_key: str = "", capabilities=("tools", "json_schema")) -> LLMAdapter:
    if provider == "school":
        from .school_adapter import SchoolAdapter

        return SchoolAdapter(base_url, api_key, capabilities=capabilities)
    if provider == "fake":
        # Offline demo: every call returns an empty text unless an agent ships its own script.
        return FakeAdapter(default="")
    raise LLMError(f"unknown LLM_PROVIDER: {provider}")


__all__ = ["LLMAdapter", "LLMError", "LLMResponse", "Message", "ToolCall", "ToolSchema", "FakeAdapter", "build_adapter"]
