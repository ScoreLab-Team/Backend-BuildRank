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
    """
    Llegeix el CSV línia a línia fins a tenir suficients edificis (grups d'adreça únics).
    Evita carregar 1,34M de files a memòria quan només en volem 50.
    """
    files = []
    adreces_vistes = set()
    edificis_comptats = 0
    adreces_del_chunk = set()

    with open(fitxer, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=',')
        for fila in reader:
            clau = _clau_adreca(fila)

            # Saltar fins a l'offset
            if clau not in adreces_vistes:
                adreces_vistes.add(clau)
                edificis_comptats += 1
                if edificis_comptats <= offset_edificis:
                    continue

            # Si ja tenim prou edificis i aquesta fila és un edifici nou, parar
            if limit_edificis and clau not in adreces_del_chunk:
                if len(adreces_del_chunk) >= limit_edificis:
                    break
                adreces_del_chunk.add(clau)

            files.append(fila)

    return files

def _f(fila: dict, camp: str) -> float: 
    """Converteix un camp numèric del CSV (amb coma decimal) a float.""" 
    return float((fila.get(camp) or '0').replace(',', '.'))

def _parse_date(value):
    if not value:
        return None

    value = str(value).strip()

    try:
        # format europeu: DD/MM/YYYY
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        try:
            # per si algun ja ve bé
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Data invàlida: '{value}'")
def _bool_si(fila: dict, camp: str) -> bool:
    return (fila.get(camp) or '').strip().upper() == 'SI'

def _construir_dades_energetiques(grup: list[dict]):
    """
    Agafa la primera fila del grup com a representativa de l'edifici.
    Per a blocs de pisos, podria fer-se una mitjana, però la primera
    fila és suficient per a la seed inicial.
    """
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
        parser.add_argument(
            'fitxer',
            type=str,
            help='Ruta al fitxer CSV de certificats energètics'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Valida sense escriure res a la base de dades'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Nombre màxim d\'edificis (grups d\'adreça) a importar'
        )
        parser.add_argument(
            '--offset',
            type=int,
            default=0,
            help='Saltar els primers N edificis (per importar per tandes)'
        )

    def handle(self, *args, **options):
        fitxer  = options['fitxer']
        dry_run = options['dry_run']
        limit   = options['limit']
        offset  = options['offset']

        log = ImportacioLog.objects.create(origen=fitxer)
        #self.stdout.write(f"Importació #{log.pk} iniciada — dry_run={dry_run}")

        try:
            # Llegir NOMÉS les files necessàries en comptes de tot el CSV
            files = _llegir_chunk(fitxer, offset_edificis=offset, limit_edificis=limit)
            #self.stdout.write(f"Files llegides: {len(files)}")

            # Ordenar per adreça abans d'agrupar
            files.sort(key=_clau_adreca)

            # Construir llista de grups (1 grup = 1 edifici)
            grups = [
                (clau, list(grup))
                for clau, grup in groupby(files, key=_clau_adreca)
            ]


            #self.stdout.write(
            #    f"Processant {len(grups)} edificis "
            #    f"(offset={offset}, limit={limit or 'tots'})"
            #)

            ok = errors = edificis_creats = 0

            for clau, grup in grups:
                try:
                    with transaction.atomic():
                        edifici = _construir_edifici(grup)

                        if not dry_run:
                            primera = grup[0]
                            loc = Localitzacio.objects.create(
                                carrer=clau[0].title(),
                                numero=int(clau[1]) if clau[1].isdigit() else 0,
                                codiPostal=clau[2],
                                barri='',
                                latitud=float((primera.get('LATITUD') or '0').replace(',', '.')),
                                longitud=float((primera.get('LONGITUD') or '0').replace(',', '.')),
                                zonaClimatica=primera.get('ZONA CLIMATICA', '') or '',
                            )
                            edifici.localitzacio = loc
                            edifici.save()
                            dades_od = _construir_dades_energetiques(grup)
                            dades_od.edifici = edifici
                            dades_od.save()
                            edificis_creats += 1
                            
                        else:
                            #self.stdout.write(
                            #    f"  [dry] {clau[0].title()} {clau[1]}, "
                            #    f"{clau[2]} — {edifici.tipologia_open_data}"
                            #)
                            return

                        ok += len(grup)

                except Exception as e:
                    errors += len(grup)
                    for fila in grup:
                        ImportacioIncidencia.objects.create(
                            importacio=log,
                            num_cas=fila.get('NUM_CAS', ''),
                            motiu=f"{type(e).__name__}: {e}",
                            dades_raw={
                                'NUM_CAS':    fila.get('NUM_CAS', ''),
                                'ADREÇA':     fila.get('ADREÇA', ''),
                                'NUMERO':     fila.get('NUMERO', ''),
                                'CODI_POSTAL': fila.get('CODI_POSTAL', ''),
                                'US_EDIFICI': fila.get('US_EDIFICI', ''),
                            },
                        )

            log.files_ok        = ok
            log.files_error     = errors
            log.edificis_creats = edificis_creats
            log.completada      = True
            log.data_fi         = timezone.now()
            log.save()

            #self.stdout.write(self.style.SUCCESS(
            #    f"Fet: {edificis_creats} edificis creats, "
            #    f"{ok} files processades, {errors} errors. Log #{log.pk}"
            #))

        except Exception as e:
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
        anyConstruccio       = int(any_c) if any_c.isdigit() else 0,
        tipologia            = tipologia_interna,
        tipologia_open_data  = tipologia,
        superficieTotal      = float((primera.get('METRES_CADASTRE') or '0').replace(',', '.')),
        nombrePlantes        = 1,
        reglament            = primera.get('Normativa construcció', '') or '',
        orientacioPrincipal  = TipusOrientacio.SUD,
        font_open_data       = True,
        num_cas_origen       = primera.get('NUM_CAS', '') or '',
        # ← Classificació ve del CEE oficial → font sempre 'oficial'
        classificacioEstimada = qualificacio,
        classificacioFont     = FontClassificacio.OFICIAL if qualificacio else FontClassificacio.INSUFICIENT,
    )