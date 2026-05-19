from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, Profile
from apps.buildings.models import Edifici, Localitzacio, Habitatge
from .models import Votacio, OpcioVot, Vot


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


def create_votacio(edifici, creator, estat='oberta'):
    v = Votacio.objects.create(
        edifici=edifici,
        titol='Votació de prova',
        descripcio='Descripció de prova',
        creador=creator,
        estat=estat,
    )
    OpcioVot.objects.create(votacio=v, text='Sí', ordre=0)
    OpcioVot.objects.create(votacio=v, text='No', ordre=1)
    return v


# ---------------------------------------------------------------------------
# Tarea 1 — Model tests
# ---------------------------------------------------------------------------

class VotacioModelTest(TestCase):

    def setUp(self):
        self.admin = create_user('admin@test.com', role='admin')
        self.edifici = create_edifici(admin_user=self.admin)
        self.votacio = create_votacio(self.edifici, self.admin)

    def test_votacio_created(self):
        self.assertEqual(Votacio.objects.count(), 1)
        self.assertEqual(self.votacio.estat, 'oberta')
        self.assertEqual(self.votacio.opcions.count(), 2)

    def test_unique_together_prevents_duplicate_vote(self):
        """La restricció unique_together (votacio, usuari) impedeix vot duplicat a la BD."""
        opcio = self.votacio.opcions.first()
        Vot.objects.create(votacio=self.votacio, opcio=opcio, usuari=self.admin)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Vot.objects.create(votacio=self.votacio, opcio=opcio, usuari=self.admin)


# ---------------------------------------------------------------------------
# Tarea 2 — API tests
# ---------------------------------------------------------------------------

class VotacioCreateAPITest(TestCase):

    def setUp(self):
        self.admin = create_user('admin@test.com', role='admin')
        self.owner = create_user('owner@test.com', role='owner')
        self.tenant = create_user('tenant@test.com', role='tenant')
        self.outsider = create_user('outsider@test.com', role='owner')
        self.edifici = create_edifici(admin_user=self.admin)
        Habitatge.objects.create(
            edifici=self.edifici,
            referenciaCadastral='CAD000',
            planta='0',
            porta='A',
            superficie=70.0,
            usuari=self.owner,
            solicitant=self.owner,
        )
        Habitatge.objects.create(
            edifici=self.edifici,
            referenciaCadastral='CAD001',
            planta='1',
            porta='A',
            superficie=60.0,
            usuari=self.tenant,
            solicitant=self.tenant,
        )
        self.url = reverse('votacio-list-create')
        self.payload = {
            'edifici': self.edifici.idEdifici,
            'titol': 'Nova votació',
            'descripcio': 'Prova',
            'opcions': ['Sí', 'No', 'Abstenció'],
        }

    def test_admin_can_create_votacio(self):
        client = auth_client(self.admin)
        response = client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Votacio.objects.count(), 1)
        self.assertEqual(OpcioVot.objects.count(), 3)

    def test_owner_cannot_create_votacio(self):
        client = auth_client(self.owner)
        response = client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_tenant_cannot_create_votacio(self):
        client = auth_client(self.tenant)
        response = client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_cannot_create_votacio(self):
        client = auth_client(self.outsider)
        response = client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_opcions_rejected(self):
        client = auth_client(self.admin)
        payload = {**self.payload, 'opcions': ['Sí', 'Sí']}
        response = client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_cannot_create(self):
        response = APIClient().post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class EmitreVotAPITest(TestCase):

    def setUp(self):
        self.admin = create_user('admin@test.com', role='admin')
        self.owner = create_user('owner@test.com', role='owner')
        self.tenant = create_user('tenant@test.com', role='tenant')
        self.outsider = create_user('outsider@test.com', role='owner')
        self.edifici = create_edifici(admin_user=self.admin)
        Habitatge.objects.create(
            edifici=self.edifici,
            referenciaCadastral='CAD001',
            planta='1',
            porta='A',
            superficie=60.0,
            usuari=self.owner,
            solicitant=self.owner,
        )
        Habitatge.objects.create(
            edifici=self.edifici,
            referenciaCadastral='CAD002',
            planta='2',
            porta='B',
            superficie=55.0,
            usuari=self.tenant,
            solicitant=self.tenant,
        )
        self.votacio = create_votacio(self.edifici, self.admin)
        self.opcio_si = self.votacio.opcions.get(text='Sí')
        self.opcio_no = self.votacio.opcions.get(text='No')
        self.url = reverse('votacio-votar', kwargs={'pk': self.votacio.pk})

    # --- Vot duplicat ---

    def test_member_can_vote(self):
        client = auth_client(self.owner)
        response = client.post(self.url, {'opcio_id': self.opcio_si.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Vot.objects.count(), 1)

    def test_duplicate_vote_rejected_by_api(self):
        """El segon vot del mateix usuari ha de retornar 400."""
        client = auth_client(self.owner)
        client.post(self.url, {'opcio_id': self.opcio_si.id}, format='json')
        response = client.post(self.url, {'opcio_id': self.opcio_no.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Vot.objects.count(), 1)

    def test_outsider_cannot_vote(self):
        client = auth_client(self.outsider)
        response = client.post(self.url, {'opcio_id': self.opcio_si.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_opcio_rejected(self):
        client = auth_client(self.owner)
        response = client.post(self.url, {'opcio_id': 9999}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_vote_on_closed_votacio_rejected(self):
        self.votacio.estat = 'tancada'
        self.votacio.save()
        client = auth_client(self.owner)
        response = client.post(self.url, {'opcio_id': self.opcio_si.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_vote(self):
        client = auth_client(self.admin)
        response = client.post(self.url, {'opcio_id': self.opcio_si.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_tenant_cannot_vote(self):
        client = auth_client(self.tenant)
        response = client.post(self.url, {'opcio_id': self.opcio_no.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ResultatsVotacioAPITest(TestCase):

    def setUp(self):
        self.admin = create_user('admin@test.com', role='admin')
        self.member = create_user('member@test.com', role='owner')
        self.outsider = create_user('outsider@test.com', role='owner')
        self.edifici = create_edifici(admin_user=self.admin)
        Habitatge.objects.create(
            edifici=self.edifici,
            referenciaCadastral='CAD001',
            planta='1',
            porta='A',
            superficie=60.0,
            usuari=self.member,
            solicitant=self.member,
        )
        self.votacio = create_votacio(self.edifici, self.admin)
        self.opcio_si = self.votacio.opcions.get(text='Sí')
        Vot.objects.create(votacio=self.votacio, opcio=self.opcio_si, usuari=self.admin)
        Vot.objects.create(votacio=self.votacio, opcio=self.opcio_si, usuari=self.member)
        self.url = reverse('votacio-resultats', kwargs={'pk': self.votacio.pk})

    def test_member_can_see_results(self):
        client = auth_client(self.member)
        response = client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['num_vots_total'], 2)

    def test_percentatge_calculat_correctament(self):
        client = auth_client(self.admin)
        response = client.get(self.url)
        opcions = {o['text']: o for o in response.data['opcions']}
        self.assertEqual(opcions['Sí']['num_vots'], 2)
        self.assertEqual(opcions['Sí']['percentatge'], 100.0)
        self.assertEqual(opcions['No']['num_vots'], 0)
        self.assertEqual(opcions['No']['percentatge'], 0.0)

    def test_outsider_cannot_see_results(self):
        client = auth_client(self.outsider)
        response = client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Tarea 5 — Edit and delete tests
# ---------------------------------------------------------------------------

class VotacioUpdateAPITest(TestCase):

    def setUp(self):
        self.admin = create_user('admin@test.com', role='admin')
        self.owner = create_user('owner@test.com', role='owner')
        self.tenant = create_user('tenant@test.com', role='tenant')
        self.outsider = create_user('outsider@test.com', role='owner')
        self.edifici = create_edifici(admin_user=self.admin)
        Habitatge.objects.create(
            edifici=self.edifici,
            referenciaCadastral='CAD001',
            planta='1',
            porta='A',
            superficie=60.0,
            usuari=self.owner,
            solicitant=self.owner,
        )
        Habitatge.objects.create(
            edifici=self.edifici,
            referenciaCadastral='CAD002',
            planta='2',
            porta='B',
            superficie=55.0,
            usuari=self.tenant,
            solicitant=self.tenant,
        )
        self.votacio = create_votacio(self.edifici, self.admin)
        self.url = reverse('votacio-detail', kwargs={'pk': self.votacio.pk})

    def test_admin_can_update_titol(self):
        client = auth_client(self.admin)
        response = client.patch(self.url, {'titol': 'Nou títol'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.votacio.refresh_from_db()
        self.assertEqual(self.votacio.titol, 'Nou títol')

    def test_owner_cannot_update_votacio(self):
        client = auth_client(self.owner)
        response = client.patch(self.url, {'descripcio': 'Nova descripció'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_tenant_cannot_update_votacio(self):
        client = auth_client(self.tenant)
        response = client.patch(self.url, {'titol': 'Intento'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_cannot_update_votacio(self):
        client = auth_client(self.outsider)
        response = client.patch(self.url, {'titol': 'Intento'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_close_votacio(self):
        client = auth_client(self.admin)
        response = client.patch(self.url, {'estat': 'tancada'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.votacio.refresh_from_db()
        self.assertEqual(self.votacio.estat, 'tancada')

    def test_cannot_reopen_cancelled_votacio(self):
        self.votacio.estat = 'cancel·lada'
        self.votacio.save()
        client = auth_client(self.admin)
        response = client.patch(self.url, {'estat': 'oberta'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_returns_full_detail(self):
        client = auth_client(self.admin)
        response = client.patch(self.url, {'titol': 'Actualitzada'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('opcions', response.data)
        self.assertIn('ha_votat', response.data)


class VotacioDeleteAPITest(TestCase):

    def setUp(self):
        self.admin = create_user('admin@test.com', role='admin')
        self.owner = create_user('owner@test.com', role='owner')
        self.tenant = create_user('tenant@test.com', role='tenant')
        self.outsider = create_user('outsider@test.com', role='owner')
        self.edifici = create_edifici(admin_user=self.admin)
        Habitatge.objects.create(
            edifici=self.edifici,
            referenciaCadastral='CAD001',
            planta='1',
            porta='A',
            superficie=60.0,
            usuari=self.owner,
            solicitant=self.owner,
        )
        Habitatge.objects.create(
            edifici=self.edifici,
            referenciaCadastral='CAD002',
            planta='2',
            porta='B',
            superficie=55.0,
            usuari=self.tenant,
            solicitant=self.tenant,
        )

    def _fresh_votacio(self):
        return create_votacio(self.edifici, self.admin)

    def test_admin_can_delete_votacio(self):
        v = self._fresh_votacio()
        client = auth_client(self.admin)
        response = client.delete(reverse('votacio-detail', kwargs={'pk': v.pk}))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Votacio.objects.count(), 0)

    def test_owner_cannot_delete_votacio(self):
        v = self._fresh_votacio()
        client = auth_client(self.owner)
        response = client.delete(reverse('votacio-detail', kwargs={'pk': v.pk}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Votacio.objects.count(), 1)

    def test_tenant_cannot_delete_votacio(self):
        v = self._fresh_votacio()
        client = auth_client(self.tenant)
        response = client.delete(reverse('votacio-detail', kwargs={'pk': v.pk}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Votacio.objects.count(), 1)

    def test_outsider_cannot_delete_votacio(self):
        v = self._fresh_votacio()
        client = auth_client(self.outsider)
        response = client.delete(reverse('votacio-detail', kwargs={'pk': v.pk}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_cascades_votes_and_options(self):
        v = self._fresh_votacio()
        opcio = v.opcions.first()
        Vot.objects.create(votacio=v, opcio=opcio, usuari=self.admin)
        client = auth_client(self.admin)
        client.delete(reverse('votacio-detail', kwargs={'pk': v.pk}))
        self.assertEqual(Vot.objects.count(), 0)
        self.assertEqual(OpcioVot.objects.count(), 0)
