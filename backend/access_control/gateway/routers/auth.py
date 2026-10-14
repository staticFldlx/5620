from ninja import Router

from access_control.identity import services as identity
from domain.common import DomainError
from domain.governance.services import record_audit

from ..auth import issue_token
from ..presenters import user_record
from ..schemas import LoginIn, RegisterIn, SessionOut

router = Router(tags=["auth"], auth=None)


@router.post("/register", response=SessionOut)
def register(request, body: RegisterIn):
    """Public registration always creates a Student."""
    user = identity.register_student(name=body.name, email=body.email, password=body.password)
    return {"session": issue_token(user), "user": user_record(user)}


@router.post("/login", response=SessionOut)
def login(request, body: LoginIn):
    user = identity.authenticate(body.email, body.password)
    if user is None:
        raise DomainError("invalid_credentials", "Invalid email or password.", status=401)
    record_audit(user, "user.login", user)
    return {"session": issue_token(user), "user": user_record(user)}
