from django.contrib import admin

from django.contrib import admin

from .models import AdminFincaDocumentVerification, AdminFincaVerificationDocument, AdminFincaVerificationResult


class AdminFincaVerificationDocumentInline(admin.TabularInline):
   model = AdminFincaVerificationDocument
   extra = 0
   readonly_fields = ['doc_type', 'ocr_text', 'extracted_data', 'confidence', 'created_at']
   fields = ['fitxer', 'doc_type', 'confidence', 'created_at']


class AdminFincaVerificationResultInline(admin.StackedInline):
   model = AdminFincaVerificationResult
   extra = 0
   readonly_fields = [
      'confidence', 'nom_detectat', 'dni_detectat', 'carrec_detectat',
      'comunitat_detectada', 'vigencia_detectada', 'explicacio',
      'reviewed_by', 'reviewed_at', 'created_at',
   ]


@admin.register(AdminFincaDocumentVerification)
class AdminFincaDocumentVerificationAdmin(admin.ModelAdmin):
   list_display = ['id', 'user', 'edifici', 'status', 'created_at']
   list_filter = ['status', 'created_at']
   search_fields = ['user__email', 'edifici__nom']
   readonly_fields = ['celery_task_id', 'created_at', 'updated_at']
   inlines = [AdminFincaVerificationDocumentInline, AdminFincaVerificationResultInline]
