import csv
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.buildings.services.open_data_tipologia import map_tipus_edifici


OUTPUT_FIELDS = [
    "num_cas_origen",
    "carrer",
    "numero",
    "codi_postal",
    "poblacio",
    "zona_climatica",
    "latitud",
    "longitud",
    "coord_estat",
    "necessita_geocodificacio",
    "any_construccio",
    "superficie_total_m2",
    "us_edifici_original",
    "tipologia_open_data",
    "qualificacio_global",
    "consum_energia_primaria",
    "emissions_co2",
    "consum_energia_final",
    "cost_anual_energia",
    "num_certificats",
    "font_dades",
]


def _clean(value):
    if value is None:
        return ""
    return str(value).strip()


def _upper(value):
    return _clean(value).upper()


def _first(row_group, field, default=""):
    for row in row_group:
        value = _clean(row.get(field))
        if value:
            return value
    return default


def _parse_decimal(value):
    value = _clean(value)
    if not value:
        return None

    try:
        return Decimal(value.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _format_decimal(value):
    if value is None:
        return ""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _parse_int(value):
    value = _clean(value)
    if not value:
        return ""

    try:
        return str(int(float(value.replace(",", "."))))
    except (TypeError, ValueError):
        return ""


def _sum_decimal(row_group, field):
    values = [
        _parse_decimal(row.get(field))
        for row in row_group
    ]
    values = [value for value in values if value is not None]

    if not values:
        return None

    return sum(values, Decimal("0"))


def _avg_decimal(row_group, field):
    values = [
        _parse_decimal(row.get(field))
        for row in row_group
    ]
    values = [value for value in values if value is not None]

    if not values:
        return None

    return sum(values, Decimal("0")) / Decimal(len(values))


def _clau_adreca(row):
    return (
        _upper(row.get("ADREÇA")),
        _upper(row.get("NUMERO")),
        _upper(row.get("CODI_POSTAL")),
    )


def _parse_coord_value(raw, min_value, max_value):
    raw = _clean(raw)

    if not raw:
        return None, "missing"

    try:
        value = float(raw.replace(",", "."))
    except (TypeError, ValueError):
        return None, "invalid"

    if value == 0:
        return None, "zero"

    if value < min_value or value > max_value:
        return None, "invalid"

    return value, "ok"


def _format_coord(value):
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _coords_summary(row):
    lat, lat_status = _parse_coord_value(row.get("LATITUD"), -90, 90)
    lon, lon_status = _parse_coord_value(row.get("LONGITUD"), -180, 180)

    if lat_status == "ok" and lon_status == "ok":
        return lat, lon, "ok"

    if lat_status == "missing" and lon_status == "missing":
        return None, None, "sense_coordenades"

    if "invalid" in {lat_status, lon_status}:
        return None, None, "invalida"

    if "zero" in {lat_status, lon_status}:
        return None, None, "zero"

    return None, None, "parcial"


def _read_rows(csv_path):
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        content = handle.read()

    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(content.splitlines(), dialect=dialect)
    return list(reader)


def _group_by_building(rows, limit=None):
    groups = OrderedDict()

    for row in rows:
        key = _clau_adreca(row)

        if key == ("", "", ""):
            continue

        is_new_key = key not in groups

        if limit is not None and is_new_key and len(groups) >= limit:
            break

        groups.setdefault(key, []).append(row)

    return groups


def normalitzar_grup(row_group):
    first = row_group[0]

    lat, lon, coord_estat = _coords_summary(first)

    us_edifici = _first(row_group, "US_EDIFICI")
    tipologia = map_tipus_edifici(us_edifici)

    qualificacio_global = (
        _first(row_group, "Qualificació de consum d'energia primaria no renovable")
        or _first(row_group, "Qualificacio d'emissions de CO2")
    )

    return {
        "num_cas_origen": _first(row_group, "NUM_CAS"),
        "carrer": _first(row_group, "ADREÇA"),
        "numero": _first(row_group, "NUMERO"),
        "codi_postal": _first(row_group, "CODI_POSTAL"),
        "poblacio": _first(row_group, "POBLACIO"),
        "zona_climatica": _first(row_group, "ZONA CLIMATICA"),
        "latitud": _format_coord(lat),
        "longitud": _format_coord(lon),
        "coord_estat": coord_estat,
        "necessita_geocodificacio": "true" if coord_estat != "ok" else "false",
        "any_construccio": _parse_int(_first(row_group, "ANY_CONSTRUCCIO")),
        "superficie_total_m2": _format_decimal(_sum_decimal(row_group, "METRES_CADASTRE")),
        "us_edifici_original": us_edifici,
        "tipologia_open_data": str(tipologia),
        "qualificacio_global": qualificacio_global,
        "consum_energia_primaria": _format_decimal(
            _avg_decimal(row_group, "Energia primària no renovable")
        ),
        "emissions_co2": _format_decimal(
            _avg_decimal(row_group, "Emissions de CO2")
        ),
        "consum_energia_final": _format_decimal(
            _avg_decimal(row_group, "Consum d'energia final")
        ),
        "cost_anual_energia": _format_decimal(
            _avg_decimal(row_group, "Cost anual aproximat d'energia per habitatge")
        ),
        "num_certificats": str(len(row_group)),
        "font_dades": "open_data_cee",
    }


class Command(BaseCommand):
    help = "Normalitza el CSV CEE en un CSV lleuger adaptat a BuildRank."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Ruta del CSV CEE original.")
        parser.add_argument(
            "--output",
            required=True,
            help="Ruta del CSV normalitzat de sortida.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Nombre màxim d'edificis/adreces a normalitzar.",
        )
        parser.add_argument(
            "--only-with-coords",
            action="store_true",
            help="Inclou només edificis amb coordenades vàlides.",
        )

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        output_path = Path(options["output"])
        limit = options.get("limit")
        only_with_coords = options.get("only_with_coords", False)

        rows = _read_rows(csv_path)
        groups = _group_by_building(rows, limit=limit)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        written = 0
        skipped_without_coords = 0

        with open(output_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()

            for row_group in groups.values():
                normalized = normalitzar_grup(row_group)

                if only_with_coords and normalized["coord_estat"] != "ok":
                    skipped_without_coords += 1
                    continue

                writer.writerow(normalized)
                written += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"CSV normalitzat creat: {output_path} "
                f"({written} edificis, {skipped_without_coords} descartats sense coordenades vàlides)"
            )
        )
