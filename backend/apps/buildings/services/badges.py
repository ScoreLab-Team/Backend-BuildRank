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
    if temporada is not None:
        medalla = _assignar_medalla_bhs(edifici, temporada, bhs, definitions)
        if medalla:
            assignades.append(medalla)

    emissions = _to_decimal(metrics.get("emissions"))
    if temporada is not None and emissions is not None and emissions <= Decimal("10"):
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
    if temporada is not None and millores_validades >= 1:
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
    if temporada is not None and progres_bhs is not None and progres_bhs >= Decimal("10"):
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



def get_temporada_actual():
    """
    Retorna una temporada activa o vigent si es pot inferir.

    És robust perquè el model de Temporada pot variar:
    - primer intenta estat='activa'
    - després dataInici/dataFi amb la data actual
    - finalment retorna l'última temporada disponible
    """
    try:
        from django.utils import timezone
        from apps.seasons.models import Temporada

        qs = Temporada.objects.all()

        field_names = {field.name for field in Temporada._meta.fields}

        if "estat" in field_names:
            temporada = qs.filter(estat__iexact="activa").order_by("-id").first()
            if temporada:
                return temporada

        if "dataInici" in field_names and "dataFi" in field_names:
            today = timezone.localdate()
            temporada = (
                qs.filter(dataInici__lte=today, dataFi__gte=today)
                .order_by("-dataInici")
                .first()
            )
            if temporada:
                return temporada

        if "dataInici" in field_names:
            return qs.order_by("-dataInici").first()

        return qs.order_by("-id").first()

    except Exception:
        return None


def _first_numeric_attr(instance, field_names):
    for field_name in field_names:
        if hasattr(instance, field_name):
            value = getattr(instance, field_name)
            decimal_value = _to_decimal(value)
            if decimal_value is not None:
                return decimal_value
    return None


def _infer_emissions(edifici):
    try:
        from apps.buildings.models import DadesEnergetiques

        qs = DadesEnergetiques.objects.filter(dades_energetiques__edifici=edifici)

        for field in DadesEnergetiques._meta.fields:
            name = field.name
            if "emiss" not in name.lower():
                continue

            value = (
                qs.exclude(**{f"{name}__isnull": True})
                .values_list(name, flat=True)
                .first()
            )
            decimal_value = _to_decimal(value)
            if decimal_value is not None:
                return decimal_value

    except Exception:
        return None

    return None


def calcular_metrics_badges_edifici(edifici):
    """
    Calcula mètriques bàsiques sense acoblar el servei a un únic camp concret.

    Això permet que el servei funcioni encara que el BHS o les dades energètiques
    evolucionin, i evita trencar el backend si algun camp no existeix.
    """
    metrics = {}

    metrics["bhs"] = _first_numeric_attr(
        edifici,
        [
            "puntuacio",
            "puntuacioBase",
            "puntuacioBaseOpenData",
            "buildingHealthScore",
            "healthScore",
            "bhs",
        ],
    )

    metrics["emissions"] = _infer_emissions(edifici)

    try:
        from apps.buildings.models import MilloraImplementada, EstatValidacio

        metrics["millores_validades"] = MilloraImplementada.objects.filter(
            edifici=edifici,
            estatValidacio=EstatValidacio.VALIDADA,
        ).count()
    except Exception:
        metrics["millores_validades"] = 0

    # Per MVP, considerem dades verificades quan l'edifici té dades energètiques
    # vinculades o algun indicador de font fiable. Es pot refinar més endavant.
    try:
        te_dades = edifici.habitatges.filter(dadesEnergetiques__isnull=False).exists()
    except Exception:
        te_dades = False

    font_open_data = bool(
        getattr(edifici, "fontOpenData", None)
        or getattr(edifici, "font_open_data", None)
        or getattr(edifici, "fontDades", None)
    )

    metrics["dades_verificades"] = bool(te_dades or font_open_data)
    metrics["progres_bhs"] = None

    return metrics


def recalcular_insignies_edifici(edifici, temporada=None, metrics=None):
    """
    Recalcula insígnies d'un edifici a partir de mètriques actuals.

    Si no es passa temporada, intenta trobar la temporada activa/vigent.
    Les insígnies permanents no depenen de temporada.
    """
    if temporada is None:
        temporada = get_temporada_actual()

    if metrics is None:
        metrics = calcular_metrics_badges_edifici(edifici)

    return assignar_insignies_edifici(
        edifici=edifici,
        temporada=temporada,
        metrics=metrics,
    )


def serialitzar_badge_assignacio(assignacio):
    return {
        "id": assignacio.id,
        "code": assignacio.badge.code,
        "nom": assignacio.badge.nom,
        "descripcio": assignacio.badge.descripcio,
        "categoria": assignacio.badge.categoria,
        "scope": assignacio.badge.scope,
        "temporada": assignacio.temporada_id,
        "temporadaNom": assignacio.temporada.nom if assignacio.temporada_id else None,
        "valorSnapshot": (
            str(assignacio.valor_snapshot)
            if assignacio.valor_snapshot is not None
            else None
        ),
        "metadata": assignacio.metadata,
        "awardedAt": assignacio.awarded_at,
    }


def get_badges_resum_edifici(edifici, temporada=None, limit=3):
    """
    Retorna un resum curt d'insígnies per pintar en cards del frontend.
    Inclou permanents i, si hi ha temporada, les estacionals d'aquella temporada.
    """
    from django.db.models import Q

    qs = (
        BuildingBadge.objects
        .filter(edifici=edifici, badge__activa=True)
        .select_related("badge", "temporada")
        .order_by("badge__categoria", "badge__code", "-awarded_at")
    )

    if temporada:
        temporada_id = getattr(temporada, "pk", temporada)
        qs = qs.filter(Q(temporada_id=temporada_id) | Q(temporada__isnull=True))

    return [serialitzar_badge_assignacio(assignacio) for assignacio in qs[:limit]]
