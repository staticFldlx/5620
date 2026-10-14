"""Request id and CORS, written in-house to avoid extra dependencies."""

import uuid

from django.conf import settings
from django.http import HttpResponse

CORS_HEADERS = "Authorization, Content-Type, X-Request-ID"
CORS_METHODS = "GET, POST, PATCH, OPTIONS"


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response


class CorsMiddleware:
    """Bearer-token API: no cookies, so a plain origin allow-list is enough."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin")
        allowed = origin and (origin in settings.CORS_ALLOWED_ORIGINS or "*" in settings.CORS_ALLOWED_ORIGINS)
        if request.method == "OPTIONS" and "Access-Control-Request-Method" in request.headers:
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Headers"] = CORS_HEADERS
            response["Access-Control-Allow-Methods"] = CORS_METHODS
            response["Access-Control-Expose-Headers"] = "X-Request-ID"
            response["Access-Control-Max-Age"] = "600"
            response["Vary"] = "Origin"
        return response
