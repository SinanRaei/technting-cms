from django.urls import path

from . import api, views

app_name = "formbuilder"
urlpatterns = [
    path("", views.forms_list, name="list"),
    path("<int:form_id>/", views.form_edit, name="edit"),
    path("<int:form_id>/questions/", views.form_questions, name="questions"),
    path("<int:form_id>/questions/<int:field_id>/", views.field_edit, name="field"),
    path("<int:form_id>/calculations/", views.form_calcs, name="calcs"),
    path("<int:form_id>/results/", views.form_results, name="results"),
    path("<int:form_id>/results/<int:n>/", views.block_edit, name="block"),
    path("<int:form_id>/preview/", views.form_preview, name="preview"),
    path("<int:form_id>/duplicate/", views.form_duplicate, name="duplicate"),
    path("<int:form_id>/delete/", views.form_delete, name="delete"),
    path("<int:form_id>/submissions/", views.submissions, name="submissions"),
    path("<int:form_id>/export.csv", views.submissions_export, name="export"),
    path("<int:form_id>/links/", views.form_links, name="links"),
    path("links/<int:link_id>/", views.link_detail, name="link"),
    path("submissions/<int:sub_id>/", views.submission_detail, name="submission"),
]

api_patterns = [
    path("<slug:slug>/", api.definition, name="api_form"),
    path("<slug:slug>/save", api.save, name="api_save"),
    path("<slug:slug>/resume", api.resume, name="api_resume"),
    path("<slug:slug>/submit", api.submit, name="api_submit"),
    path("<slug:slug>/event", api.event, name="api_event"),
]

link_patterns = [
    path("<str:token>/", api.link_page, name="link_page"),
]
