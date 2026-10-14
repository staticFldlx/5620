"""Bearer session tokens (A2): the frontend stores `session` and sends `Authorization: Bearer <session>`.

Tokens are signed user ids with a timestamp (django.core.signing): stateless, no table,
no CSRF needed. Logging out is client-side; tokens expire after AUTH_TOKEN_MAX_AGE seconds.
"""

from django.conf import settings
from django.core.signing import BadSignature, TimestampSigner
from ninja.security import HttpBearer

from access_control.identity.models import User

_signer = TimestampSigner(salt="lingopath.session.v1")


def issue_token(user: User) -> str:
    return _signer.sign(str(user.pk))


def user_from_token(token: str) -> User | None:
    try:
        user_id = _signer.unsign(token, max_age=settings.AUTH_TOKEN_MAX_AGE)
    except BadSignature:
        return None
    return User.objects.filter(pk=user_id, is_active=True).first()


class BearerAuth(HttpBearer):
    def authenticate(self, request, token):
        user = user_from_token(token)
        if user is not None:
            request.user = user
        return user
