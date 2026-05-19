from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .middleware import AuditMiddleware
from .models import AuditLog

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_middleware():
    return AuditMiddleware(get_response=lambda r: r)


def _auth_header(user):
    token = RefreshToken.for_user(user).access_token
    return {'HTTP_AUTHORIZATION': f'Bearer {token}'}


# ---------------------------------------------------------------------------
# Unit tests: normalització de paths (sense BD)
# ---------------------------------------------------------------------------

class ParsePathTests(TestCase):
    def setUp(self):
        self.mw = _get_middleware()

    def test_integer_id_normalized(self):
        normalized, _, _ = self.mw._parse_path('/api/buildings/123/')
        self.assertEqual(normalized, '/api/buildings/:id/')

    def test_uuid_normalized(self):
        normalized, _, _ = self.mw._parse_path(
            '/api/accounts/550e8400-e29b-41d4-a716-446655440000/'
        )
        self.assertEqual(normalized, '/api/accounts/:id/')

    def test_multiple_ids_normalized(self):
        normalized, _, resource_id = self.mw._parse_path('/api/buildings/42/millores/7/')
        self.assertEqual(normalized, '/api/buildings/:id/millores/:id/')
        self.assertEqual(resource_id, '7')

    def test_no_id_unchanged(self):
        normalized, resource_type, resource_id = self.mw._parse_path('/api/buildings/')
        self.assertEqual(normalized, '/api/buildings/')
        self.assertEqual(resource_type, 'buildings')
        self.assertEqual(resource_id, '')

    def test_resource_type_extracted(self):
        _, resource_type, _ = self.mw._parse_path('/api/verification/123/')
        self.assertEqual(resource_type, 'verification')

    def test_resource_id_is_raw_value(self):
        _, _, resource_id = self.mw._parse_path('/api/buildings/99/')
        self.assertEqual(resource_id, '99')


# ---------------------------------------------------------------------------
# Integration tests: endpoint GET /api/audit/logs/
# ---------------------------------------------------------------------------

class AuditLogListViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            email='admin@test.com',
            password='Password123',
        )
        cls.user = User.objects.create_user(
            email='user@test.com',
            password='Password123',
        )
        cls.url = reverse('audit-log-list')

        AuditLog.objects.create(
            user=cls.admin,
            method='GET',
            endpoint='/api/buildings/',
            resource_type='buildings',
            resource_id='',
            status_code=200,
            ip_address='127.0.0.1',
            duration_ms=10,
        )
        AuditLog.objects.create(
            user=cls.user,
            method='DELETE',
            endpoint='/api/buildings/:id/',
            resource_type='buildings',
            resource_id='5',
            status_code=403,
            ip_address='10.0.0.1',
            duration_ms=20,
        )
        AuditLog.objects.create(
            user=cls.user,
            method='POST',
            endpoint='/api/accounts/',
            resource_type='accounts',
            resource_id='',
            status_code=201,
            ip_address='10.0.0.1',
            duration_ms=30,
        )

    # --- Permisos ---

    def test_unauthenticated_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_user_returns_403(self):
        self.client.credentials(**_auth_header(self.user))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_returns_200(self):
        self.client.credentials(**_auth_header(self.admin))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_response_includes_user_email(self):
        self.client.credentials(**_auth_header(self.admin))
        response = self.client.get(self.url)
        emails = [r['user_email'] for r in response.data['results']]
        self.assertIn('admin@test.com', emails)

    # --- Filtres ---

    def test_filter_by_method(self):
        self.client.credentials(**_auth_header(self.admin))
        response = self.client.get(self.url, {'method': 'DELETE'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(all(r['method'] == 'DELETE' for r in response.data['results']))

    def test_filter_by_resource_type(self):
        self.client.credentials(**_auth_header(self.admin))
        response = self.client.get(self.url, {'resource_type': 'accounts'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(all(r['resource_type'] == 'accounts' for r in response.data['results']))

    def test_filter_by_status_code(self):
        self.client.credentials(**_auth_header(self.admin))
        response = self.client.get(self.url, {'status_code': 403})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(all(r['status_code'] == 403 for r in response.data['results']))

    def test_filter_by_user_id(self):
        self.client.credentials(**_auth_header(self.admin))
        response = self.client.get(self.url, {'user_id': self.user.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(all(r['user'] == self.user.pk for r in response.data['results']))

    def test_filter_by_date_range(self):
        self.client.credentials(**_auth_header(self.admin))
        today = timezone.now().date().isoformat()
        response = self.client.get(self.url, {'from_date': today, 'to_date': today})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
