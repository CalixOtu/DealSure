from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "",
        RedirectView.as_view(
            pattern_name="accounts:dashboard",
            permanent=False,
        ),
        name="home",
    ),
    path("accounts/", include("accounts.urls")),
    path("procurement/", include("procurement.urls")),
    path("ai/", include("ai_engine.urls")),
    path("escrow/", include("escrow.urls")),
]
