from .base import LLMAdapter, LLMError, LLMResponse, Message, ToolCall, ToolSchema
from .fake_adapter import FakeAdapter

# Any OpenAI-compatible /chat/completions endpoint (Gemini, the ELEC5620 proxy, ...).
# "school" is kept as an alias so existing .env files keep working.
OPENAI_COMPATIBLE_PROVIDERS = frozenset({"openai", "school"})


def build_adapter(provider: str, *, base_url: str = "", api_key: str = "", capabilities=("tools", "json_schema")) -> LLMAdapter:
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        from .school_adapter import SchoolAdapter

        return SchoolAdapter(base_url, api_key, capabilities=capabilities)
    if provider == "fake":
        # Offline demo: every call returns an empty text unless an agent ships its own script.
        return FakeAdapter(default="")
    raise LLMError(f"unknown LLM_PROVIDER: {provider} (expected openai, school or fake)")


__all__ = [
    "LLMAdapter",
    "LLMError",
    "LLMResponse",
    "Message",
    "ToolCall",
    "ToolSchema",
    "FakeAdapter",
    "OPENAI_COMPATIBLE_PROVIDERS",
    "build_adapter",
]
