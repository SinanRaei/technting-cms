from django.urls import path

from . import newsletter, prospects, views

app_name = "crm"
urlpatterns = [
    path("", views.home, name="home"),
    path("pipeline/", views.pipeline, name="pipeline"),
    path("prospects/", prospects.prospects, name="prospects"),
    path("prospects/new/", prospects.prospect_edit, name="prospect_new"),
    path("prospects/move/", prospects.prospect_move, name="prospect_move"),
    path("prospects/status/", prospects.prospect_status, name="prospect_status"),
    path("prospects/export/", prospects.prospects_export, name="prospects_export"),
    path("prospects/import/", prospects.prospects_import, name="prospects_import"),
    path("prospects/<int:prospect_id>/", prospects.prospect_detail, name="prospect"),
    path("prospects/<int:prospect_id>/edit/", prospects.prospect_edit, name="prospect_edit"),
    path("deals/", views.deals, name="deals"),
    path("deals/new/", views.deal_new, name="deal_new"),
    path("deals/<int:deal_id>/", views.deal_detail, name="deal"),
    path("api/deals/<int:deal_id>/move/", views.api_move, name="api_move"),
    path("tasks/", views.tasks, name="tasks"),
    path("tasks/<int:activity_id>/toggle/", views.task_toggle, name="task_toggle"),
    path("contacts/", views.contacts, name="contacts"),
    path("contacts/new/", views.contact_edit, name="contact_new"),
    path("contacts/<int:contact_id>/", views.contact_detail, name="contact"),
    path("contacts/<int:contact_id>/edit/", views.contact_edit, name="contact_edit"),
    path("organisations/", views.organizations, name="organizations"),
    path("organisations/new/", views.organization_edit, name="organization_new"),
    path("organisations/<int:org_id>/", views.organization_detail, name="organization"),
    path("organisations/<int:org_id>/edit/", views.organization_edit, name="organization_edit"),
    path("search/", views.search, name="search"),
    path("newsletter/", newsletter.subscribers, name="subscribers"),
    path("settings/", views.settings_page, name="settings"),
]
