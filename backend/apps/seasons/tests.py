from datetime import date

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model

from .models import Temporada, EstatTemporada

User = get_user_model()

SEASON_DATA = {
    'nom': 'Temporada Test',
    'dataInici': date(2026, 1, 1),
    'dataFi': date(2026, 12, 31),
}


def make_superuser(email='super@example.com'):
    return User.objects.create_superuser(email=email, password='Password123')


def make_user(email='user@example.com'):
    return User.objects.create_user(email=email, password='Password123', first_name='User')


class EstatTemporadaManagerTest(TestCase):
    """Tests unitaris del SeasonManager."""

    def setUp(self):
        self.temporada = Temporada.objects.create(**SEASON_DATA)

    def test_temporada_creada_en_estat_pendent(self):
        self.assertEqual(self.temporada.estat, EstatTemporada.PENDENT)
        self.assertFalse(self.temporada.activa)

    def test_iniciar_temporada_pendent(self):
        Temporada.objects.iniciar(self.temporada)
        self.temporada.refresh_from_db()
        self.assertEqual(self.temporada.estat, EstatTemporada.ACTIVA)
        self.assertTrue(self.temporada.activa)

    def test_iniciar_temporada_activa_falla(self):
        Temporada.objects.iniciar(self.temporada)
        with self.assertRaises(ValueError):
            Temporada.objects.iniciar(self.temporada)

    def test_iniciar_temporada_tancada_falla(self):
        Temporada.objects.iniciar(self.temporada)
        Temporada.objects.tancar(self.temporada)
        with self.assertRaises(ValueError):
            Temporada.objects.iniciar(self.temporada)

    def test_iniciar_quan_ja_existeix_activa_falla(self):
        Temporada.objects.iniciar(self.temporada)
        altra = Temporada.objects.create(
            nom='Altra temporada', dataInici='2027-01-01', dataFi='2027-12-31'
        )
        with self.assertRaises(ValueError):
            Temporada.objects.iniciar(altra)

    def test_tancar_temporada_activa(self):
        Temporada.objects.iniciar(self.temporada)
        Temporada.objects.tancar(self.temporada)
        self.temporada.refresh_from_db()
        self.assertEqual(self.temporada.estat, EstatTemporada.TANCADA)
        self.assertFalse(self.temporada.activa)

    def test_tancar_temporada_pendent_falla(self):
        with self.assertRaises(ValueError):
            Temporada.objects.tancar(self.temporada)

    def test_tancar_temporada_tancada_falla(self):
        Temporada.objects.iniciar(self.temporada)
        Temporada.objects.tancar(self.temporada)
        with self.assertRaises(ValueError):
            Temporada.objects.tancar(self.temporada)

    def test_is_active_temporada_activa_dins_rang(self):
        Temporada.objects.iniciar(self.temporada)
        self.assertTrue(Temporada.objects.is_active(self.temporada))

    def test_is_active_temporada_pendent(self):
        self.assertFalse(Temporada.objects.is_active(self.temporada))

    def test_is_active_temporada_tancada(self):
        Temporada.objects.iniciar(self.temporada)
        Temporada.objects.tancar(self.temporada)
        self.assertFalse(Temporada.objects.is_active(self.temporada))


class TemporadaAPITest(APITestCase):
    """Tests dels endpoints REST de temporades."""

    def setUp(self):
        self.client = APIClient()
        self.admin = make_superuser()
        self.user = make_user()
        self.temporada = Temporada.objects.create(**SEASON_DATA)

    # --- Creació ---

    def test_admin_pot_crear_temporada(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/seasons/', {
            'nom': 'Nova temporada',
            'dataInici': '2027-01-01',
            'dataFi': '2027-12-31',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['estat'], EstatTemporada.PENDENT)

    def test_usuari_no_admin_no_pot_crear_temporada(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/seasons/', {
            'nom': 'Nova temporada',
            'dataInici': '2027-01-01',
            'dataFi': '2027-12-31',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_autenticat_no_pot_crear_temporada(self):
        response = self.client.post('/api/seasons/', {
            'nom': 'Nova temporada',
            'dataInici': '2027-01-01',
            'dataFi': '2027-12-31',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- Llistat i detall (autenticats) ---

    def test_usuari_autenticat_pot_llistar_temporades(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/seasons/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_usuari_autenticat_pot_veure_detall(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'/api/seasons/{self.temporada.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('estat', response.data)
        self.assertIn('activa', response.data)

    # --- Iniciar ---

    def test_admin_pot_iniciar_temporada_pendent(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['estat'], EstatTemporada.ACTIVA)
        self.assertTrue(response.data['activa'])

    def test_iniciar_temporada_activa_retorna_400(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_iniciar_temporada_tancada_retorna_400(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.client.post(f'/api/seasons/{self.temporada.pk}/tancar/')
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_iniciar_quan_ja_hi_ha_activa_retorna_400(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        altra = Temporada.objects.create(
            nom='Altra temporada', dataInici='2027-01-01', dataFi='2027-12-31'
        )
        response = self.client.post(f'/api/seasons/{altra.pk}/iniciar/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_usuari_no_admin_no_pot_iniciar(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # --- Tancar ---

    def test_admin_pot_tancar_temporada_activa(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/tancar/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['estat'], EstatTemporada.TANCADA)
        self.assertFalse(response.data['activa'])

    def test_tancar_temporada_pendent_retorna_400(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/tancar/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_tancar_temporada_tancada_retorna_400(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.client.post(f'/api/seasons/{self.temporada.pk}/tancar/')
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/tancar/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_usuari_no_admin_no_pot_tancar(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.client.force_authenticate(user=self.user)
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/tancar/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
