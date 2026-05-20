from decimal import Decimal, InvalidOperation

from apps.buildings.models import (
    BadgeCategory,
    BadgeDefinition,
    BadgeScope,
    BuildingBadge,
)


DEFAULT_BADGE_DEFINITIONS = [
    {
        "code": "BRONZE_BHS",
        "nom": "Bronze BHS",
        "descripcio": "Edifici amb una puntuació BHS correcta durant la temporada.",
        "categoria": BadgeCategory.SCORE,
        "scope": BadgeScope.SEASONAL,
        "criteris": {"bhs_min": 50},
    },
    {
        "code": "PLATA_BHS",
        "nom": "Plata BHS",
        "descripcio": "Edifici amb una puntuació BHS notable durant la temporada.",
        "categoria": BadgeCategory.SCORE,
        "scope": BadgeScope.SEASONAL,
        "criteris": {"bhs_min": 70},
    },
    {
        "code": "OR_BHS",
        "nom": "Or BHS",
        "descripcio": "Edifici amb una puntuació BHS excel·lent durant la temporada.",
        "categoria": BadgeCategory.SCORE,
        "scope": BadgeScope.SEASONAL,
        "criteris": {"bhs_min": 85},
    },
    {
        "code": "BAIXES_EMISSIONS",
        "nom": "Baixes emissions",
        "descripcio": "Edifici amb emissions estimades baixes en relació amb el criteri definit.",
        "categoria": BadgeCategory.EMISSIONS,
        "scope": BadgeScope.SEASONAL,
        "criteris": {"emissions_max": 10},
    },
    {
        "code": "DADES_VERIFICADES",
        "nom": "Dades verificades",
        "descripcio": "Edifici amb dades revisades o considerades fiables dins del sistema.",
        "categoria": BadgeCategory.DATA_QUALITY,
        "scope": BadgeScope.PERMANENT,
        "criteris": {"dades_verificades": True},
    },
    {
        "code": "MILLORA_IMPLEMENTADA",
        "nom": "Millora implementada",
        "descripcio": "Edifici amb almenys una millora validada com a implementada.",
        "categoria": BadgeCategory.IMPROVEMENT,
        "scope": BadgeScope.SEASONAL,
        "criteris": {"millores_validades_min": 1},
    },
    {
        "code": "PROGRES_DESTACAT",
        "nom": "Progrés destacat",
        "descripcio": "Edifici que ha millorat de manera significativa respecte a una referència anterior.",
        "categoria": BadgeCategory.PROGRESS,
        "scope": BadgeScope.SEASONAL,
        "criteris": {"progres_bhs_min": 10},
    },
]


SCORE_BADGE_CODES = ["BRONZE_BHS", "PLATA_BHS", "OR_BHS"]


def _to_decimal(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def crear_definicions_badges_base():
    """
    Crea o actualitza les definicions bàsiques d'insígnies.

    Aquesta funció és idempotent: es pot executar múltiples vegades sense duplicar
    definicions. Serveix per inicialitzar el catàleg bàsic del MVP.
    """
    definitions = {}

    for item in DEFAULT_BADGE_DEFINITIONS:
        badge, _created = BadgeDefinition.objects.update_or_create(
            code=item["code"],
            defaults={
                "nom": item["nom"],
                "descripcio": item["descripcio"],
                "categoria": item["categoria"],
                "scope": item["scope"],
                "criteris": item["criteris"],
                "activa": True,
            },
        )
        definitions[badge.code] = badge

    return definitions


def _assignar_badge(edifici, badge, temporada=None, valor_snapshot=None, metadata=None):
    if badge.scope == BadgeScope.PERMANENT:
        temporada = None

    assignacio, _created = BuildingBadge.objects.get_or_create(
        edifici=edifici,
        temporada=temporada,
        badge=badge,
        defaults={
            "valor_snapshot": valor_snapshot,
            "metadata": metadata or {},
        },
    )

    return assignacio


def _assignar_medalla_bhs(edifici, temporada, bhs, definitions):
    if bhs is None:
        return None

    selected_code = None

    if bhs >= Decimal("85"):
        selected_code = "OR_BHS"
    elif bhs >= Decimal("70"):
        selected_code = "PLATA_BHS"
    elif bhs >= Decimal("50"):
        selected_code = "BRONZE_BHS"

    if not selected_code:
        return None

    badge = definitions[selected_code]

    # En una mateixa temporada mantenim només la millor medalla BHS activa.
    BuildingBadge.objects.filter(
        edifici=edifici,
        temporada=temporada,
        badge__code__in=SCORE_BADGE_CODES,
    ).exclude(badge=badge).delete()

    return _assignar_badge(
        edifici=edifici,
        temporada=temporada,
        badge=badge,
        valor_snapshot=bhs,
        metadata={"metric": "bhs"},
    )


def assignar_insignies_edifici(edifici, temporada=None, metrics=None):
    """
    Assigna insígnies bàsiques a un edifici segons mètriques ja calculades.

    metrics pot incloure:
    - bhs
    - emissions
    - dades_verificades
    - millores_validades
    - progres_bhs

    Les insígnies de rendiment són estacionals. Les permanents, com DADES_VERIFICADES,
    no depenen de temporada.
    """
    metrics = metrics or {}
    definitions = crear_definicions_badges_base()
    assignades = []

    bhs = _to_decimal(metrics.get("bhs"))
    medalla = _assignar_medalla_bhs(edifici, temporada, bhs, definitions)
    if medalla:
        assignades.append(medalla)

    emissions = _to_decimal(metrics.get("emissions"))
    if emissions is not None and emissions <= Decimal("10"):
        assignades.append(
            _assignar_badge(
                edifici=edifici,
                temporada=temporada,
                badge=definitions["BAIXES_EMISSIONS"],
                valor_snapshot=emissions,
                metadata={"metric": "emissions"},
            )
        )

    if metrics.get("dades_verificades") is True:
        assignades.append(
            _assignar_badge(
                edifici=edifici,
                badge=definitions["DADES_VERIFICADES"],
                valor_snapshot=None,
                metadata={"metric": "dades_verificades"},
            )
        )

    millores_validades = metrics.get("millores_validades") or 0
    if millores_validades >= 1:
        assignades.append(
            _assignar_badge(
                edifici=edifici,
                temporada=temporada,
                badge=definitions["MILLORA_IMPLEMENTADA"],
                valor_snapshot=Decimal(str(millores_validades)),
                metadata={"metric": "millores_validades"},
            )
        )

    progres_bhs = _to_decimal(metrics.get("progres_bhs"))
    if progres_bhs is not None and progres_bhs >= Decimal("10"):
        assignades.append(
            _assignar_badge(
                edifici=edifici,
                temporada=temporada,
                badge=definitions["PROGRES_DESTACAT"],
                valor_snapshot=progres_bhs,
                metadata={"metric": "progres_bhs"},
            )
        )

    return assignades
