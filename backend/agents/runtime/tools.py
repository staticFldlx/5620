"""Tool registration (spec 4.4)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import pydantic

from infrastructure.llm.base import ToolSchema

ToolKind = Literal["pure", "db", "rag", "llm", "external"]
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ToolSpec:
    name: str  # snake_case, globally unique
    description: str  # written for the model: what it does and when to use it
    input_model: type[pydantic.BaseModel]  # generates the input schema
    fn: Callable[..., dict]  # returns a small JSON-serialisable dict
    kind: ToolKind
    read_only: bool = True  # tools exposed to the model are read-only by default

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise ValueError(f"tool name must be snake_case: {self.name!r}")

    def schema(self) -> ToolSchema:
        return ToolSchema(name=self.name, description=self.description, input_schema=self.input_model.model_json_schema())


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        existing = self._tools.get(spec.name)
        if existing is not None and existing is not spec:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)
