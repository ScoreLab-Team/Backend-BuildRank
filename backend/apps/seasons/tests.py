from django.test import TestCase
from rest_framework.test import APIClient, APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils.timezone import now

from apps.seasons.models import Temporada
from apps.accounts.models import RoleChoices

User = get_user_model()

class SeasonManagerTest(APITestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="admin@example.com",
            password="Password123",
            first_name="Test"
        )
        self.user.profile.role = RoleChoices.ADMIN
        self.user.profile.save()

        self.client.force_authenticate(user=self.user)

        self.temporada = Temporada.objects.create(
            nom="Season",
            dataInici="2026-01-01",
            dataFi="2026-12-31",
            activa=False
        )

    def test_create_season(self):
        t = Temporada.objects.create_season(
            id_temporada=2,
            nom="New Season",
            dataInici="2026-01-01",
            dataFi="2026-12-31"
        )

        self.assertFalse(t.activa)
        self.assertEqual(t.nom, "New Season")

    def test_activate_season(self):
        Temporada.objects.activate(self.temporada)

        self.temporada.refresh_from_db()
        self.assertTrue(self.temporada.activa)

    def test_deactivate_season(self):
        self.temporada.activa = True
        self.temporada.save()

        Temporada.objects.deactivate(self.temporada)

        self.temporada.refresh_from_db()
        self.assertFalse(self.temporada.activa)

    def test_is_active_true(self):
        today = now().date()

        t = Temporada.objects.create(
            nom="Active Season",
            dataInici=today,
            dataFi=today,
            activa=True
        )

        self.assertTrue(Temporada.objects.is_active(t))

    def test_is_active_false(self):
        today = now().date()

        t = Temporada.objects.create(
            nom="Inactive Season",
            dataInici=today,
            dataFi=today,
            activa=False
        )

        self.assertFalse(Temporada.objects.is_active(t))

    def test_activate_endpoint(self):
        url = f"/api/seasons/{self.temporada.pk}/activar/"

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.temporada.refresh_from_db()
        self.assertTrue(self.temporada.activa)

    def test_deactivate_endpoint(self):
        self.temporada.activa = True
        self.temporada.save()

        url = f"/api/seasons/{self.temporada.pk}/desactivar/"

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.temporada.refresh_from_db()
        self.assertFalse(self.temporada.activa)