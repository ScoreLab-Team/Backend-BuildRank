"""
Tests de concurrència per a apps.buildings.

Cubre escenarios donde varias requests simultànies ataquen el mateix recurs
i han de quedar resoltes amb respostes controlades (201/200/400), mai amb 500.

Convencions:
- TransactionTestCase: els workers de cada fil veuen els commits reals a BD.
- threading.Barrier: sincronitza l'inici exacte de totes les requests.
- subTest(): parametritza casos (workers, usuaris concurrents) sense repetir codi.
- @tag('concurrency'): exclou d'un CI ràpid amb --exclude-tag=concurrency.
"""

from django.core.cache import cache
from django.db import connections
from django.test import TransactionTestCase, tag
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import RoleChoices
from apps.buildings.models import (
    Edifici,
    EstatValidacio,
    GrupComparable,
    Habitatge,
    Localitzacio,
)
from apps.tests_concurrency_utils import _run_workers


User = get_user_model()

HABITATGES_URL = "/api/buildings/habitatges/"


def _make_edifici():
    """Crea i retorna un Edifici mínim amb les seves dependències."""
    grup = GrupComparable.objects.create(
        idGrup=1,
        zonaClimatica="C2",
        tipologia="Residencial",
        rangSuperficie="0-100",
    )
    localitzacio = Localitzacio.objects.create(
        carrer="Carrer test",
        numero=1,
        codiPostal="08001",
        barri="Centre",
        latitud=41.0,
        longitud=2.0,
        zonaClimatica="C2",
    )
    return Edifici.objects.create(
        anyConstruccio=2000,
        tipologia="Residencial",
        superficieTotal=400,
        reglament="CTE",
        orientacioPrincipal="Sud",
        localitzacio=localitzacio,
        grupComparable=grup,
    )


# ---------------------------------------------------------------------------
# 1. Creació d'Habitatge: race condition amb PRIMARY KEY UNIQUE
# ---------------------------------------------------------------------------

@tag('concurrency')
class StrictConcurrencyHabitatgeCreateTests(TransactionTestCase):
    """
    Diverses requests intenten crear un Habitatge amb la mateixa referenciaCadastral
    simultàniament. Mai ha de retornar 500.
    Parametritzat per nombre de workers: [4, 8, 16].
    """

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(
            email="concurrency-habitatge-owner@example.com",
            password="Gihistzzz_2026",
            first_name="Owner",
            last_name="Concurrency",
        )
        self.owner.profile.role = RoleChoices.OWNER
        self.owner.profile.save(update_fields=["role"])
        self.edifici = _make_edifici()

    def test_parallel_habitatge_create_same_ref_cadastral_never_returns_500(self):
        for workers in [4, 8, 16]:
            with self.subTest(workers=workers):
                # Referència única per iteració → no cal neteja entre subtests
                ref = f"REF{workers:04d}ABCDE0001"

                statuses, errors = [], []

                def worker(barrier, lock, _):
                    client = APIClient()
                    client.raise_request_exception = False
                    client.force_authenticate(user=self.owner)
                    payload = {
                        "referenciaCadastral": ref,
                        "planta": "1",
                        "porta": "A",
                        "superficie": 75.0,
                        "edifici": self.edifici.idEdifici,
                    }
                    try:
                        barrier.wait(timeout=5)
                        r = client.post(HABITATGES_URL, payload, format="json")
                        with lock:
                            statuses.append(r.status_code)
                    except Exception as exc:
                        with lock:
                            errors.append(str(exc))
                    finally:
                        connections.close_all()

                threads = _run_workers(worker, workers)

                self.assertFalse(any(t.is_alive() for t in threads),
                                 f"[workers={workers}] Threads did not finish")
                self.assertEqual(errors, [], f"[workers={workers}] Unexpected errors")
                self.assertEqual(len(statuses), workers)

                self.assertEqual(statuses.count(status.HTTP_500_INTERNAL_SERVER_ERROR), 0,
                                 f"[workers={workers}] 500 detected: {statuses}")
                self.assertEqual(statuses.count(status.HTTP_201_CREATED), 1,
                                 f"[workers={workers}] Expected exactly 1 creation: {statuses}")
                self.assertEqual(statuses.count(status.HTTP_400_BAD_REQUEST), workers - 1,
                                 f"[workers={workers}] Expected {workers-1} conflicts: {statuses}")
                self.assertEqual(
                    Habitatge.objects.filter(referenciaCadastral=ref).count(), 1,
                    f"[workers={workers}] Expected 1 row in DB",
                )


# ---------------------------------------------------------------------------
# 2. Sol·licitud d'accés: race condition en patró check-then-write
# ---------------------------------------------------------------------------

@tag('concurrency')
class StrictConcurrencySolicitarAccesTests(TransactionTestCase):
    """
    N usuaris sol·liciten accés al mateix habitatge simultàniament.
    La view comprova `if habitatge.usuari:` i després guarda `solicitant`.
    Sota concurrència, tots passen la comprovació (usuari=None).
    Cap ha de retornar 500; last-writer-wins en solicitant és comportament esperat.
    Parametritzat per nombre d'usuaris concurrents: [2, 4, 6].
    """

    def setUp(self):
        cache.clear()
        self.edifici = _make_edifici()
        self.habitatge = Habitatge.objects.create(
            referenciaCadastral="SOLICIT0001ABCDE",
            planta="1",
            porta="A",
            superficie=80.0,
            edifici=self.edifici,
            estatValidacio=EstatValidacio.PENDENT_DOCUMENTACIO,
        )

    def test_parallel_solicitar_acces_never_returns_500(self):
        url = f"{HABITATGES_URL}{self.habitatge.referenciaCadastral}/solicitar-acces/"

        for concurrent_users in [2, 4, 6]:
            with self.subTest(concurrent_users=concurrent_users):
                # Usuaris frescos per a cada iteració
                users = [
                    User.objects.create_user(
                        email=f"sol-{concurrent_users}u-{i}@example.com",
                        password="Gihistzzz_2026",
                        first_name=f"Sol{i}",
                        last_name="Concurrency",
                    )
                    for i in range(concurrent_users)
                ]

                statuses, errors = [], []

                def worker(barrier, lock, idx):
                    client = APIClient()
                    client.raise_request_exception = False
                    client.force_authenticate(user=users[idx])
                    try:
                        barrier.wait(timeout=5)
                        r = client.post(url, format="json")
                        with lock:
                            statuses.append(r.status_code)
                    except Exception as exc:
                        with lock:
                            errors.append(str(exc))
                    finally:
                        connections.close_all()

                threads = _run_workers(worker, concurrent_users)

                self.assertFalse(any(t.is_alive() for t in threads),
                                 f"[users={concurrent_users}] Threads did not finish")
                self.assertEqual(errors, [], f"[users={concurrent_users}] Unexpected errors")
                self.assertEqual(len(statuses), concurrent_users)

                self.assertEqual(statuses.count(status.HTTP_500_INTERNAL_SERVER_ERROR), 0,
                                 f"[users={concurrent_users}] 500 detected: {statuses}")

                self.habitatge.refresh_from_db()
                self.assertIn(self.habitatge.solicitant, users,
                              f"[users={concurrent_users}] solicitant not in the expected set")

                # Neteja entre iteracions
                self.habitatge.solicitant = None
                self.habitatge.estatValidacio = EstatValidacio.PENDENT_DOCUMENTACIO
                self.habitatge.save(update_fields=["solicitant", "estatValidacio"])
                User.objects.filter(pk__in=[u.pk for u in users]).delete()


# ---------------------------------------------------------------------------
# 3. Assignació de resident: race condition en last-writer-wins
# ---------------------------------------------------------------------------

@tag('concurrency')
class StrictConcurrencyResidentAssignmentTests(TransactionTestCase):
    """
    Un administrador assigna N residents diferents al mateix habitatge simultàniament.
    Cap ha de retornar 500; exactament un resident queda assignat (last-writer-wins).
    Parametritzat per nombre de workers: [2, 4].
    """

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            email="concurrent-admin@example.com",
            password="Gihistzzz_2026",
            first_name="Admin",
            last_name="Concurrency",
        )
        self.admin.profile.role = RoleChoices.ADMIN
        self.admin.profile.save(update_fields=["role"])

        self.edifici = _make_edifici()
        self.edifici.administradorFinca = self.admin
        self.edifici.save(update_fields=["administradorFinca"])

        self.habitatge = Habitatge.objects.create(
            referenciaCadastral="ASSIGN0001ABCDE",
            planta="2",
            porta="B",
            superficie=65.0,
            edifici=self.edifici,
            estatValidacio=EstatValidacio.PENDENT_DOCUMENTACIO,
        )

        # Crea el màxim de residents que necessitarem (workers=4)
        self.residents = [
            User.objects.create_user(
                email=f"resident-{i}@example.com",
                password="Gihistzzz_2026",
                first_name=f"Resident{i}",
                last_name="Concurrency",
            )
            for i in range(4)
        ]

    def test_parallel_resident_assignment_never_returns_500(self):
        url = reverse("assignar-resident",
                      kwargs={"ref_cadastral": self.habitatge.referenciaCadastral})

        for workers in [2, 4]:
            with self.subTest(workers=workers):
                residents = self.residents[:workers]
                statuses, errors = [], []

                def worker(barrier, lock, idx):
                    client = APIClient()
                    client.raise_request_exception = False
                    client.force_authenticate(user=self.admin)
                    payload = {"user_id": residents[idx].pk}
                    try:
                        barrier.wait(timeout=5)
                        r = client.patch(url, payload, format="json")
                        with lock:
                            statuses.append(r.status_code)
                    except Exception as exc:
                        with lock:
                            errors.append(str(exc))
                    finally:
                        connections.close_all()

                threads = _run_workers(worker, workers)

                self.assertFalse(any(t.is_alive() for t in threads),
                                 f"[workers={workers}] Threads did not finish")
                self.assertEqual(errors, [], f"[workers={workers}] Unexpected errors")
                self.assertEqual(len(statuses), workers)

                self.assertEqual(statuses.count(status.HTTP_500_INTERNAL_SERVER_ERROR), 0,
                                 f"[workers={workers}] 500 detected: {statuses}")
                self.assertTrue(all(s == status.HTTP_200_OK for s in statuses),
                                f"[workers={workers}] Expected all 200, got: {statuses}")

                self.habitatge.refresh_from_db()
                self.assertIn(self.habitatge.usuari, residents,
                              f"[workers={workers}] Final resident not in expected set")

                # Neteja entre iteracions: desassigna el resident
                self.habitatge.usuari = None
                self.habitatge.save(update_fields=["usuari"])
