from django.apps import AppConfig


class CrmConfig(AppConfig):
    name = "crm"
    verbose_name = "Technting CRM"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from cms import ui_i18n
        from .ui_ar import AR, COUNT_AR
        for k, v in AR.items():
            ui_i18n.AR.setdefault(k, v)
        for k, v in COUNT_AR.items():
            ui_i18n.COUNT_AR.setdefault(k, v)
