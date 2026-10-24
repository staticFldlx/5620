from django.conf import settings
from django.http import FileResponse, Http404
from django.urls import path, re_path

from access_control.gateway.api import api


def frontend(request):
    index = settings.FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise Http404("Frontend build is unavailable")
    return FileResponse(index.open("rb"), content_type="text/html")


urlpatterns = [
    path("api/v1/", api.urls),
    re_path(r"^(?!api/|assets/|media/).*$", frontend),
]
