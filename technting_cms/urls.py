from django.urls import include, path

from formbuilder import urls as form_urls

urlpatterns = [
    path("crm/", include("crm.urls")),
    path("shield/", include("shield.urls")),
    path("forms/", include("formbuilder.urls")),
    path("api/forms/", include((form_urls.api_patterns, "formapi"))),
    path("f/", include((form_urls.link_patterns, "formlink"))),
    path("", include("cms.urls")),
]
