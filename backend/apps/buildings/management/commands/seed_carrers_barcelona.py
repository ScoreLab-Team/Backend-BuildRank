import csv
import re
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.buildings.models import carrersBarcelona


def normalize_header(value: str) -> str:
    value = value.strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def to_int_or_none(value):
    value = clean_text(value)

    if not value:
        return None

    # Alguns CSV poden portar decimals o textos estranys.
    match = re.search(r"\d+", value)
    if not match:
        return None

    return int(match.group(0))


def first_existing(row, candidates, default=""):
    for candidate in candidates:
        if candidate in row and clean_text(row[candidate]):
            return clean_text(row[candidate])
    return default


class Command(BaseCommand):
    help = "Importa el carrerer oficial de Barcelona a la taula carrersBarcelona."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default=None,
            help="Ruta al CSV del carrerer. Per defecte: backend/data/carrerer.csv",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Esborra els carrers existents abans d'importar.",
        )

    def handle(self, *args, **options):
        path = options["path"]

        if path is None:
            # En Docker, BASE_DIR acostuma a ser /app.
            path = Path(settings.BASE_DIR) / "data" / "carrerer.csv"
        else:
            path = Path(path)

        if not path.exists():
            raise CommandError(
                f"No s'ha trobat el fitxer CSV: {path}. "
                "Descarrega el carrerer d'Open Data BCN i desa'l com data/carrerer.csv."
            )

        if options["clear"]:
            deleted, _ = carrersBarcelona.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"S'han esborrat {deleted} carrers existents."))

        created = 0
        updated = 0
        skipped = 0

        # utf-8-sig evita problemes amb BOM.
        with path.open("r", encoding="utf-8-sig", newline="") as csvfile:
            sample = csvfile.read(4096)
            csvfile.seek(0)

            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;")
            except csv.Error:
                dialect = csv.excel

            reader = csv.DictReader(csvfile, dialect=dialect)

            if not reader.fieldnames:
                raise CommandError("El CSV no té capçalera.")

            normalized_fieldnames = [normalize_header(name) for name in reader.fieldnames]

            for raw_row in reader:
                row = {
                    normalize_header(key): value
                    for key, value in raw_row.items()
                    if key is not None
                }

                # Intentem ser tolerants amb noms de columna diferents del portal.
                codi_carrer_ine = first_existing(
                    row,
                    [
                        "codi_carrer_ine",
                        "codi_ine",
                        "codi_via_ine",
                        "codi",
                        "codi_carrer",
                        "ine",
                    ],
                )

                tipus_via = first_existing(
                    row,
                    [
                        "tipus_via",
                        "tipus",
                        "tipus_de_via",
                        "tipus_carrer",
                        "nom_tipus_via",
                    ],
                    default="Carrer",
                )

                nom_curt = first_existing(
                    row,
                    [
                        "nom_curt",
                        "nom",
                        "nom_via",
                        "nom_carrer",
                        "nom_curt_via",
                    ],
                )

                nom_oficial = first_existing(
                    row,
                    [
                        "nom_oficial",
                        "nom_oficial_via",
                        "nom_llarg",
                        "nom_complet",
                        "denominacio",
                    ],
                    default=nom_curt,
                )

                nre_min = to_int_or_none(
                    first_existing(
                        row,
                        [
                            "nre_min",
                            "num_min",
                            "numero_min",
                            "numeracio_min",
                            "nre_minim",
                        ],
                    )
                )

                nre_max = to_int_or_none(
                    first_existing(
                        row,
                        [
                            "nre_max",
                            "num_max",
                            "numero_max",
                            "numeracio_max",
                            "nre_maxim",
                        ],
                    )
                )

                if not nom_oficial:
                    skipped += 1
                    continue

                # Si no hi ha codi al CSV, generem una clau funcional estable.
                # El model té AutoField com a PK, així que aquest camp pot ser informatiu.
                if not codi_carrer_ine:
                    codi_carrer_ine = f"AUTO-{normalize_header(tipus_via)}-{normalize_header(nom_oficial)}"

                obj, was_created = carrersBarcelona.objects.update_or_create(
                    codi_carrer_ine=codi_carrer_ine,
                    defaults={
                        "tipus_via": tipus_via[:50],
                        "nom_curt": (nom_curt or nom_oficial)[:100],
                        "nom_oficial": nom_oficial[:150],
                        "nre_min": nre_min,
                        "nre_max": nre_max,
                    },
                )

                if was_created:
                    created += 1
                else:
                    updated += 1

        total = carrersBarcelona.objects.count()

        self.stdout.write(
            self.style.SUCCESS(
                f"Importació completada. Creats: {created}. Actualitzats: {updated}. "
                f"Omesos: {skipped}. Total actual: {total}."
            )
        )