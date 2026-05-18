from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html

from .models import AdminFincaDocumentVerification, AdminFincaVerificationDocument, AdminFincaVerificationResult
from .services.review import aprovar_verificacio, rebutjar_verificacio


class AdminFincaVerificationDocumentInline(admin.TabularInline):
   model = AdminFincaVerificationDocument
   extra = 0
   readonly_fields = ['doc_type', 'ocr_text', 'extracted_data', 'confidence', 'score', 'score_flags', 'created_at']
   fields = ['fitxer', 'doc_type', 'confidence', 'score', 'created_at']


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
   list_display = ['id', 'user', 'edifici', 'status_badge', 'score_display', 'suggeriment_curt', 'created_at']
   list_filter = ['status', 'created_at']
   search_fields = ['user__email']
   readonly_fields = ['celery_task_id', 'created_at', 'updated_at', 'score', 'score_flags', 'suggeriment']
   inlines = [AdminFincaVerificationDocumentInline, AdminFincaVerificationResultInline]
   actions = ['accio_aprovar', 'accio_rebutjar']

   # ── Columnes visuals ──────────────────────────────────────────────────────

   @admin.display(description='Estat')
   def status_badge(self, obj):
      colors = {
         'pending':  '#888',
         'running':  '#f0a500',
         'review':   '#1a6ef5',
         'approved': '#27ae60',
         'rejected': '#e74c3c',
      }
      color = colors.get(obj.status, '#888')
      return format_html(
         '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
         color, obj.get_status_display()
      )

   @admin.display(description='Score')
   def score_display(self, obj):
      if obj.score is None:
         return '—'
      color = '#27ae60' if obj.score >= 0.75 else ('#f0a500' if obj.score >= 0.50 else '#e74c3c')
      score_pct = f'{obj.score:.0%}'
      return format_html(
         '<span style="color:{};font-weight:bold">{}</span>',
         color, score_pct
      )

   @admin.display(description='Suggeriment')
   def suggeriment_curt(self, obj):
      if not obj.suggeriment:
         return '—'
      return obj.suggeriment[:60] + '...' if len(obj.suggeriment) > 60 else obj.suggeriment

   # ── Accions ───────────────────────────────────────────────────────────────

   @admin.action(description='Aprovar verificacions seleccionades')
   def accio_aprovar(self, request, queryset):
      en_review = queryset.filter(status=AdminFincaDocumentVerification.Status.REVIEW)
      no_review = queryset.exclude(status=AdminFincaDocumentVerification.Status.REVIEW)

      if no_review.exists():
         self.message_user(
            request,
            f'{no_review.count()} verificació(ns) ignorada(es) — no estaven en estat "Revisió manual".',
            level=messages.WARNING,
         )

      aprovades = 0
      errors = 0
      for v in en_review.select_related('user', 'user__profile', 'edifici').prefetch_related('documents'):
         try:
            aprovar_verificacio(v, reviewer=request.user)
            aprovades += 1
         except Exception as exc:
            self.message_user(request, f'Error aprovant #{v.pk}: {exc}', level=messages.ERROR)
            errors += 1

      if aprovades:
         self.message_user(
            request,
            f'{aprovades} verificació(ns) aprovada(es) correctament. Fitxers esborrats.',
            level=messages.SUCCESS,
         )

   @admin.action(description='Rebutjar verificacions seleccionades')
   def accio_rebutjar(self, request, queryset):
      en_review = queryset.filter(status=AdminFincaDocumentVerification.Status.REVIEW)
      no_review = queryset.exclude(status=AdminFincaDocumentVerification.Status.REVIEW)

      if no_review.exists():
         self.message_user(
            request,
            f'{no_review.count()} verificació(ns) ignorada(es) — no estaven en estat "Revisió manual".',
            level=messages.WARNING,
         )

      rebutjades = 0
      for v in en_review.select_related('user', 'edifici').prefetch_related('documents'):
         try:
            rebutjar_verificacio(v, reviewer=request.user, motiu='Rebutjat per l\'administrador del sistema.')
            rebutjades += 1
         except Exception as exc:
            self.message_user(request, f'Error rebutjant #{v.pk}: {exc}', level=messages.ERROR)

      if rebutjades:
         self.message_user(
            request,
            f'{rebutjades} verificació(ns) rebutjada(es). Fitxers esborrats.',
            level=messages.SUCCESS,
         )