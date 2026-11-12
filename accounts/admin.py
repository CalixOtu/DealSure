
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, BusinessProfile


class BusinessProfileInline(admin.StackedInline):
    model = BusinessProfile
    extra = 0
    can_delete = False


@admin.register(User)
class UserAdmin(admin.ModelAdmin):

    list_display = (
        "email",
        "first_name",
        "last_name",
        "role",
        "kyc_status",
        "is_staff",
        "is_active",
    )

    list_filter = (
        "role",
        "kyc_status",
        "is_staff",
        "is_active",
        "email_verified",
    )

    search_fields = (
        "email",
        "first_name",
        "last_name",
        "phone",
    )

    ordering = ("email",)

    readonly_fields = (
        "date_joined",
        "last_login",
    )

    fieldsets = (
        ("Account Information", {
            "fields": (
                "email",
                "first_name",
                "last_name",
                "phone",
                "role",
            )
        }),

        ("Verification", {
            "fields": (
                "kyc_status",
                "email_verified",
                "phone_verified",
                "terms_accepted",
            )
        }),

        ("Permissions", {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            )
        }),

        ("Dates", {
            "fields": (
                "last_login",
                "date_joined",
            )
        }),
    )

    inlines = [BusinessProfileInline]

    def has_add_permission(self, request):
        # Accounts are created through registration.
        # Superusers are created through createsuperuser.
        return False


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):

    list_display = (
        "business_name",
        "user",
        "business_type",
        "state",
        "stellar_wallet_verified",
    )

    search_fields = (
        "business_name",
        "user__email",
        "registration_number",
    )

    list_filter = (
        "business_type",
        "stellar_wallet_verified",
        "state",
    )
