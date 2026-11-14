from django.apps import AppConfig


class ShieldConfig(AppConfig):
    name = "shield"
    verbose_name = "Technting Shield"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa: F401  (sign-in hooks)
