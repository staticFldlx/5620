"""Read-only tools for the answer_question tool loop (TEACHING_SUPPORT_EXPLAIN_MODE=loop).

The model decides what to look up. Only the learner's own approved materials can be read, and
only materials actually read count as valid citations.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from agents.runtime import ToolSpec

from . import context


class NoInput(BaseModel):
    pass


class MaterialInput(BaseModel):
    material_id: str


class ExplainTools:
    def __init__(self, student: Any):
        self.student = student
        self.available = {m["id"]: m for m in context.stage_materials(student)}
        self.read: dict[str, dict] = {}  # materials the model actually read, in reading order

    def get_student_context(self) -> dict:
        learner = context.learner(self.student)
        learner.pop("recent_questions", None)
        return learner

    def list_stage_materials(self) -> dict:
        return {"materials": [{"id": m["id"], "title": m["title"], "locator": m["locator"]} for m in self.available.values()]}

    def read_material(self, material_id: str) -> dict:
        material = self.available.get(material_id)
        if material is None:
            return {"error": "This material is not available to the learner. Use list_stage_materials for valid ids."}
        self.read[material_id] = material
        return material

    def recent_questions(self) -> dict:
        return {"questions": context.recent_questions(self.student)}

    def specs(self) -> tuple[ToolSpec, ...]:
        return (
            ToolSpec("get_student_context", "Learner's level, goal, current plan stage and weak areas.", NoInput, self.get_student_context, "db"),
            ToolSpec("list_stage_materials", "Ids and titles of the approved course materials for this learner, current stage first.", NoInput, self.list_stage_materials, "db"),
            ToolSpec("read_material", "Full text of one approved material. Read a material before citing it.", MaterialInput, self.read_material, "db"),
            ToolSpec("recent_questions", "The learner's recent questions, to keep explanations consistent.", NoInput, self.recent_questions, "db"),
        )
