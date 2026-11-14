from django.apps import AppConfig


class CmsConfig(AppConfig):
    name = "cms"

    def ready(self):
        from .demo import install_network_guard
        install_network_guard()   # refuses outbound HTTP only while TECHNTING_CMS_DEMO_MODE is on
