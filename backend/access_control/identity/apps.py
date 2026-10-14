from django.apps import AppConfig


class IdentityConfig(AppConfig):
    name = "access_control.identity"
    label = "identity"
    default_auto_field = "django.db.models.BigAutoField"
