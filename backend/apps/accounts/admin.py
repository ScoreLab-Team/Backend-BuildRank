from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import User, Profile, TokenLoginLog, AccessDenialLog


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ("email", "is_staff", "is_active", "is_superuser")
    list_filter = ("is_staff", "is_active", "is_superuser")
    ordering = ("email",)
    search_fields = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Informació personal", {"fields": ("first_name", "last_name")}),
        ("Permisos", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates importants", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "is_staff", "is_active", "is_superuser"),
        }),
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "created_at", "updated_at")
    list_filter = ("role",)
    search_fields = ("user__email",)


@admin.register(TokenLoginLog)
class TokenLoginLogAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "login_at", "logout_at", "jti")
    list_filter = ("status", "login_at")
    search_fields = ("user__email", "jti")
    readonly_fields = ("login_at", "jti")
    date_hierarchy = "login_at"


@admin.register(AccessDenialLog)
class AccessDenialLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "role", "accio", "motiu", "edifici_sol_licitat", "ip")
    list_filter = ("role", "timestamp")
    search_fields = ("user__email", "accio", "motiu", "edifici_sol_licitat", "ip")
    readonly_fields = ("timestamp",)
    date_hierarchy = "timestamp"