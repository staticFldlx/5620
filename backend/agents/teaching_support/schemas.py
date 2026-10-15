"""LLM output schemas. Kept flat (no nested models) so the JSON schema has no $defs,
which some OpenAI-compatible endpoints (e.g. Gemini) do not accept."""

from pydantic import BaseModel


class ExplainOutput(BaseModel):
    answer: str
    cited_material_ids: list[str] = []
    self_confidence: float
    in_scope: bool
    needs_teacher: bool = False
    reason: str = ""


class ResourceGuide(BaseModel):
    guide: str
    material_ids: list[str] = []  # in the order the learner should use them


class PracticeItem(BaseModel):
    question: str
    expected_points: list[str] = []  # hidden from the learner, used for feedback
    material_id: str = ""


class PracticeFeedback(BaseModel):
    feedback: str
    met_points: list[str] = []
    missing_points: list[str] = []


class ProgressAnalysis(BaseModel):
    analysis: str
    evidence: list[str] = []
    missing_data: list[str] = []
    suggest_directed_assessment: bool = False


class PlanRecommendations(BaseModel):
    recommendations: list[str]
    evidence: list[str] = []


class LessonBriefing(BaseModel):
    briefing: str
    material_ids: list[str] = []


class MaterialDraft(BaseModel):
    title: str
    content: str
    cited_material_ids: list[str] = []
