from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'method', 'endpoint', 'status_code', 'duration_ms', 'ip_address')
    list_filter = ('method', 'status_code', 'resource_type')
    search_fields = ('user__email', 'endpoint', 'ip_address', 'resource_id')
    readonly_fields = [f.name for f in AuditLog._meta.get_fields()]
    ordering = ('-timestamp',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
