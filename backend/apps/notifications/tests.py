from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, Profile
from apps.buildings.models import Edifici, Localitzacio, Habitatge
from apps.community.models import Votacio, OpcioVot
from .models import Notificacio


def create_user(email, role='owner'):
    user = User.objects.create_user(
        email=email,
        password='testpass123',
        first_name='Test',
        last_name='User',
    )
    Profile.objects.filter(user=user).update(role=role)
    return user


def auth_client(user):
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


def create_edifici(admin_user=None):
    loc = Localitzacio.objects.create(
        carrer='Carrer Test',
        numero='1',
        codiPostal='08001',
        barri='Eixample',
        latitud=41.38,
        longitud=2.17,
    )
    return Edifici.objects.create(
        localitzacio=loc,
        anyConstruccio=2000,
        tipologia='Residencial',
        superficieTotal=500.0,
        nombrePlantes=5,
        administradorFinca=admin_user,
    )


def create_habitatge(edifici, user, ref='CAD001', planta='1', porta='A'):
    return Habitatge.objects.create(
        edifici=edifici,
        referenciaCadastral=ref,
        planta=planta,
        porta=porta,
        superficie=60.0,
        usuari=user,
        solicitant=user,
    )


def create_votacio(edifici, creator):
    v = Votacio.objects.create(
        edifici=edifici,
        titol='Votació de prova',
        descripcio='Descripció de prova',
        creador=creator,
        estat='oberta',
    )
    OpcioVot.objects.create(votacio=v, text='Sí', ordre=0)
    OpcioVot.objects.create(votacio=v, text='No', ordre=1)
    return v


# ---------------------------------------------------------------------------
# Signals — notificació en crear votació
# ---------------------------------------------------------------------------

class NotificacioCreacioVotacioTest(TestCase):

    def setUp(self):
        self.admin = create_user('admin@test.com', role='admin')
        self.owner = create_user('owner@test.com', role='owner')
        self.tenant = create_user('tenant@test.com', role='tenant')
        self.outsider = create_user('outsider@test.com', role='owner')
        self.edifici = create_edifici(admin_user=self.admin)
        create_habitatge(self.edifici, self.owner, ref='CAD001')
        create_habitatge(self.edifici, self.tenant, ref='CAD002', planta='2', porta='B')

    def test_nova_votacio_genera_notificacio_per_a_cada_membre(self):
        create_votacio(self.edifici, self.admin)
        self.assertEqual(Notificacio.objects.count(), 3)  # admin + owner + tenant
        self.assertTrue(Notificacio.objects.filter(destinatari=self.admin).exists())
        self.assertTrue(Notificacio.objects.filter(destinatari=self.owner).exists())
        self.assertTrue(Notificacio.objects.filter(destinatari=self.tenant).exists())

    def test_outsider_no_rep_notificacio(self):
        create_votacio(self.edifici, self.admin)
        self.assertFalse(Notificacio.objects.filter(destinatari=self.outsider).exists())

    def test_notificacio_tipus_nova_votacio(self):
        create_votacio(self.edifici, self.admin)
        notif = Notificacio.objects.get(destinatari=self.owner)
        self.assertEqual(notif.tipus, 'nova_votacio')

    def test_notificacio_titol_inclou_titol_votacio(self):
        create_votacio(self.edifici, self.admin)
        notif = Notificacio.objects.get(destinatari=self.owner)
        self.assertIn('Votació de prova', notif.titol)

    def test_notificacio_apunta_a_la_votacio(self):
        v = create_votacio(self.edifici, self.admin)
        notif = Notificacio.objects.get(destinatari=self.owner)
        self.assertEqual(notif.objecte_id, v.pk)
        self.assertEqual(notif.objecte, v)


# ---------------------------------------------------------------------------
# Signals — notificació en tancar / cancel·lar votació
# ---------------------------------------------------------------------------

class NotificacioEstatVotacioTest(TestCase):

    def setUp(self):
        self.admin = create_user('admin@test.com', role='admin')
        self.owner = create_user('owner@test.com', role='owner')
        self.edifici = create_edifici(admin_user=self.admin)
        create_habitatge(self.edifici, self.owner)
        self.votacio = create_votacio(self.edifici, self.admin)
        Notificacio.objects.all().delete()  # clear creation notifications

    def test_tancar_votacio_genera_notificacio(self):
        self.votacio.estat = 'tancada'
        self.votacio.save()
        self.assertEqual(Notificacio.objects.filter(tipus='votacio_tancada').count(), 2)

    def test_cancellar_votacio_genera_notificacio(self):
        self.votacio.estat = 'cancel·lada'
        self.votacio.save()
        self.assertEqual(Notificacio.objects.filter(tipus='votacio_cancellada').count(), 2)

    def test_modificar_titol_no_genera_notificacio(self):
        self.votacio.titol = 'Títol modificat'
        self.votacio.save()
        self.assertEqual(Notificacio.objects.count(), 0)

    def test_tancar_via_api_genera_notificacio(self):
        from django.urls import reverse as dj_reverse
        client = auth_client(self.admin)
        client.patch(
            dj_reverse('votacio-detail', kwargs={'pk': self.votacio.pk}),
            {'estat': 'tancada'},
            format='json',
        )
        self.assertTrue(Notificacio.objects.filter(tipus='votacio_tancada').exists())


# ---------------------------------------------------------------------------
# API — llistat, no llegides, marcar llegida
# ---------------------------------------------------------------------------

class NotificacioAPITest(TestCase):

    def setUp(self):
        self.admin = create_user('admin@test.com', role='admin')
        self.owner = create_user('owner@test.com', role='owner')
        self.edifici = create_edifici(admin_user=self.admin)
        create_habitatge(self.edifici, self.owner)
        create_votacio(self.edifici, self.admin)  # generates 2 notifications

    def test_user_only_sees_own_notifications(self):
        client = auth_client(self.owner)
        response = client.get(reverse('notificacio-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [n['id'] for n in response.data]
        self.assertTrue(
            Notificacio.objects.filter(pk__in=ids, destinatari=self.owner).count() == len(ids)
        )

    def test_unread_count(self):
        client = auth_client(self.owner)
        response = client.get(reverse('notificacio-no-llegides'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['no_llegides'], 1)

    def test_mark_one_as_read(self):
        notif = Notificacio.objects.get(destinatari=self.owner)
        client = auth_client(self.owner)
        response = client.post(reverse('notificacio-llegir', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        notif.refresh_from_db()
        self.assertTrue(notif.llegida)

    def test_unread_count_drops_after_marking_read(self):
        notif = Notificacio.objects.get(destinatari=self.owner)
        client = auth_client(self.owner)
        client.post(reverse('notificacio-llegir', kwargs={'pk': notif.pk}))
        response = client.get(reverse('notificacio-no-llegides'))
        self.assertEqual(response.data['no_llegides'], 0)

    def test_mark_all_as_read(self):
        Notificacio.objects.create(
            destinatari=self.owner, tipus='nova_votacio', titol='Segona'
        )
        client = auth_client(self.owner)
        client.post(reverse('notificacio-llegir-totes'))
        self.assertEqual(
            Notificacio.objects.filter(destinatari=self.owner, llegida=False).count(), 0
        )

    def test_cannot_read_other_users_notification(self):
        notif = Notificacio.objects.get(destinatari=self.admin)
        client = auth_client(self.owner)
        response = client.post(reverse('notificacio-llegir', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_cannot_access(self):
        response = APIClient().get(reverse('notificacio-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
