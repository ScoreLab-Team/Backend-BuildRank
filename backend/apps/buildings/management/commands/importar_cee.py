# apps/buildings/management/commands/importar_cee.py

import csv
from itertools import groupby
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.buildings.models import (
    Edifici,
    FontClassificacio,
    ImportacioIncidencia,
    ImportacioLog,
    Localitzacio,
    TipusEdifici,
    TipusEdificiOpenData,
    TipusOrientacio,
    DadesEnergetiquesOpenData,
)
from apps.buildings.services.open_data_tipologia import map_tipus_edifici


def _llegir_chunk(fitxer: str, offset_edificis: int, limit_edificis: int | None) -> list[dict]:
    files = []
    adreces_vistes = set()
    edificis_comptats = 0
    adreces_del_chunk = set()

    with open(fitxer, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=',')

        # DEBUG: mostra les columnes reals del CSV
        print(f"\n[DEBUG] Columnes del CSV: {reader.fieldnames}\n")

        for fila in reader:
            clau = _clau_adreca(fila)

            if clau not in adreces_vistes:
                adreces_vistes.add(clau)
                edificis_comptats += 1
                if edificis_comptats <= offset_edificis:
                    continue

            if limit_edificis and clau not in adreces_del_chunk:
                if len(adreces_del_chunk) >= limit_edificis:
                    break
                adreces_del_chunk.add(clau)

            files.append(fila)

    print(f"[DEBUG] Total files llegides: {len(files)}")
    print(f"[DEBUG] Total adreces úniques al chunk: {len(adreces_del_chunk)}\n")
    return files


def _f(fila: dict, camp: str) -> float:
    return float((fila.get(camp) or '0').replace(',', '.'))


def _parse_date(value):
    if not value:
        return None
    value = str(value).strip()
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Data invàlida: '{value}'")


def _bool_si(fila: dict, camp: str) -> bool:
    return (fila.get(camp) or '').strip().upper() == 'SI'


def _construir_dades_energetiques(grup: list[dict]):
    f = grup[0]
    data_raw = _parse_date(f.get('DATA_ENTRADA'))
    return DadesEnergetiquesOpenData(
        qualificacioGlobal      = f.get("Qualificació de consum d'energia primaria no renovable") or None,
        consumEnergiaPrimaria   = _f(f, 'Energia primària no renovable'),
        consumEnergiaFinal      = _f(f, 'Consum d\'energia final'),
        emissionsCO2            = _f(f, 'Emissions de CO2'),
        costAnualEnergia        = _f(f, 'Cost anual aproximat d\'energia per habitatge'),
        energiaCalefaccio       = _f(f, 'Energia calefacció'),
        energiaRefrigeracio     = _f(f, 'Energia refrigeració'),
        energiaACS              = _f(f, 'Energia ACS'),
        energiaEnllumenament    = _f(f, 'Energia enllumenament'),
        emissionsCalefaccio     = _f(f, 'Emissions calefacció'),
        emissionsRefrigeracio   = _f(f, 'Emissions refrigeració'),
        emissionsACS            = _f(f, 'Emissions ACS'),
        emissionsEnllumenament  = _f(f, 'Emissions enllumenament'),
        aillamentTermic         = _f(f, 'VALOR AILLAMENTS'),
        valorFinestres          = _f(f, 'VALOR FINESTRES'),
        normativa               = f.get('Normativa construcció') or '',
        einaCertificacio        = f.get('Eina de certificacio') or '',
        motiuCertificacio       = f.get('Motiu de la certificacio') or '',
        rehabilitacioEnergetica = (f.get('REHABILITACIO_ENERGETICA') or '').lower() == 'sí',
        dataEntrada             = data_raw,
        teSolarTermica          = _bool_si(f, 'SOLAR TERMICA'),
        teSolarFotovoltaica     = _bool_si(f, 'SOLAR FOTOVOLTAICA'),
        teBiomassa              = _bool_si(f, 'SISTEMA BIOMASSA'),
        teGeotermia             = _bool_si(f, 'ENERGIA GEOTERMICA'),
    )


class Command(BaseCommand):
    help = 'Importa dades obertes CEE — crea Edificis i Localitzacions'

    def add_arguments(self, parser):
        parser.add_argument('fitxer', type=str)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--offset', type=int, default=0)

    def handle(self, *args, **options):
        fitxer  = options['fitxer']
        dry_run = options['dry_run']
        limit   = options['limit']
        offset  = options['offset']

        print(f"[DEBUG] fitxer={fitxer} | dry_run={dry_run} | limit={limit} | offset={offset}\n")

        log = ImportacioLog.objects.create(origen=fitxer)

        try:
            files = _llegir_chunk(fitxer, offset_edificis=offset, limit_edificis=limit)
            files.sort(key=_clau_adreca)

            grups = [
                (clau, list(grup))
                for clau, grup in groupby(files, key=_clau_adreca)
            ]

            print(f"[DEBUG] Grups (edificis únics) a processar: {len(grups)}\n")

            ok = errors = edificis_creats = saltats = 0

            for i, (clau, grup) in enumerate(grups):
                primera = grup[0]
                num_cas = primera.get('NUM_CAS', '') or ''
                print(f"[DEBUG] [{i+1}/{len(grups)}] clau={clau} | num_cas='{num_cas}' | files_grup={len(grup)}")

                try:
                    with transaction.atomic():

                        # --- CHECK DUPLICAT ---
                        if num_cas and Edifici.objects.filter(num_cas_origen=num_cas).exists():
                            print(f"  → SALTAT (ja existeix num_cas='{num_cas}')")
                            saltats += 1
                            continue

                        edifici = _construir_edifici(grup)
                        print(f"  → Edifici construït: tipologia={edifici.tipologia}, any={edifici.anyConstruccio}, qualificacio={edifici.classificacioEstimada}")

                        if not dry_run:
                            lat_raw = (primera.get('LATITUD') or '0').replace(',', '.')
                            lon_raw = (primera.get('LONGITUD') or '0').replace(',', '.')
                            print(f"  → Localitzacio: carrer='{clau[0].title()}' num={clau[1]} cp={clau[2]} lat={lat_raw} lon={lon_raw}")

                            loc = Localitzacio.objects.create(
                                carrer=clau[0].title(),
                                numero=int(clau[1]) if clau[1].isdigit() else 0,
                                codiPostal=clau[2],
                                barri='',
                                latitud=float(lat_raw),
                                longitud=float(lon_raw),
                                zonaClimatica=primera.get('ZONA CLIMATICA', '') or '',
                            )
                            edifici.localitzacio = loc
                            edifici.save()
                            print(f"  → Edifici desat (id={edifici.idEdifici})")

                            dades_od = _construir_dades_energetiques(grup)
                            dades_od.edifici = edifici
                            dades_od.save()
                            print(f"  → DadesEnergetiquesOpenData desades")

                            edificis_creats += 1
                        else:
                            print(f"  → DRY-RUN: no s'escriu res")
                            ok += len(grup)
                            continue

                        ok += len(grup)
                        print(f"  → OK\n")

                except Exception as e:
                    import traceback
                    print(f"  → ERROR: {type(e).__name__}: {e}")
                    print(traceback.format_exc())
                    errors += len(grup)
                    for fila in grup:
                        ImportacioIncidencia.objects.create(
                            importacio=log,
                            num_cas=fila.get('NUM_CAS', ''),
                            motiu=f"{type(e).__name__}: {e}",
                            dades_raw={
                                'NUM_CAS':     fila.get('NUM_CAS', ''),
                                'ADREÇA':      fila.get('ADREÇA', ''),
                                'NUMERO':      fila.get('NUMERO', ''),
                                'CODI_POSTAL': fila.get('CODI_POSTAL', ''),
                                'US_EDIFICI':  fila.get('US_EDIFICI', ''),
                            },
                        )

            print(f"\n[DEBUG] RESUM: creats={edificis_creats} | saltats={saltats} | errors={errors} | files_ok={ok}\n")

            log.total_files     = ok + errors
            log.files_ok        = ok
            log.files_error     = errors
            log.edificis_creats = edificis_creats
            log.completada      = True
            log.data_fi         = timezone.now()
            log.save()

        except Exception as e:
            import traceback
            print(f"[DEBUG] EXCEPCIÓ GLOBAL: {type(e).__name__}: {e}")
            print(traceback.format_exc())
            log.completada = False
            log.data_fi    = timezone.now()
            log.save()
            raise


def _clau_adreca(r: dict) -> tuple:
    return (
        (r.get('ADREÇA') or '').strip().upper(),
        (r.get('NUMERO') or '').strip(),
        (r.get('CODI_POSTAL') or '').strip(),
    )


def _construir_edifici(grup: list[dict]) -> Edifici:
    primera = grup[0]
    tipologia_raw     = (primera.get('US_EDIFICI') or '').strip()
    tipologia         = map_tipus_edifici(tipologia_raw)
    tipologia_interna = (
        TipusEdifici.COMERCIAL
        if tipologia == TipusEdificiOpenData.TERCIARI
        else TipusEdifici.RESIDENCIAL
    )
    any_c = str(primera.get('ANY_CONSTRUCCIO') or '')
    qualificacio = primera.get("Qualificació de consum d'energia primaria no renovable") or None

    return Edifici(
        anyConstruccio        = int(any_c) if any_c.isdigit() else 0,
        tipologia             = tipologia_interna,
        tipologia_open_data   = tipologia,
        superficieTotal       = float((primera.get('METRES_CADASTRE') or '0').replace(',', '.')),
        nombrePlantes         = 1,
        reglament             = primera.get('Normativa construcció', '') or '',
        orientacioPrincipal   = TipusOrientacio.SUD,
        font_open_data        = True,
        num_cas_origen        = primera.get('NUM_CAS', '') or '',
        classificacioEstimada = qualificacio,
        classificacioFont     = FontClassificacio.OFICIAL if qualificacio else FontClassificacio.INSUFICIENT,
    )