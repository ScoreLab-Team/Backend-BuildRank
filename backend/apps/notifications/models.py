from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class TipusNotificacio(models.TextChoices):
    NOVA_VOTACIO = 'nova_votacio', 'Nova votació'
    VOTACIO_TANCADA = 'votacio_tancada', 'Votació tancada'
    VOTACIO_CANCELLADA = 'votacio_cancellada', 'Votació cancel·lada'


class Notificacio(models.Model):
    destinatari = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notificacions',
    )
    tipus = models.CharField(max_length=50, choices=TipusNotificacio.choices)
    titol = models.CharField(max_length=200)
    cos = models.TextField(blank=True)
    llegida = models.BooleanField(default=False)
    dataCreacio = models.DateTimeField(auto_now_add=True)

    # GenericFK — allows linking to any model without future schema changes
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    objecte_id = models.PositiveIntegerField(null=True, blank=True)
    objecte = GenericForeignKey('content_type', 'objecte_id')

    class Meta:
        ordering = ['-dataCreacio']

    def __str__(self):
        return f'[{self.tipus}] {self.titol} → {self.destinatari}'
