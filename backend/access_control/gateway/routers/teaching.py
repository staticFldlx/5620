"""Human teaching records: observations, availability, lesson outcomes, materials (no agent involved)."""

from ninja import Router

from access_control.identity.permissions import require_role
from domain.common import DomainError, Role, iso
from domain.learning import selectors as learning
from domain.learning import services as learning_services
from domain.learning.models import TeacherComment
from domain.learning.views import availability_view, lesson_view, material_view
from orchestration.task_queue.contracts import LessonRecord, MaterialRecord

from .. import lookups
from ..schemas import AvailabilityIn, AvailabilityOut, LessonPatchIn, MaterialPatchIn, ObservationIn, ObservationOut

router = Router(tags=["teaching"])


@router.patch("/students/{student_id}/observation", response=ObservationOut)
def save_observation(request, student_id: str, body: ObservationIn):
    user = request.auth
    require_role(user, Role.TEACHER)
    student = lookups.accessible_student(user, student_id)
    if not body.note.strip():
        raise DomainError("note_required", "Write an observation before saving.", status=400)
    comment = learning_services.add_teacher_comment(user, teacher=user, student=student, kind=TeacherComment.Kind.OBSERVATION, text=body.note)
    return {"note": comment.text, "updated_at": iso(comment.created_at), "teacher_id": str(user.pk)}


@router.patch("/teachers/me/availability", response=AvailabilityOut)
def save_availability(request, body: AvailabilityIn):
    user = request.auth
    require_role(user, Role.TEACHER)
    slots = learning_services.replace_availability(user, user, windows=[w.dict() for w in body.availability], tz=body.timezone)
    return {"timezone": body.timezone, "availability": [availability_view(s) for s in slots]}


@router.patch("/lessons/{lesson_id}", response=LessonRecord)
def save_lesson(request, lesson_id: str, body: LessonPatchIn):
    """Attendance and feedback only; time changes go through the Coordinator (reschedule)."""
    user = request.auth
    require_role(user, Role.TEACHER)
    lesson = lookups.get_or_404(learning.lesson, lesson_id, "Lesson")
    lookups.require_owner(lesson.teacher_id == user.pk, "You do not teach this lesson.")
    learning_services.record_lesson_outcome(user, lesson, attendance=body.attendance, feedback=body.feedback, teacher=user)
    from orchestration.milestones import publish_ready_milestone
    publish_ready_milestone(lesson.student, user)
    return lesson_view(learning.lesson(lesson.pk))


def _readable_material(user, material_id: str):
    role = require_role(user, Role.STUDENT, Role.TEACHER)
    material = lookups.get_or_404(learning.material, material_id, "Material")
    if role == Role.STUDENT:
        # students only see approved material of their own lessons
        if material.status != "approved" or material.lesson.student_id != user.pk:
            raise lookups.not_found("Material")
    else:
        lookups.require_owner(material.lesson.teacher_id == user.pk, "You do not teach this lesson.")
    return material


@router.get("/materials/{material_id}", response=MaterialRecord)
def get_material(request, material_id: str):
    return material_view(_readable_material(request.auth, material_id))


@router.patch("/materials/{material_id}", response=MaterialRecord)
def save_material(request, material_id: str, body: MaterialPatchIn):
    user = request.auth
    require_role(user, Role.TEACHER)
    material = _readable_material(user, material_id)
    approve = body.status == "approved" or body.action == "approve"  # A11: both formats accepted
    learning_services.edit_material(user, material, content=body.content, approve=approve, by=user)
    return material_view(learning.material(material.pk))
