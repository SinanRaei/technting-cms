from django.apps import AppConfig


class FormBuilderConfig(AppConfig):
    name = "formbuilder"
    verbose_name = "Technting Forms"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from cms import ui_i18n
        from .ui_ar import AR
        for k, v in AR.items():
            ui_i18n.AR.setdefault(k, v)
