from django.db import models
from django.conf import settings


class AdminFincaDocumentVerification(models.Model):
    """Un intent de verificació: usuari + edifici + documents pujats."""
    
    class Status(models.TextChoices):
        PENDING   = 'pending',   'Pendent'
        RUNNING   = 'running',   'Processant'
        APPROVED  = 'approved',  'Aprovada'
        REJECTED  = 'rejected',  'Rebutjada'
        REVIEW    = 'review',    'Revisió manual'

    user     = models.ForeignKey(settings.AUTH_USER_MODEL,
                                  on_delete=models.CASCADE,
                                  related_name='verifications')
    edifici  = models.ForeignKey('buildings.Edifici',
                                  on_delete=models.CASCADE,
                                  related_name='verifications')
    status   = models.CharField(max_length=20,
                                 choices=Status.choices,
                                 default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    celery_task_id = models.CharField(max_length=255, blank=True)


class AdminFincaVerificationDocument(models.Model):
    """Cada fitxer individual dins d'una verificació."""

    class DocType(models.TextChoices):
        ACTA_JUNTA    = 'acta_junta',    'Acta de junta'
        CERTIFICAT    = 'certificat',    'Certificat de nomenament'
        CONTRACTE     = 'contracte',     'Contracte d\'administració'
        CERTIFICAT_COL = 'cert_col',     'Certificat col·legial'
        IDENTIFICATIU = 'identificatiu', 'Document identificatiu'
        FACTURA       = 'factura',       'Factura/document comunitat'
        DESCONEGUT    = 'desconegut',    'Desconegut'

    verification  = models.ForeignKey(AdminFincaDocumentVerification,
                                       on_delete=models.CASCADE,
                                       related_name='documents')
    fitxer        = models.FileField(upload_to='verifications/%Y/%m/')
    doc_type      = models.CharField(max_length=30,
                                      choices=DocType.choices,
                                      default=DocType.DESCONEGUT)
    ocr_text      = models.TextField(blank=True)
    extracted_data = models.JSONField(null=True, blank=True)
    confidence    = models.FloatField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)


class AdminFincaVerificationResult(models.Model):
    """Resultat final agregat de la verificació."""

    verification   = models.OneToOneField(AdminFincaDocumentVerification,
                                           on_delete=models.CASCADE,
                                           related_name='result')
    confidence     = models.FloatField()
    nom_detectat   = models.CharField(max_length=255, blank=True)
    dni_detectat   = models.CharField(max_length=20, blank=True)
    carrec_detectat = models.CharField(max_length=100, blank=True)
    comunitat_detectada = models.CharField(max_length=255, blank=True)
    vigencia_detectada  = models.BooleanField(default=False)
    explicacio     = models.TextField(blank=True)
    raw_llm_output = models.JSONField(null=True, blank=True)
    reviewed_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reviews_fetes'
    )
    reviewed_at    = models.DateTimeField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)