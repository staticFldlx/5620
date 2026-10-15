"""Adapter for the school's LLM endpoint, assumed OpenAI-compatible (/chat/completions).

Standard library only (urllib). If the endpoint turns out not to be OpenAI-compatible,
only this file needs to change. Unsupported capabilities are declared via LLM_CAPABILITIES;
the runtime then falls back to prompt-based JSON (spec 4.3).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Iterable

from .base import LLMAdapter, LLMError, LLMResponse, Message, ToolCall, ToolSchema

RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
MAX_RETRY_WAIT_S = 5.0  # a 429 that asks for a longer wait (e.g. a daily quota) fails at once instead of retrying
RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')
FINISH_TO_STOP = {
    "stop": "end",
    "tool_calls": "tool_calls",
    "function_call": "tool_calls",
    "length": "max_tokens",
    "content_filter": "refused",
}


class SchoolAdapter(LLMAdapter):
    def __init__(self, base_url: str, api_key: str, *, capabilities: Iterable[str] = ("tools", "json_schema"), max_retries: int = 2):
        if not base_url:
            raise LLMError("LLM_BASE_URL is not configured")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.capabilities = frozenset(capabilities)
        self.max_retries = max_retries

    def complete(self, system, messages, *, model, tools=None, json_schema=None, max_tokens, timeout_s) -> LLMResponse:
        body: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, *(_to_openai(m) for m in messages)],
        }
        if tools and "tools" in self.capabilities:
            body["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}}
                for t in tools
            ]
        if json_schema and "json_schema" in self.capabilities:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "result", "schema": json_schema}}
        data = self._post("/chat/completions", body, timeout_s)
        try:
            choice = data["choices"][0]
            message = choice.get("message") or {}
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response shape: {exc}") from exc
        calls = []
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": fn.get("arguments")}
            calls.append(ToolCall(id=raw.get("id", ""), name=fn.get("name", ""), args=args))
        usage = data.get("usage") or {}
        return LLMResponse(
            text=message.get("content") or "",
            tool_calls=calls,
            stop=FINISH_TO_STOP.get(choice.get("finish_reason") or "stop", "end"),
            usage={"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0)},
            model=data.get("model", model),
        )

    def embed(self, texts, *, model, timeout_s):
        if "embeddings" not in self.capabilities:
            raise NotImplementedError("embeddings are not enabled in LLM_CAPABILITIES")
        data = self._post("/embeddings", {"model": model, "input": texts}, timeout_s)
        return [item["embedding"] for item in data["data"]]

    def _post(self, path: str, body: dict, timeout_s: float) -> dict:
        payload = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(self.base_url + path, data=payload, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=timeout_s) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in RETRY_STATUS:
                    raise LLMError(f"LLM HTTP {exc.code}: {exc.read()[:300]!r}") from exc
                wait = _retry_after(exc)
                if wait is not None and wait > MAX_RETRY_WAIT_S:
                    raise LLMError(f"LLM rate limit or quota exceeded (HTTP {exc.code}); the provider asks to retry in {int(wait)} s") from exc
                if attempt < self.max_retries:
                    time.sleep(wait if wait is not None else 2**attempt)
                continue
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
            if attempt < self.max_retries:
                time.sleep(2**attempt)
        raise LLMError(f"LLM request failed after {self.max_retries + 1} attempts: {last_error}")


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    """Seconds the provider asks us to wait: the Retry-After header, or Gemini's retryDelay in the body."""
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header and header.strip().replace(".", "", 1).isdigit():
        return float(header)
    try:
        match = RETRY_DELAY.search(exc.read().decode("utf-8", "replace"))
    except Exception:
        return None
    return float(match.group(1)) if match else None


def _to_openai(message: Message) -> dict:
    if message.role == "tool":
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
    item: dict = {"role": message.role, "content": message.content}
    if message.tool_calls:
        item["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.args)}}
            for c in message.tool_calls
        ]
    return item


__all__ = ["SchoolAdapter", "ToolSchema"]
