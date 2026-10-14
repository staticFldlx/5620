from django.urls import path

from access_control.gateway.api import api

urlpatterns = [
    path("api/v1/", api.urls),
]
