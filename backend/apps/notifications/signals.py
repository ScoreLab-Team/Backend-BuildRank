from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.community.models import Votacio


def _get_membres(votacio):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    ids = set()
    edifici = votacio.edifici
    if edifici.administradorFinca_id:
        ids.add(edifici.administradorFinca_id)
    for h in edifici.habitatges.filter(usuari__isnull=False):
        ids.add(h.usuari_id)
    return User.objects.filter(pk__in=ids)


@receiver(pre_save, sender=Votacio)
def _track_estat(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_estat = Votacio.objects.get(pk=instance.pk).estat
        except Votacio.DoesNotExist:
            instance._old_estat = None
    else:
        instance._old_estat = None


@receiver(post_save, sender=Votacio)
def _notificar_votacio(sender, instance, created, **kwargs):
    from django.contrib.contenttypes.models import ContentType
    from .models import Notificacio, TipusNotificacio

    ct = ContentType.objects.get_for_model(Votacio)
    membres = list(_get_membres(instance))

    if created:
        Notificacio.objects.bulk_create([
            Notificacio(
                destinatari=user,
                tipus=TipusNotificacio.NOVA_VOTACIO,
                titol=f'Nova votació: {instance.titol}',
                cos=instance.descripcio[:200] if instance.descripcio else '',
                content_type=ct,
                objecte_id=instance.pk,
            )
            for user in membres
        ])
        return

    old = getattr(instance, '_old_estat', None)
    if old is None or old == instance.estat:
        return

    if instance.estat == 'tancada':
        tipus = TipusNotificacio.VOTACIO_TANCADA
        titol = f'Votació tancada: {instance.titol}'
    elif instance.estat == 'cancel·lada':
        tipus = TipusNotificacio.VOTACIO_CANCELLADA
        titol = f'Votació cancel·lada: {instance.titol}'
    else:
        return

    Notificacio.objects.bulk_create([
        Notificacio(
            destinatari=user,
            tipus=tipus,
            titol=titol,
            content_type=ct,
            objecte_id=instance.pk,
        )
        for user in membres
    ])
