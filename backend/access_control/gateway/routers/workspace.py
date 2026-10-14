from ninja import Router

from access_control.identity.permissions import Forbidden, require_role
from domain.common import Role
from orchestration.task_queue.contracts import WorkspaceRecord

from .. import lookups, presenters

router = Router(tags=["workspace"])


@router.get("/workspace", response=WorkspaceRecord, exclude_unset=True)
def workspace(request, student_id: str | None = None):
    """Role envelope: Student / Teacher (optionally one assigned student) / Founder operations."""
    user = request.auth
    role = require_role(user, Role.STUDENT, Role.TEACHER, Role.FOUNDER)
    if role == Role.STUDENT:
        if student_id and student_id != str(user.pk):
            raise Forbidden("forbidden_student_access", "Students can only view their own records.")
        return presenters.student_workspace(user)
    if role == Role.TEACHER:
        student = lookups.accessible_student(user, student_id) if student_id else None
        return presenters.teacher_workspace(user, student)
    if student_id:
        raise Forbidden("forbidden_student_access", "The Founder workspace contains operational summaries only.")
    return presenters.founder_workspace(user)
