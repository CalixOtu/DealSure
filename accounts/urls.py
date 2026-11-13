from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_redirect, name="dashboard"),
    path("buyer/dashboard/", views.buyer_dashboard, name="buyer_dashboard"),
    path("supplier/dashboard/", views.supplier_dashboard, name="supplier_dashboard"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/edit/", views.profile_edit, name="profile_edit"),
    path("business-profile/", views.business_profile_view, name="business_profile"),
    path(
        "business-profile/edit/",
        views.business_profile_edit,
        name="business_profile_edit",
    ),
    path(
        "stellar-wallet/challenge/",
        views.stellar_wallet_challenge,
        name="stellar_wallet_challenge",
    ),
    path(
        "stellar-wallet/verify/",
        views.stellar_wallet_verify,
        name="stellar_wallet_verify",
    ),
]
