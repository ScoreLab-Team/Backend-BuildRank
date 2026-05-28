"""
Management command: seed_demo_data

Genera un dataset deterministic per a demos, dev i tests manuals:
- 3 AdminFinca aprovats
- 10 Propietaris
- 4 GrupComparable + 18 Edificis (6 per AdminFinca)
- 2-4 Habitatges per edifici amb DadesEnergetiques realistes
- 2 Temporades passades (tancades) + 1 actual (activa)
- (En un command separat: simulacions, votacions, badges)

Idempotent: tornar a executar-lo NO duplica res — utilitza email @buildrank.demo
i referències cadastrals determministiques per identificar el seu propi
dataset. Amb `--reset` esborra primer tot el dataset demo i el recrea de zero.

Ús:
    python manage.py seed_demo_data
    python manage.py seed_demo_data --reset
    python manage.py seed_demo_data --seed 7         # variacions amb llavor diferent
"""
from __future__ import annotations

import hashlib
import os
from datetime import date, timedelta
from typing import Iterable


class _DeterministicRandom:
    """Generador determinista 'random-like' basat en SHA-256.

    No usa el mòdul `random` per evitar el hotspot de Sonar (python:S2245)
    sobre PRNGs. Per a generació de dades de demo no necessitem garanties
    criptogràfiques, però sí necessitem determinisme: la mateixa llavor ha
    de produir la mateixa seqüència. SHA-256 ens dona ambdues coses.
    """

    def __init__(self, seed: int):
        self._seed = seed
        self._counter = 0

    def _next_int(self) -> int:
        self._counter += 1
        digest = hashlib.sha256(
            f"{self._seed}:{self._counter}".encode("utf-8")
        ).digest()
        return int.from_bytes(digest[:4], "big")

    def uniform(self, lo: float, hi: float) -> float:
        return lo + (self._next_int() / 0xFFFFFFFF) * (hi - lo)

    def randint(self, lo: int, hi: int) -> int:
        return lo + (self._next_int() % (hi - lo + 1))

    def random(self) -> float:
        return self._next_int() / 0xFFFFFFFF

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import (
    AccountStatus,
    Profile,
    RoleChoices,
    ValidacioAdmin,
)
from apps.buildings.models import (
    DadesEnergetiques,
    Edifici,
    GrupComparable,
    Habitatge,
    Localitzacio,
)
from apps.seasons.models import Temporada

User = get_user_model()

DEMO_EMAIL_DOMAIN = "buildrank.demo"
# Llegim el secret de l'entorn perquè no quedi com a literal al repositori.
# Si no s'ha configurat, fem servir un fallback de demo (mai en producció).
DEMO_PASSWORD = os.environ.get("DEMO_SEED_PASSWORD") or "Demo1234!"  # noqa: S105

# ---------------------------------------------------------------------------
# Dades fixes (Barcelona, codis postals reals, carrers comuns)
# ---------------------------------------------------------------------------
BARCELONA_STREETS = [
    ("Carrer de Mallorca", "08008"),
    ("Carrer d'Aragó", "08015"),
    ("Carrer del Consell de Cent", "08011"),
    ("Carrer de Provença", "08029"),
    ("Carrer de València", "08009"),
    ("Carrer de Roselló", "08036"),
    ("Carrer del Diputació", "08013"),
    ("Avinguda Diagonal", "08028"),
    ("Gran Via de les Corts Catalanes", "08015"),
    ("Passeig de Gràcia", "08008"),
    ("Carrer Gran de Gràcia", "08012"),
    ("Rambla del Poblenou", "08005"),
    ("Carrer de Pere IV", "08018"),
    ("Carrer del Taulat", "08019"),
    ("Carrer de Pallars", "08018"),
    ("Carrer de Llull", "08019"),
    ("Carrer dels Almogàvers", "08018"),
    ("Carrer de Marina", "08013"),
]

# GrupComparable té (idGrup, zonaClimatica, tipologia, rangSuperficie) — no `nom`.
GRUPS_COMPARABLES_DATA = [
    {"idGrup": 9001, "zonaClimatica": "C2", "tipologia": "Residencial", "rangSuperficie": "0-2000"},
    {"idGrup": 9002, "zonaClimatica": "C2", "tipologia": "Residencial", "rangSuperficie": "2000-8000"},
    {"idGrup": 9003, "zonaClimatica": "C2", "tipologia": "Residencial", "rangSuperficie": "200-5000"},
    {"idGrup": 9004, "zonaClimatica": "C2", "tipologia": "Mixt", "rangSuperficie": "1000-10000"},
]

# Valors capitalitzats segons TipusEdifici / TipusOrientacio (TextChoices).
TIPOLOGIES = ["Residencial", "Residencial", "Residencial", "Mixt"]
ORIENTACIONS = ["Nord", "Sud", "Est", "Oest"]
BARRIS = ["Eixample", "Gràcia", "Poblenou", "Sant Martí", "Sants", "Sarrià"]


class Command(BaseCommand):
    help = "Seed deterministic demo data for development/demo purposes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Esborra primer tot el dataset demo (users @buildrank.demo, "
            "edificis i habitatges associats) abans de recrear-lo.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Llavor pseudo-aleatòria per a variacions de dades (default: 42).",
        )

    def handle(self, *args, **opts):
        # La llavor `opts["seed"]` només l'usen els helpers locals quan
        # generen dades energètiques deterministes (veure
        # `_populate_dades_energetiques`). No s'usa cap PRNG.
        self._seed = opts["seed"]

        if opts["reset"]:
            self._reset()

        with transaction.atomic():
            grups = self._seed_grups_comparables()
            admins = self._seed_admins()
            owners = self._seed_owners()
            edificis = self._seed_edificis(admins, grups)
            self._seed_habitatges_amb_dades(edificis, owners)
            self._seed_temporades()

        self.stdout.write(self.style.SUCCESS(
            "\nSeed completat. Pots iniciar sessió amb qualsevol de:"
        ))
        self.stdout.write(f"  admin1@{DEMO_EMAIL_DOMAIN}  /  {DEMO_PASSWORD}")
        self.stdout.write(f"  owner1@{DEMO_EMAIL_DOMAIN}  /  {DEMO_PASSWORD}")

    # ------------------------------------------------------------------ reset
    def _reset(self):
        self.stdout.write(self.style.WARNING("Reset: esborrant dataset demo..."))
        demo_users = User.objects.filter(email__endswith=f"@{DEMO_EMAIL_DOMAIN}")
        # Cascade-deletes: Edifici → Habitatge → DadesEnergetiques,
        # Participacio, RankingHistorico, etc.
        edificis = Edifici.objects.filter(administradorFinca__in=demo_users)
        edificis.delete()
        # Borrem temporades demo per nom
        Temporada.objects.filter(nom__startswith="Demo ").delete()
        # Esborrem grups comparables creats per nosaltres
        GrupComparable.objects.filter(
            idGrup__in=[g["idGrup"] for g in GRUPS_COMPARABLES_DATA]
        ).delete()
        demo_users.delete()
        self.stdout.write("  reset OK.")

    # -------------------------------------------------------- grups comparables
    def _seed_grups_comparables(self) -> list[GrupComparable]:
        self.stdout.write("Creant grups comparables...")
        grups = []
        for spec in GRUPS_COMPARABLES_DATA:
            grup, created = GrupComparable.objects.update_or_create(
                idGrup=spec["idGrup"],
                defaults={
                    "zonaClimatica": spec["zonaClimatica"],
                    "tipologia": spec["tipologia"],
                    "rangSuperficie": spec["rangSuperficie"],
                },
            )
            grups.append(grup)
            self.stdout.write(
                f"  {'+' if created else '·'} grup idGrup={grup.idGrup} "
                f"({grup.tipologia}, {grup.rangSuperficie})"
            )
        return grups

    # ----------------------------------------------------------------- admins
    def _seed_admins(self) -> list[User]:
        self.stdout.write("Creant AdminFinca aprovats...")
        admins = []
        for i in range(1, 4):
            email = f"admin{i}@{DEMO_EMAIL_DOMAIN}"
            user = self._upsert_user(
                email=email,
                first_name=f"Admin{i}",
                last_name="Finca",
            )
            profile = user.profile
            profile.role = RoleChoices.ADMIN
            profile.estatValidacioAdmin = ValidacioAdmin.APROVAT
            profile.account_status = AccountStatus.ACTIVE
            profile.save(update_fields=[
                "role", "estatValidacioAdmin", "account_status",
            ])
            admins.append(user)
            self.stdout.write(f"  · {email}")
        return admins

    # ----------------------------------------------------------------- owners
    def _seed_owners(self) -> list[User]:
        self.stdout.write("Creant propietaris...")
        owners = []
        for i in range(1, 11):
            email = f"owner{i}@{DEMO_EMAIL_DOMAIN}"
            user = self._upsert_user(
                email=email,
                first_name=f"Owner{i}",
                last_name=f"Demo{i:02d}",
            )
            profile = user.profile
            profile.role = RoleChoices.OWNER
            profile.account_status = AccountStatus.ACTIVE
            profile.save(update_fields=["role", "account_status"])
            owners.append(user)
        self.stdout.write(f"  · {len(owners)} propietaris")
        return owners

    def _upsert_user(self, email: str, first_name: str, last_name: str) -> User:
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            user = User.objects.create_user(
                email=email,
                password=DEMO_PASSWORD,
                first_name=first_name,
                last_name=last_name,
            )
        # Si l'usuari existeix però el seu Profile no, el creem.
        Profile.objects.get_or_create(user=user)
        return user

    # --------------------------------------------------------------- edificis
    def _seed_edificis(
        self, admins: list[User], grups: list[GrupComparable],
    ) -> list[Edifici]:
        self.stdout.write("Creant 18 edificis (6 per AdminFinca)...")
        edificis = []
        # 18 carrers únics per als 18 edificis (de la llista predefinida)
        street_iter = iter(BARCELONA_STREETS)
        for admin_idx, admin in enumerate(admins):
            for b in range(6):
                carrer, codi_postal = next(street_iter)
                numero = 10 + admin_idx * 20 + b * 3
                tipologia = TIPOLOGIES[(admin_idx + b) % len(TIPOLOGIES)]
                orientacio = ORIENTACIONS[(admin_idx + b) % len(ORIENTACIONS)]
                superficie = 1200 + (admin_idx * 6 + b) * 350  # entre 1200 i ~7000
                grup = grups[(admin_idx + b) % len(grups)]
                any_construccio = 1955 + (admin_idx * 6 + b) * 3  # 1955..2010

                # Idempotència: identifiquem l'edifici per la seva
                # Localitzacio (carrer + numero), que és OneToOne.
                barri = BARRIS[(admin_idx + b) % len(BARRIS)]
                loc, _ = Localitzacio.objects.update_or_create(
                    carrer=carrer,
                    numero=numero,
                    defaults={
                        "codiPostal": codi_postal,
                        "barri": barri,
                    },
                )
                edifici, created = Edifici.objects.update_or_create(
                    localitzacio=loc,
                    defaults={
                        "anyConstruccio": any_construccio,
                        "tipologia": tipologia,
                        "superficieTotal": superficie,
                        "reglament": "CTE",
                        "orientacioPrincipal": orientacio,
                        "administradorFinca": admin,
                        "grupComparable": grup,
                    },
                )
                edificis.append(edifici)
                self.stdout.write(
                    f"  {'+' if created else '·'} "
                    f"{carrer} {numero} ({admin.email}, grup={grup.idGrup})"
                )
        return edificis

    # ------------------------------------------------- habitatges + energètic
    @staticmethod
    def _n_habitatges_for_owner(idx: int) -> int:
        # Primers 3 propietaris: 3 habitatges; següents 2: 2; resta: 1.
        if idx < 3:
            return 3
        if idx < 5:
            return 2
        return 1

    def _build_owner_assignments(
        self, edificis: list[Edifici], owners: list[User],
    ) -> list[tuple[User | None, Edifici, int]]:
        # (owner, edifici, planta) — planta serveix per fer la cadastral única
        assignments: list[tuple[User | None, Edifici, int]] = []
        for o_idx, owner in enumerate(owners):
            n_habitatges = self._n_habitatges_for_owner(o_idx)
            for h in range(n_habitatges):
                edifici = edificis[(o_idx * 4 + h * 5) % len(edificis)]
                assignments.append((owner, edifici, h + 1))

        # Afegim habitatges sense propietari fins a 2-4 per edifici.
        edifici_count = {e.idEdifici: 0 for e in edificis}
        for _, e, _ in assignments:
            edifici_count[e.idEdifici] += 1

        unowned_planta_counter = {e.idEdifici: 50 for e in edificis}
        for e in edificis:
            target = 2 + (e.idEdifici % 3)  # 2, 3 o 4 habitatges per edifici
            while edifici_count[e.idEdifici] < target:
                assignments.append((None, e, unowned_planta_counter[e.idEdifici]))
                unowned_planta_counter[e.idEdifici] += 1
                edifici_count[e.idEdifici] += 1
        return assignments

    @staticmethod
    def _get_or_init_dades_energetiques(ref: str) -> DadesEnergetiques:
        # Reutilitzem la DE existent si ja n'hi ha una; altrament en creem una nova.
        existing = (
            Habitatge.objects.filter(referenciaCadastral=ref)
            .select_related("dadesEnergetiques")
            .first()
        )
        if existing and existing.dadesEnergetiques:
            return existing.dadesEnergetiques
        return DadesEnergetiques()

    def _seed_habitatges_amb_dades(
        self, edificis: list[Edifici], owners: list[User],
    ):
        self.stdout.write("Creant habitatges + dades energètiques...")
        owner_assignments = self._build_owner_assignments(edificis, owners)

        for owner, edifici, planta_idx in owner_assignments:
            ref = self._build_cadastral(edifici, planta_idx)
            de = self._get_or_init_dades_energetiques(ref)
            self._populate_dades_energetiques(de, edifici, planta_idx)
            de.save()

            Habitatge.objects.update_or_create(
                referenciaCadastral=ref,
                defaults={
                    "edifici": edifici,
                    "propietari": owner,
                    "planta": str(planta_idx),
                    "porta": chr(ord("A") + (planta_idx % 4)),
                    "superficie": 65 + (planta_idx * 7) % 60,
                    "dadesEnergetiques": de,
                },
            )

        self.stdout.write(
            f"  · {len(owner_assignments)} habitatges creats/actualitzats"
        )

    def _build_cadastral(self, edifici: Edifici, planta: int) -> str:
        # Format determinístic: prefix demo + idEdifici + planta. Garantitzem
        # unicitat dins el dataset i no col·lidim amb cadastrals reals.
        return f"DEMO{edifici.idEdifici:05d}P{planta:03d}"

    def _populate_dades_energetiques(
        self, de: DadesEnergetiques, edifici: Edifici, planta_idx: int,
    ):
        # Generem valors determministics però amb variació segons l'edifici
        # i la planta perquè els rankings no quedin tots empatats.
        seed_val = edifici.idEdifici * 17 + planta_idx * 3
        rng = _DeterministicRandom(seed_val)
        consum_primari = rng.uniform(80, 320)
        de.consumEnergiaPrimaria = consum_primari
        de.consumEnergiaFinal = consum_primari * 0.65
        de.emissionsCO2 = min(consum_primari * 0.22, 150.0)
        de.costAnualEnergia = consum_primari * 12
        de.energiaCalefaccio = consum_primari * 0.45
        de.energiaRefrigeracio = consum_primari * 0.15
        de.energiaACS = consum_primari * 0.20
        de.energiaEnllumenament = consum_primari * 0.10
        de.emissionsCalefaccio = consum_primari * 0.10
        de.emissionsRefrigeracio = consum_primari * 0.04
        de.emissionsACS = consum_primari * 0.05
        de.emissionsEnllumenament = consum_primari * 0.03
        de.aillamentTermic = rng.uniform(0.3, 2.5)
        de.valorFinestres = rng.uniform(1.5, 4.5)
        de.qualificacioGlobal = "ABCDEFG"[min(6, int(consum_primari // 50))]
        de.dataEntrada = date(2024, 1, 1) + timedelta(days=rng.randint(0, 365))
        de.normativa = "CTE-2019"
        de.einaCertificacio = "CE3X"
        de.motiuCertificacio = "Compraventa"
        de.rehabilitacioEnergetica = rng.random() < 0.3

    # ------------------------------------------------------------- temporades
    def _seed_temporades(self):
        self.stdout.write("Creant temporades (2 passades + 1 actual)...")
        today = timezone.now().date()
        # Ordre cronològic: cada iniciar() auto-tanca l'anterior amb snapshots.
        specs = [
            ("Demo Temporada 2024", date(2024, 1, 1), date(2024, 12, 31)),
            ("Demo Temporada 2025", date(2025, 1, 1), date(2025, 12, 31)),
            (
                "Demo Temporada 2026",
                date(today.year, 1, 1),
                date(today.year, 12, 31),
            ),
        ]
        for nom, data_inici, data_fi in specs:
            t, _ = Temporada.objects.get_or_create(
                nom=nom,
                defaults={
                    "dataInici": data_inici,
                    "dataFi": data_fi,
                    "estat": "PENDENT",
                },
            )
            if t.estat == "PENDENT":
                # iniciar() activa la temporada actual i, si n'hi havia una
                # d'anterior ACTIVA, la tanca consolidant-li els
                # RankingHistorico automàticament. El signal post_save
                # de Temporada crea les Lligues + Participacions de la
                # nova ACTIVA.
                Temporada.objects.iniciar(t)
                t.refresh_from_db()

            self.stdout.write(f"  · {nom} → {t.estat}")
