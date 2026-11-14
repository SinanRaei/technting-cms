from django.urls import path

from . import views

app_name = "shield"
urlpatterns = [
    path("", views.home, name="home"),
    path("log.json", views.log_json, name="log_json"),
    path("blocks/add/", views.block_add, name="block_add"),
    path("blocks/<int:block_id>/remove/", views.block_remove, name="block_remove"),
    path("run/<str:job>/", views.run_now, name="run"),
    path("files/accept/", views.integrity_accept, name="integrity_accept"),
    path("public/accept/", views.public_accept, name="public_accept"),
    path("check/", views.ip_check, name="ip_check"),
    path("sessions/<str:ref_id>/end/", views.session_end, name="session_end"),
    path("sessions/others/", views.sessions_others, name="sessions_others"),
    path("alerts/", views.alerts_pref, name="alerts"),
]
