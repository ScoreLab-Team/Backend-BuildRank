from django.db import models
from django.conf import settings
from apps.buildings.models import Edifici


class EstatVotacio(models.TextChoices):
    OBERTA = 'oberta', 'Oberta'
    TANCADA = 'tancada', 'Tancada'
    CANCEL_LADA = 'cancel·lada', 'Cancel·lada'


class Votacio(models.Model):
    edifici = models.ForeignKey(
        Edifici, on_delete=models.CASCADE, related_name='votacions'
    )
    titol = models.CharField(max_length=200)
    descripcio = models.TextField(blank=True)
    creador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='votacions_creades',
    )
    dataCreacio = models.DateTimeField(auto_now_add=True)
    dataLimit = models.DateTimeField(null=True, blank=True)
    estat = models.CharField(
        max_length=20,
        choices=EstatVotacio.choices,
        default=EstatVotacio.OBERTA,
    )

    class Meta:
        ordering = ['-dataCreacio']

    def __str__(self):
        return f"{self.titol} ({self.edifici})"


class OpcioVot(models.Model):
    votacio = models.ForeignKey(
        Votacio, on_delete=models.CASCADE, related_name='opcions'
    )
    text = models.CharField(max_length=200)
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordre']

    def __str__(self):
        return f"{self.votacio.titol} – {self.text}"


class Vot(models.Model):
    votacio = models.ForeignKey(
        Votacio, on_delete=models.CASCADE, related_name='vots'
    )
    opcio = models.ForeignKey(
        OpcioVot, on_delete=models.CASCADE, related_name='vots'
    )
    usuari = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vots_emesos',
    )
    dataEmissio = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('votacio', 'usuari')

    def __str__(self):
        return f"{self.usuari} → {self.opcio.text} ({self.votacio.titol})"
