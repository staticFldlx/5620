"""Unified error body (A4): {"message": ..., "error": {"code", "message", "request_id"}}.

`message` is what the frontend displays (it reads response.data.message); `error` is the spec format.
"""

from __future__ import annotations

import logging

from django.http import Http404
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, HttpError, ValidationError

from domain.common import DomainError
from infrastructure.monitoring import log_event


class ApiError(DomainError):
    """DomainError carrying extra body fields, e.g. the failed request envelope (A5)."""

    def __init__(self, code: str, message: str, *, status: int, extra: dict | None = None):
        super().__init__(code, message, status=status)
        self.extra = extra or {}


def error_body(request, code: str, message: str, extra: dict | None = None) -> dict:
    return {"message": message, "error": {"code": code, "message": message, "request_id": getattr(request, "request_id", "")}, **(extra or {})}


def install(api: NinjaAPI) -> None:
    @api.exception_handler(DomainError)
    def domain_error(request, exc: DomainError):
        return api.create_response(request, error_body(request, exc.code, exc.message, getattr(exc, "extra", None)), status=exc.status)

    @api.exception_handler(ValidationError)
    def validation_error(request, exc: ValidationError):
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', ()) if p not in ('body', 'payload'))}: {e.get('msg')}" for e in exc.errors[:5]
        )
        return api.create_response(request, error_body(request, "invalid_input", f"Invalid input - {problems}"), status=400)

    @api.exception_handler(AuthenticationError)
    def not_authenticated(request, exc):
        return api.create_response(request, error_body(request, "not_authenticated", "Sign in with an authorised account."), status=401)

    @api.exception_handler(HttpError)
    def http_error(request, exc: HttpError):
        return api.create_response(request, error_body(request, "http_error", str(exc)), status=exc.status_code)

    @api.exception_handler(Http404)
    def not_found(request, exc):
        return api.create_response(request, error_body(request, "not_found", "Record not found."), status=404)

    @api.exception_handler(Exception)
    def unexpected(request, exc: Exception):
        log_event("unhandled_api_error", level=logging.ERROR, exc_info=True, path=request.path, request_id=getattr(request, "request_id", ""))
        return api.create_response(request, error_body(request, "internal_error", "Unexpected server error."), status=500)
