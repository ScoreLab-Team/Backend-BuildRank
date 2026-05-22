# apps/buildings/schemas.py
from drf_spectacular.utils import (
    extend_schema, extend_schema_view,
    OpenApiExample, OpenApiResponse, OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers


# ===========================================================================
# Serializers inline (només per a la documentació OpenAPI)
# ===========================================================================

class PointInputSerializer(serializers.Serializer):
    lat = serializers.FloatField(help_text="Latitud en graus decimals (WGS84). Rang [-90, 90].")
    lng = serializers.FloatField(help_text="Longitud en graus decimals (WGS84). Rang [-180, 180].")

class ThirdPartyRequestSerializer(serializers.Serializer):
    points = PointInputSerializer(many=True, help_text="Llista de coordenades a consultar.")

class PointResultSerializer(serializers.Serializer):
    lat   = serializers.FloatField(help_text="Latitud original del punt.")
    lng   = serializers.FloatField(help_text="Longitud original del punt.")
    score = serializers.FloatField(allow_null=True, required=False,
        help_text="Building Health Score (0–100). null si l'edifici no té puntuació.")
    match_type = serializers.ChoiceField(
        choices=["exacta", "carrer", "cap"], required=False,
        help_text="Nivell de coincidència: exacta (carrer+número), carrer (qualsevol número), cap (no trobat / random).")

class ThirdPartyResponseSerializer(serializers.Serializer):
    results = PointResultSerializer(many=True)


class DesactivarBodySerializer(serializers.Serializer):
    motiu = serializers.CharField(required=False, allow_blank=True,
        help_text="Motiu de la desactivació (opcional).")

class DesactivarDryRunResponseSerializer(serializers.Serializer):
    detail        = serializers.CharField()
    edifici_id    = serializers.IntegerField()
    advertencies  = serializers.ListField(child=serializers.CharField())
    pot_desactivar = serializers.BooleanField()

class DesactivarResponseSerializer(serializers.Serializer):
    detail                   = serializers.CharField()
    edifici_id               = serializers.IntegerField()
    dataDesactivacio         = serializers.DateTimeField()
    motiu                    = serializers.CharField()
    advertencies_en_el_moment = serializers.ListField(child=serializers.CharField())

class ReactivarResponseSerializer(serializers.Serializer):
    detail     = serializers.CharField()
    edifici_id = serializers.IntegerField()

class BadgesResponseSerializer(serializers.Serializer):
    edifici   = serializers.IntegerField()
    temporada = serializers.CharField(allow_null=True)
    count     = serializers.IntegerField()
    summary   = serializers.DictField()
    results   = serializers.ListField(child=serializers.DictField())

class RecalcularBadgesResponseSerializer(serializers.Serializer):
    edifici   = serializers.IntegerField()
    temporada = serializers.IntegerField(allow_null=True)
    count     = serializers.IntegerField()
    summary   = serializers.DictField()

class MapaResponseSerializer(serializers.Serializer):
    type     = serializers.CharField(default="FeatureCollection")
    count    = serializers.IntegerField()
    features = serializers.ListField(child=serializers.DictField())
    meta     = serializers.DictField()

class PosicioRankingResponseSerializer(serializers.Serializer):
    edificio_id      = serializers.IntegerField()
    liga             = serializers.CharField()
    posicion         = serializers.IntegerField()
    top_objetivo     = serializers.IntegerField()
    esta_en_top      = serializers.BooleanField()
    puntos_actuales  = serializers.FloatField()
    puntos_para_top  = serializers.FloatField()

class AdminFincaAltaResponseSerializer(serializers.Serializer):
    message               = serializers.CharField()
    edifici_id            = serializers.IntegerField()
    requereix_verificacio = serializers.BooleanField()

class SolicitudAccesResponseSerializer(serializers.Serializer):
    detail       = serializers.CharField()
    rolSolicitat = serializers.CharField()

class AutocompleteCarrerItemSerializer(serializers.Serializer):
    codi_via         = serializers.IntegerField()
    codi_carrer_ine  = serializers.CharField()
    nom_oficial      = serializers.CharField()
    nom_curt         = serializers.CharField()
    tipus_via        = serializers.CharField()
    nre_min          = serializers.IntegerField(allow_null=True)
    nre_max          = serializers.IntegerField(allow_null=True)


# ===========================================================================
# Third-party
# ===========================================================================

third_party_score_schema = extend_schema(
    tags=["Third-party"],
    summary="Consulta el Building Health Score per coordenades",
    description=(
        "Rep una llista de parells de coordenades (lat/lng) i retorna el **Building Health Score (BHS)** "
        "de l'edifici corresponent.\n\n"
        "**Flux intern per cada punt:**\n"
        "1. Geocodificació inversa via OpenStreetMap (Nominatim).\n"
        "2. Validació que les coordenades pertanyen a Barcelona.\n"
        "3. Cerca de l'edifici (coincidència exacta → carrer com a fallback).\n\n"
        "Si no es troba l'edifici, `score` és aleatori i `match_type` és `cap`.\n\n"
        "**Rate limiting:** 1 req/s per Nominatim. Per a volums >500 punts, contacteu-nos.\n\n"
        "**Autenticació:** `Authorization: Api-Key <token>`."
    ),
    request=ThirdPartyRequestSerializer,
    responses={
        200: OpenApiResponse(
            response=ThirdPartyResponseSerializer,
            description="Llista de resultats en el mateix ordre que els punts d'entrada.",
            examples=[
                OpenApiExample("Resposta mixta", value={
                    "results": [
                        {"lat": 41.3901, "lng": 2.1542, "score": 73.4, "match_type": "exacta"},
                        {"lat": 41.3875, "lng": 2.1601, "score": 55.2, "match_type": "carrer"},
                        {"lat": 40.4168, "lng": -3.7038, "score": 42.1, "match_type": "cap"},
                    ]
                }),
            ],
        ),
        400: OpenApiResponse(description="El camp `points` no és una llista vàlida."),
        403: OpenApiResponse(description="API Key absent o invàlida."),
    },
    examples=[
        OpenApiExample("Request d'exemple", request_only=True, value={
            "points": [
                {"lat": 41.3901, "lng": 2.1542},
                {"lat": 41.3875, "lng": 2.1601},
                {"lat": 40.4168, "lng": -3.7038},
            ]
        }),
    ],
)


# ===========================================================================
# EdificiViewSet
# ===========================================================================

edifici_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Edificis"],
        summary="Llista els edificis accessibles per l'usuari autenticat",
        description=(
            "Retorna els edificis als quals l'usuari té accés segons el seu rol.\n\n"
            "- **Superuser:** tots els edificis (actius per defecte; `?inclou_desactivats=true` per veure'ls tots).\n"
            "- **Admin finca:** edificis que administra (verificació documental aprovada).\n"
            "- **Owner/Tenant:** edificis on té habitatge vinculat."
        ),
        parameters=[
            OpenApiParameter("inclou_desactivats", OpenApiTypes.BOOL, OpenApiParameter.QUERY,
                description="Només superuser. Inclou edificis desactivats.", required=False),
        ],
        responses={200: "EdificiListSerializer", 401: OpenApiResponse(description="No autenticat.")},
    ),
    retrieve=extend_schema(
        tags=["Edificis"],
        summary="Detall d'un edifici",
        responses={200: "EdificiDetailSerializer", 403: OpenApiResponse(description="Sense permisos."), 404: OpenApiResponse(description="No trobat.")},
    ),
    create=extend_schema(
        tags=["Edificis"],
        summary="Crea un nou edifici",
        description="Només admins de finca o superusers. La vinculació efectiva es produeix un cop aprovada la verificació documental.",
        responses={201: "EdificiDetailSerializer", 400: OpenApiResponse(description="Dades invàlides.")},
    ),
    update=extend_schema(
        tags=["Edificis"],
        summary="Actualitza un edifici (PUT)",
        responses={200: "EdificiDetailSerializer", 400: OpenApiResponse(description="Dades invàlides."), 403: OpenApiResponse(description="Sense permisos.")},
    ),
    partial_update=extend_schema(
        tags=["Edificis"],
        summary="Actualitza parcialment un edifici (PATCH)",
        responses={200: "EdificiDetailSerializer", 400: OpenApiResponse(description="Dades invàlides."), 403: OpenApiResponse(description="Sense permisos.")},
    ),
    destroy=extend_schema(
        tags=["Edificis"],
        summary="Elimina un edifici",
        responses={204: OpenApiResponse(description="Eliminat correctament."), 403: OpenApiResponse(description="Sense permisos.")},
    ),
)

desactivar_schema = extend_schema(
    tags=["Edificis"],
    summary="Desactiva un edifici",
    description=(
        "Sense `?confirmat=true` → **dry-run**: retorna advertències sense executar res.\n\n"
        "Amb `?confirmat=true` → executa la desactivació i registra l'auditoria.\n\n"
        "Requereix rol **admin sistema**."
    ),
    parameters=[
        OpenApiParameter("confirmat", OpenApiTypes.BOOL, OpenApiParameter.QUERY,
            description="Si `true`, executa la desactivació. Si no, dry-run.", required=False),
    ],
    request=DesactivarBodySerializer,
    responses={
        200: OpenApiResponse(response=DesactivarDryRunResponseSerializer,
            description="Dry-run (sense confirmat) o desactivació executada."),
        400: OpenApiResponse(description="L'edifici ja estava desactivat."),
        403: OpenApiResponse(description="Sense permisos (cal admin sistema)."),
    },
)

reactivar_schema = extend_schema(
    tags=["Edificis"],
    summary="Reactiva un edifici desactivat",
    description="Requereix rol **admin sistema**.",
    responses={
        200: OpenApiResponse(response=ReactivarResponseSerializer, description="Edifici reactivat."),
        400: OpenApiResponse(description="L'edifici ja estava actiu."),
        403: OpenApiResponse(description="Sense permisos."),
    },
)

habitatges_schema = extend_schema(
    tags=["Edificis"],
    summary="Llista els habitatges d'un edifici",
    description="Admin finca veu tots. Owner/Tenant veu només els seus.",
    responses={200: "HabitatgeResumSerializer(many=True)"},
)

habitatge_detail_schema = extend_schema(
    tags=["Edificis"],
    summary="Detall d'un habitatge concret d'un edifici",
    parameters=[
        OpenApiParameter("referenciaCadastral", OpenApiTypes.STR, OpenApiParameter.PATH,
            description="Referència cadastral de l'habitatge."),
    ],
    responses={
        200: "HabitatgeDetailSerializer",
        403: OpenApiResponse(description="Sense permisos."),
        404: OpenApiResponse(description="Habitatge no trobat."),
    },
)

dades_energetiques_schema = extend_schema(
    tags=["Edificis"],
    summary="Dades energètiques dels habitatges d'un edifici",
    description="Retorna les dades energètiques filtrades per rol. Admin veu totes; Owner/Tenant les seves.",
    responses={
        200: OpenApiResponse(description="Llista de dades energètiques per habitatge."),
        404: OpenApiResponse(description="No hi ha dades energètiques disponibles."),
    },
)

me_habitatge_schema = extend_schema(
    tags=["Edificis"],
    summary="Actualitza les dades del propi habitatge (PATCH)",
    parameters=[
        OpenApiParameter("referenciaCadastral", OpenApiTypes.STR, OpenApiParameter.PATH),
    ],
    responses={
        200: "HabitatgeMeUpdateSerializer",
        403: OpenApiResponse(description="Sense permisos."),
        404: OpenApiResponse(description="Habitatge no trobat."),
    },
)

simulacions_preview_schema = extend_schema(
    tags=["Simulacions"],
    summary="Preview d'una simulació de millores (sense guardar)",
    description="Calcula l'impacte estimat de les millores seleccionades sense persistir res a la BD.",
    responses={
        200: OpenApiResponse(description="Resultat de la simulació (abans/després + deltes)."),
        400: OpenApiResponse(description="Dades de millores invàlides."),
    },
)

simulacions_schema = extend_schema(
    tags=["Simulacions"],
    summary="Llista o crea simulacions de millores",
    description=(
        "**GET:** Retorna totes les simulacions guardades de l'edifici.\n\n"
        "**POST:** Calcula i guarda una simulació. Retorna el resultat complet amb tots els ítems."
    ),
    responses={
        200: "SimulacioMilloraSerializer(many=True)  [GET]",
        201: "SimulacioMilloraSerializer  [POST]",
        400: OpenApiResponse(description="Dades invàlides."),
    },
)

sotmetre_simulacio_votacio_schema = extend_schema(
    tags=["Votacions"],
    summary="Sotmet una simulació a votació comunitària",
    description=(
        "Crea una `VotacioSimulacioMillora` associada a la simulació i canvia el seu estat a `EN_VOTACIO`.\n\n"
        "Només ho pot fer l'**administrador de finca** de l'edifici.\n\n"
        "La simulació ha d'estar en estat `ESBORRANY` o `REBUTJADA`."
    ),
    responses={
        201: "VotacioSimulacioMilloraSerializer",
        400: OpenApiResponse(description="La simulació ja té votació o estat incorrecte."),
        403: OpenApiResponse(description="Sense permisos."),
        404: OpenApiResponse(description="Simulació no trobada."),
    },
)

votacions_simulacions_schema = extend_schema(
    tags=["Votacions"],
    summary="Llista les votacions de simulacions d'un edifici",
    responses={200: "VotacioSimulacioMilloraSerializer(many=True)"},
)

votar_simulacio_schema = extend_schema(
    tags=["Votacions"],
    summary="Emet un vot en una votació de simulació",
    description=(
        "Registra o actualitza el vot de l'usuari (`A_FAVOR` / `EN_CONTRA` / `ABSTENCIO`).\n\n"
        "La votació ha d'estar en estat `ACTIVA` i no haver superat `dataFi`."
    ),
    responses={
        200: "VotacioSimulacioMilloraSerializer",
        403: OpenApiResponse(description="Sense permisos per votar."),
        409: OpenApiResponse(description="Votació ja tancada o finalitzada."),
    },
)

acreditar_implementacio_schema = extend_schema(
    tags=["Simulacions"],
    summary="Acredita la implementació d'una simulació aprovada",
    description=(
        "L'**administrador de finca** puja les evidències de l'execució real de les millores.\n\n"
        "La simulació ha d'estar en estat `APROVADA`. "
        "La validació final la fa l'admin de sistema a `/millores-implementades/{id}/validar/`."
    ),
    responses={
        201: "MilloraImplementadaSerializer(many=True)",
        400: OpenApiResponse(description="Simulació no aprovada o sense ítems."),
        403: OpenApiResponse(description="Sense permisos."),
    },
)

millores_implementades_schema = extend_schema(
    tags=["Simulacions"],
    summary="Llista les millores implementades d'un edifici",
    responses={200: "MilloraImplementadaSerializer(many=True)"},
)

mapa_schema = extend_schema(
    tags=["Edificis"],
    summary="Edificis en format GeoJSON per al mapa",
    description=(
        "Retorna edificis actius amb coordenades vàlides en format GeoJSON `FeatureCollection`.\n\n"
        "**Query params:**\n"
        "- `scope`: `public` (tots els actius, defecte) | `mine` (els de l'usuari).\n"
        "- `bbox`: `minLng,minLat,maxLng,maxLat` — filtra per bounding box.\n"
        "- `tipologia`: ex. `Residencial`.\n"
        "- `score_min`: puntuació mínima (float).\n"
        "- `q`: cerca per carrer, barri o codi postal.\n"
        "- `limit`: màxim de resultats (1–1000, defecte 500)."
    ),
    parameters=[
        OpenApiParameter("scope",     OpenApiTypes.STR,   OpenApiParameter.QUERY, required=False),
        OpenApiParameter("bbox",      OpenApiTypes.STR,   OpenApiParameter.QUERY, required=False,
            description="Format: minLng,minLat,maxLng,maxLat"),
        OpenApiParameter("tipologia", OpenApiTypes.STR,   OpenApiParameter.QUERY, required=False),
        OpenApiParameter("score_min", OpenApiTypes.FLOAT, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("q",         OpenApiTypes.STR,   OpenApiParameter.QUERY, required=False),
        OpenApiParameter("limit",     OpenApiTypes.INT,   OpenApiParameter.QUERY, required=False),
    ],
    responses={
        200: OpenApiResponse(response=MapaResponseSerializer, description="GeoJSON FeatureCollection."),
        400: OpenApiResponse(description="Paràmetre bbox o score_min invàlid."),
    },
)

cerca_per_carrer_schema = extend_schema(
    tags=["Edificis"],
    summary="Cerca edificis per nom de carrer",
    parameters=[
        OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY,
            description="Text a cercar (mínim 3 caràcters).", required=True),
    ],
    responses={200: "EdificiCercaSerializer(many=True)"},
)

badges_schema = extend_schema(
    tags=["Badges"],
    summary="Insígnies assignades a un edifici",
    description=(
        "Retorna les insígnies actives de l'edifici.\n\n"
        "Amb `?temporada=<id>` retorna les permanents + les d'aquella temporada."
    ),
    parameters=[
        OpenApiParameter("temporada", OpenApiTypes.INT, OpenApiParameter.QUERY,
            description="ID de temporada per filtrar.", required=False),
    ],
    responses={200: OpenApiResponse(response=BadgesResponseSerializer)},
)

recalcular_badges_schema = extend_schema(
    tags=["Badges"],
    summary="Recalcula les insígnies d'un edifici",
    description="Accessible per admin de sistema o administrador de finca de l'edifici.",
    responses={
        200: OpenApiResponse(response=RecalcularBadgesResponseSerializer),
        403: OpenApiResponse(description="Sense permisos."),
    },
)


# ===========================================================================
# MilloraImplementadaViewSet
# ===========================================================================

validar_millora_schema = extend_schema(
    tags=["Millores"],
    summary="Valida o rebutja una millora implementada",
    description=(
        "Canvia l'estat d'una `MilloraImplementada` a `VALIDADA` o `REBUTJADA`.\n\n"
        "Si totes les millores d'una simulació queden validades, la simulació passa a `IMPLEMENTADA`.\n\n"
        "Requereix rol **admin sistema**."
    ),
    responses={
        200: "MilloraImplementadaSerializer",
        400: OpenApiResponse(description="Estat incorrecte per validar."),
        403: OpenApiResponse(description="Sense permisos."),
    },
)


# ===========================================================================
# HabitatgeViewSet
# ===========================================================================

habitatge_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Habitatges"],
        summary="Llista els habitatges de l'usuari",
        responses={200: "HabitatgeResumSerializer(many=True)"},
    ),
    retrieve=extend_schema(
        tags=["Habitatges"],
        summary="Detall d'un habitatge",
        responses={200: "HabitatgeDetailSerializer", 403: OpenApiResponse(description="Sense permisos.")},
    ),
    create=extend_schema(
        tags=["Habitatges"],
        summary="Sol·licita accés a un habitatge",
        description=(
            "Propietaris i llogaters poden sol·licitar vincular-se a un habitatge per referència cadastral.\n\n"
            "Si l'habitatge ja existeix, actualitza la sol·licitud. Si no, el crea."
        ),
        responses={
            200: "HabitatgeDetailSerializer  [habitatge existent actualitzat]",
            201: "HabitatgeDetailSerializer  [habitatge nou creat]",
            400: OpenApiResponse(description="Referència cadastral absent o rol ja ocupat."),
            409: OpenApiResponse(description="Sol·licitud pendent d'un altre usuari."),
        },
    ),
    update=extend_schema(tags=["Habitatges"], summary="Actualitza un habitatge (PUT)"),
    partial_update=extend_schema(tags=["Habitatges"], summary="Actualitza parcialment un habitatge (PATCH)"),
    destroy=extend_schema(tags=["Habitatges"], summary="Elimina un habitatge"),
)

solicitar_acces_schema = extend_schema(
    tags=["Habitatges"],
    summary="Sol·licita vincular-se a un habitatge existent",
    description="Envia una sol·licitud de vinculació com a propietari o llogater. Pendent d'aprovació per l'admin de finca.",
    responses={
        200: OpenApiResponse(response=SolicitudAccesResponseSerializer),
        400: OpenApiResponse(description="Rol ja ocupat."),
        403: OpenApiResponse(description="Sense perfil o rol no permès."),
        409: OpenApiResponse(description="Ja hi ha una sol·licitud pendent."),
    },
)

validar_acces_schema = extend_schema(
    tags=["Habitatges"],
    summary="Aprova o rebutja una sol·licitud d'accés a un habitatge",
    description="Acció exclusiva de l'**administrador de finca** de l'edifici.",
    responses={
        200: OpenApiResponse(description="Sol·licitud aprovada o rebutjada."),
        400: OpenApiResponse(description="Sense sol·licitud pendent o estat invàlid."),
        403: OpenApiResponse(description="Sense permisos."),
    },
)

pendents_schema = extend_schema(
    tags=["Habitatges"],
    summary="Habitatges amb sol·licituds d'accés pendents",
    description="Retorna els habitatges en estat `EN_REVISIO` dels edificis que administra l'usuari.",
    responses={
        200: "HabitatgeDetailSerializer(many=True)",
        403: OpenApiResponse(description="Sense permisos (cal rol admin)."),
    },
)


# ===========================================================================
# CatalegMilloraViewSet
# ===========================================================================

cataleg_millora_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Catàleg de millores"],
        summary="Llista les millores actives del catàleg",
        parameters=[
            OpenApiParameter("categoria", OpenApiTypes.STR, OpenApiParameter.QUERY,
                description="Filtra per categoria de millora.", required=False),
        ],
        responses={200: "CatalegMilloraSerializer(many=True)"},
    ),
    retrieve=extend_schema(
        tags=["Catàleg de millores"],
        summary="Detall d'una millora del catàleg",
        responses={200: "CatalegMilloraSerializer"},
    ),
)


# ===========================================================================
# RankingViewSet
# ===========================================================================

ranking_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Ranking"],
        summary="Ranking global d'edificis per puntuació",
        parameters=[
            OpenApiParameter("liga", OpenApiTypes.STR, OpenApiParameter.QUERY,
                description="Filtra per liga (ex. `oro`, `plata`).", required=False),
        ],
        responses={200: "RankingSerializer(many=True)"},
    ),
    retrieve=extend_schema(
        tags=["Ranking"],
        summary="Detall de posició d'un edifici al ranking",
        responses={200: "RankingSerializer"},
    ),
)

posicion_schema = extend_schema(
    tags=["Ranking"],
    summary="Posició d'un edifici dins la seva lliga",
    parameters=[
        OpenApiParameter("top", OpenApiTypes.INT, OpenApiParameter.QUERY,
            description="Objectiu de top N (defecte 5).", required=False),
    ],
    responses={200: OpenApiResponse(response=PosicioRankingResponseSerializer)},
)


# ===========================================================================
# AdminFincaEdificiAltaView
# ===========================================================================

admin_finca_alta_schema = extend_schema(
    tags=["Administrador de finca"],
    summary="Alta i reclamació d'edifici per part d'un administrador de finca",
    description=(
        "Un administrador de finca (amb verificació documental aprovada) pot reclamar la gestió d'un edifici.\n\n"
        "- Si l'edifici ja existeix i no té admin: s'inicia el procés de verificació.\n"
        "- Si l'edifici no existeix: es crea i s'inicia la verificació.\n"
        "- Si ja té un altre admin assignat: retorna `409 Conflict`."
    ),
    responses={
        200: OpenApiResponse(response=AdminFincaAltaResponseSerializer,
            description="Edifici existent localitzat. Cal verificació documental."),
        201: OpenApiResponse(response=AdminFincaAltaResponseSerializer,
            description="Edifici nou creat. Cal verificació documental."),
        400: OpenApiResponse(description="Dades invàlides."),
        403: OpenApiResponse(description="Compte d'admin pendent de validació o rebutjat."),
        409: OpenApiResponse(description="L'edifici ja té un administrador assignat."),
    },
)


# ===========================================================================
# Funcions auxiliars (APIViews legacy + autocomplete)
# ===========================================================================

edificis_mostrar_schema = extend_schema(
    tags=["Edificis (legacy)"],
    summary="[Legacy] Llista tots els edificis",
    responses={200: "EdificiListSerializer(many=True)"},
)

edifici_crear_schema = extend_schema(
    tags=["Edificis (legacy)"],
    summary="[Legacy] Crea un nou edifici",
    responses={201: "EdificiDetailSerializer", 400: OpenApiResponse(description="Dades invàlides.")},
)

edifici_veure_schema = extend_schema(
    tags=["Edificis (legacy)"],
    summary="[Legacy] Detall d'un edifici",
    responses={200: "EdificiDetailSerializer", 403: OpenApiResponse(description="Sense permisos."), 404: OpenApiResponse(description="No trobat.")},
)

edifici_editar_schema = extend_schema(
    tags=["Edificis (legacy)"],
    summary="[Legacy] Actualitza un edifici (PUT / PATCH)",
    responses={200: "EdificiDetailSerializer", 400: OpenApiResponse(description="Dades invàlides.")},
)

edifici_esborrar_schema = extend_schema(
    tags=["Edificis (legacy)"],
    summary="[Legacy] Elimina un edifici",
    responses={204: OpenApiResponse(description="Eliminat correctament.")},
)

autocomplete_carrers_schema = extend_schema(
    tags=["Utilitats"],
    summary="Suggeriments de carrers per a formularis",
    description=(
        "Cerca tolerant per nom oficial i curt, ignorant stopwords comunes "
        "(`carrer`, `avinguda`, `de`, etc.). Retorna màxim 10 resultats."
    ),
    parameters=[
        OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY,
            description="Text a cercar (mínim 2 caràcters).", required=True),
    ],
    responses={200: AutocompleteCarrerItemSerializer(many=True)},
)