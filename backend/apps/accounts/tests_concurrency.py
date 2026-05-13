"""
Tests de concurrència per a apps.accounts.

Cubre escenarios donde varias requests simultànies ataquen el mateix recurs
i han de quedar resoltes amb respostes controlades (201/200/400), mai amb 500.

Convencions:
- TransactionTestCase: els workers de cada fil veuen els commits reals a BD.
- threading.Barrier: sincronitza l'inici exacte de totes les requests.
- subTest(): s'usa NOMÉS on hi ha variació funcional real (pre_sessions).
- @tag('concurrency'): exclou d'un CI ràpid amb --exclude-tag=concurrency.
"""

import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.db import connections
from django.test import TransactionTestCase, tag
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Profile, RoleChoices, TokenLoginLog
from apps.accounts.views import RegisterView, LoginView, MeView
from apps.tests_concurrency_utils import _run_workers


User = get_user_model()


# ---------------------------------------------------------------------------
# 1. Registre: race condition amb UNIQUE email
# ---------------------------------------------------------------------------

@tag('concurrency')
class StrictConcurrencyRegistrationTests(TransactionTestCase):
    """
    6 workers intenten registrar el mateix email simultàniament.
    Exactament 1 × 201, 5 × 400, mai 500.
    """

    def setUp(self):
        cache.clear()

    def test_parallel_register_same_email_never_returns_500(self):
        workers = 6
        email = "strict-reg-concurrent@example.com"
        password = "Gihistzzz_2026"
        url = reverse("register")
        payload = {
            "email": email,
            "first_name": "Strict",
            "last_name": "Concurrency",
            "password": password,
            "password_confirm": password,
        }

        statuses, errors = [], []

        def worker(barrier, lock, _):
            client = APIClient()
            client.raise_request_exception = False
            try:
                barrier.wait(timeout=5)
                r = client.post(url, payload, format="json")
                with lock:
                    statuses.append(r.status_code)
            except Exception as exc:
                with lock:
                    errors.append(str(exc))
            finally:
                connections.close_all()

        with patch.object(RegisterView, 'throttle_classes', []):
            threads = _run_workers(worker, workers)

        self.assertFalse(any(t.is_alive() for t in threads), "Threads did not finish")
        self.assertEqual(errors, [], "Unexpected errors")
        self.assertEqual(len(statuses), workers)

        self.assertEqual(statuses.count(status.HTTP_201_CREATED), 1,
                         f"Expected exactly 1 registration, got: {statuses}")
        self.assertEqual(statuses.count(status.HTTP_500_INTERNAL_SERVER_ERROR), 0,
                         f"500 detected: {statuses}")
        self.assertEqual(User.objects.filter(email=email).count(), 1)
        self.assertEqual(Profile.objects.filter(user__email=email).count(), 1)


# ---------------------------------------------------------------------------
# 2. Login: race condition amb el límit de sessions actives
# ---------------------------------------------------------------------------

@tag('concurrency')
class StrictConcurrencyLoginSessionLimitTests(TransactionTestCase):
    """
    6 logins simultanis del mateix usuari mai han de superar max_sessions=5.

    Parametritzat per pre_sessions per cobrir els estats de frontera:
    - 0: arrencada en net (tots creen, cap revoca)
    - 4: un pas abans del límit (alguns han de revocar)
    - 5: ja al límit (tots han de revocar una sessió prèvia)
    """

    MAX_SESSIONS = 5
    WORKERS = 6
    CASES = [0, 4, 5]

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="concurrent-login@example.com",
            password="Gihistzzz_2026",
            first_name="Login",
            last_name="Concurrency",
        )

    def test_parallel_logins_never_exceed_session_limit(self):
        url = reverse("login")
        payload = {"email": "concurrent-login@example.com", "password": "Gihistzzz_2026"}

        for pre_sessions in self.CASES:
            with self.subTest(pre_sessions=pre_sessions):
                TokenLoginLog.objects.filter(user=self.user).delete()
                for _ in range(pre_sessions):
                    TokenLoginLog.objects.create(
                        user=self.user,
                        status=TokenLoginLog.LOGIN,
                        expires_at=timezone.now(),
                        jti=str(uuid.uuid4()),
                    )

                statuses, errors = [], []

                def worker(barrier, lock, _):
                    client = APIClient()
                    client.raise_request_exception = False
                    try:
                        barrier.wait(timeout=5)
                        r = client.post(url, payload, format="json")
                        with lock:
                            statuses.append(r.status_code)
                    except Exception as exc:
                        with lock:
                            errors.append(str(exc))
                    finally:
                        connections.close_all()

                with patch.object(LoginView, 'throttle_classes', []):
                    threads = _run_workers(worker, self.WORKERS)

                self.assertFalse(any(t.is_alive() for t in threads),
                                 f"[pre={pre_sessions}] Threads did not finish")
                self.assertEqual(errors, [],
                                 f"[pre={pre_sessions}] Unexpected errors")
                self.assertEqual(len(statuses), self.WORKERS)

                self.assertEqual(statuses.count(status.HTTP_500_INTERNAL_SERVER_ERROR), 0,
                                 f"[pre={pre_sessions}] 500 detected: {statuses}")
                self.assertTrue(all(s == status.HTTP_200_OK for s in statuses),
                                f"[pre={pre_sessions}] Expected all 200, got: {statuses}")

                active_count = TokenLoginLog.objects.filter(
                    user=self.user,
                    status=TokenLoginLog.LOGIN,
                    logout_at__isnull=True,
                ).count()
                self.assertLessEqual(
                    active_count,
                    self.MAX_SESSIONS,
                    f"[pre={pre_sessions}] Limit exceeded: "
                    f"{active_count} active sessions (max {self.MAX_SESSIONS})",
                )


# ---------------------------------------------------------------------------
# 3. Actualització d'email: race condition amb UNIQUE email
# ---------------------------------------------------------------------------

@tag('concurrency')
class StrictConcurrencyAccountEmailUpdateTests(TransactionTestCase):
    """
    4 usuaris intenten canviar el seu email al mateix valor simultàniament.
    Exactament 1 × 200, 3 × 400, mai 500.
    """

    def setUp(self):
        cache.clear()

    def test_parallel_account_email_update_never_returns_500(self):
        workers = 4
        target_email = "shared-target-concurrent@example.com"

        users = [
            User.objects.create_user(
                email=f"origin-upd-{i}@example.com",
                password="Gihistzzz_2026",
                first_name=f"User{i}",
                last_name="Concurrency",
            )
            for i in range(workers)
        ]

        statuses, errors = [], []

        def worker(barrier, lock, idx):
            client = APIClient()
            client.raise_request_exception = False
            client.force_authenticate(user=users[idx])
            try:
                barrier.wait(timeout=5)
                r = client.patch(reverse("me"), {"email": target_email}, format="json")
                with lock:
                    statuses.append(r.status_code)
            except Exception as exc:
                with lock:
                    errors.append(str(exc))
            finally:
                connections.close_all()

        with patch.object(MeView, 'throttle_classes', []):
            threads = _run_workers(worker, workers)

        self.assertFalse(any(t.is_alive() for t in threads), "Threads did not finish")
        self.assertEqual(errors, [], "Unexpected errors")
        self.assertEqual(len(statuses), workers)

        self.assertEqual(statuses.count(status.HTTP_500_INTERNAL_SERVER_ERROR), 0,
                         f"500 detected: {statuses}")
        self.assertEqual(statuses.count(status.HTTP_200_OK), 1,
                         f"Expected exactly 1 success: {statuses}")
        self.assertEqual(statuses.count(status.HTTP_400_BAD_REQUEST), workers - 1,
                         f"Expected {workers - 1} conflicts: {statuses}")
        self.assertEqual(User.objects.filter(email=target_email).count(), 1)
