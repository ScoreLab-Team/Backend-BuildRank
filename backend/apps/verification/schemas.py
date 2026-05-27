# apps/verification/schemas.py
"""
Decoradors @extend_schema per a la documentació OpenAPI del mòdul de verificació.
Importa'ls directament a views.py per mantenir les vistes netes.
"""

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiExample,
    inline_serializer,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers


# ---------------------------------------------------------------------------
# Respostes reutilitzables
# ---------------------------------------------------------------------------

_R401 = OpenApiResponse(description="No autenticat. Cal proporcionar credencials vàlides.")
_R403 = OpenApiResponse(description="Sense permisos. Només accessible per AdminFinca o AdminSistema.")
_R404 = OpenApiResponse(description="Verificació no trobada.")

_R409_STATUS = OpenApiResponse(
    description="Conflicte d'estat. La verificació no es troba en estat 'review'.",
    response=inline_serializer(
        name="ConflicteEstatSerializer",
        fields={
            "detail": serializers.CharField(
                help_text="Descripció de l'error de conflicte."
            ),
            "status_actual": serializers.CharField(
                help_text="Estat actual de la verificació (p.ex. 'pending', 'running', 'approved', 'rejected')."
            ),
        },
    ),
)


# ---------------------------------------------------------------------------
# Respostes de detall per a la revisió manual
# ---------------------------------------------------------------------------

_R200_APROVADA = OpenApiResponse(
    description="Verificació aprovada correctament.",
    response=inline_serializer(
        name="AprovadaResponseSerializer",
        fields={
            "detail": serializers.CharField(
                help_text="Missatge de confirmació de l'aprovació."
            ),
            "edifici": serializers.IntegerField(
                help_text="ID de l'edifici associat a la verificació."
            ),
            "administrador_assignat": serializers.EmailField(
                help_text="Correu electrònic de l'administrador de finca verificat."
            ),
        },
    ),
    examples=[
        OpenApiExample(
            name="Aprovació correcta",
            value={
                "detail": "Verificació #42 aprovada.",
                "edifici": 7,
                "administrador_assignat": "admin@finca.cat",
            },
        )
    ],
)

_R200_REBUTJADA = OpenApiResponse(
    description="Verificació rebutjada correctament.",
    response=inline_serializer(
        name="RebutjadaResponseSerializer",
        fields={
            "detail": serializers.CharField(
                help_text="Missatge de confirmació del rebuig."
            ),
            "motiu": serializers.CharField(
                help_text="Motiu indicat per l'operador que ha rebutjat la verificació."
            ),
        },
    ),
    examples=[
        OpenApiExample(
            name="Rebuig correcte",
            value={
                "detail": "Verificació #42 rebutjada.",
                "motiu": "El document aportat és il·legible.",
            },
        )
    ],
)

_R400_REVISIO = OpenApiResponse(
    description=(
        "Dades invàlides. Pot ser perquè 'accio' no és 'aprovar' ni 'rebutjar', "
        "o perquè s'ha intentat rebutjar sense indicar 'motiu'."
    ),
    response=inline_serializer(
        name="ErrorRevisioSerializer",
        fields={
            "detail": serializers.CharField(
                help_text="Descripció de l'error de validació."
            ),
        },
    ),
    examples=[
        OpenApiExample(
            name="Acció invàlida",
            value={"detail": "El camp 'accio' ha de ser 'aprovar' o 'rebutjar'."},
        ),
        OpenApiExample(
            name="Motiu absent en rebuig",
            value={"detail": "Cal indicar un 'motiu' quan es rebutja una verificació."},
        ),
    ],
)


# ---------------------------------------------------------------------------
# Body de la revisió manual (inline)
# ---------------------------------------------------------------------------

_REVISIO_REQUEST_SERIALIZER = inline_serializer(
    name="RevisioRequestSerializer",
    fields={
        "accio": serializers.ChoiceField(
            choices=["aprovar", "rebutjar"],
            help_text="Acció a aplicar sobre la verificació.",
        ),
        "motiu": serializers.CharField(
            required=False,
            help_text=(
                "Motiu del rebuig. Obligatori si 'accio' és 'rebutjar'; "
                "ignorat si 'accio' és 'aprovar'."
            ),
        ),
    },
)


# ---------------------------------------------------------------------------
# Schema: AdminFincaDocumentVerificationCreateView
# ---------------------------------------------------------------------------

verification_create_schema = extend_schema(
    tags=["Verificació"],
    summary="Crear una nova verificació documental",
    description=(
        "Crea una nova sol·licitud de verificació d'administrador de finca per a un edifici concret. "
        "S'han d'adjuntar entre 1 i 10 documents (PDF, JPEG, PNG o WEBP, màxim 10 MB cadascun). "
        "Cada fitxer ha d'anar acompanyat del seu tipus declarat (`documents_doc_type`).\n\n"
        "Un cop creada la verificació, es llança automàticament el pipeline asíncron de Celery "
        "que executa OCR, extracció estructurada via LLM i scoring. La verificació transitarà pels "
        "estats `pending` → `running` → `review` (o `rejected` si el pipeline falla de manera definitiva).\n\n"
        "**Restricció:** No es pot crear una nova verificació si ja n'existeix una en curs "
        "(`pending`, `running` o `review`) per al mateix usuari i edifici."
    ),
    request={
        "multipart/form-data": inline_serializer(
            name="VerificationCreateMultipartSerializer",
            fields={
                "edifici": serializers.IntegerField(
                    help_text="ID de l'edifici per al qual es sol·licita la verificació."
                ),
                "documents_fitxer": serializers.ListField(
                    child=serializers.FileField(),
                    help_text=(
                        "Llista de fitxers a adjuntar. "
                        "Formats acceptats: PDF, JPEG, PNG, WEBP. Mida màxima: 10 MB per fitxer."
                    ),
                ),
                "documents_doc_type": serializers.ListField(
                    child=serializers.CharField(),
                    required=False,
                    help_text=(
                        "Tipus declarat per a cada fitxer, en el mateix ordre que `documents_fitxer`. "
                        "Valors possibles: `acta_junta`, `certificat`, `contracte`, `cert_col`, "
                        "`identificatiu`, `factura`, `desconegut`."
                    ),
                ),
            },
        )
    },
    responses={
        201: OpenApiResponse(
            description="Verificació creada correctament. El pipeline asíncron ja ha estat llançat.",
        ),
        400: OpenApiResponse(
            description=(
                "Error de validació. Possibles causes: cap fitxer adjuntat, "
                "més de 10 documents, tipus de fitxer no permès, mida superior a 10 MB, "
                "nombre de fitxers i tipus que no coincideix, o verificació en curs existent."
            ),
        ),
        401: _R401,
        403: _R403,
    },
    examples=[
        OpenApiExample(
            name="Sol·licitud multipart (exemple de camps)",
            value={
                "edifici": 3,
                "documents_fitxer": ["<fitxer_1.pdf>", "<fitxer_2.jpg>"],
                "documents_doc_type": ["certificat", "identificatiu"],
            },
            request_only=True,
        ),
    ],
)


# ---------------------------------------------------------------------------
# Schema: AdminFincaDocumentVerificationListView
# ---------------------------------------------------------------------------

verification_list_schema = extend_schema(
    tags=["Verificació"],
    summary="Llistar verificacions documentals",
    description=(
        "Retorna la llista de verificacions documentals paginada.\n\n"
        "- **AdminSistema**: veu totes les verificacions del sistema.\n"
        "- **AdminFinca**: veu únicament les seves pròpies verificacions.\n\n"
        "Cada element inclou el detall de l'usuari, l'edifici, els documents adjunts i el resultat "
        "de la verificació si ja s'ha processat."
    ),
    responses={
        200: OpenApiResponse(description="Llista de verificacions obtinguda correctament."),
        401: _R401,
        403: _R403,
    },
)


# ---------------------------------------------------------------------------
# Schema: AdminFincaDocumentVerificationDetailView
# ---------------------------------------------------------------------------

verification_detail_schema = extend_schema(
    tags=["Verificació"],
    summary="Obtenir el detall d'una verificació",
    description=(
        "Retorna el detall complet d'una verificació documental: informació de l'usuari, "
        "l'edifici, tots els documents adjunts (amb text OCR i dades extretes), "
        "el resultat agregat i el scoring calculat.\n\n"
        "- **AdminSistema**: pot consultar qualsevol verificació.\n"
        "- **AdminFinca**: només pot consultar les seves pròpies verificacions."
    ),
    parameters=[
        OpenApiParameter(
            name="id",
            location=OpenApiParameter.PATH,
            type=OpenApiTypes.INT,
            description="Identificador únic de la verificació.",
        )
    ],
    responses={
        200: OpenApiResponse(description="Detall de la verificació obtingut correctament."),
        401: _R401,
        403: _R403,
        404: _R404,
    },
)


# ---------------------------------------------------------------------------
# Schema: VerificacioRevisioView
# ---------------------------------------------------------------------------

verificacio_revisio_schema = extend_schema(
    tags=["Verificació"],
    summary="Aprovar o rebutjar una verificació (revisió manual)",
    description=(
        "Permet a un **AdminSistema** (superusuari) aprovar o rebutjar una verificació "
        "que es trobi en estat `review` (revisió manual pendent).\n\n"
        "En cas d'aprovació, s'assigna l'administrador de finca a l'edifici corresponent. "
        "En cas de rebuig, cal indicar obligatòriament un motiu que quedarà registrat.\n\n"
        "**Estats possibles de la verificació:**\n"
        "- `pending` — pendent de processament\n"
        "- `running` — pipeline en execució\n"
        "- `review` — pendent de revisió manual, únic estat des del qual es pot revisar\n"
        "- `approved` — aprovada\n"
        "- `rejected` — rebutjada"
    ),
    parameters=[
        OpenApiParameter(
            name="id",
            location=OpenApiParameter.PATH,
            type=OpenApiTypes.INT,
            description="Identificador únic de la verificació a revisar.",
        )
    ],
    request=_REVISIO_REQUEST_SERIALIZER,
    responses={
        200: OpenApiResponse(
            description="Decisió aplicada. Consulta els exemples per veure el cos de resposta.",
            response=inline_serializer(
                name="RevisioOkSerializer",
                fields={
                    "detail": serializers.CharField(),
                    "edifici": serializers.IntegerField(required=False),
                    "administrador_assignat": serializers.EmailField(required=False),
                    "motiu": serializers.CharField(required=False),
                },
            ),
        ),
        400: _R400_REVISIO,
        401: _R401,
        403: _R403,
        404: _R404,
        409: _R409_STATUS,
    },
    examples=[
        OpenApiExample(
            name="Aprovació",
            value={"accio": "aprovar"},
            request_only=True,
        ),
        OpenApiExample(
            name="Rebuig amb motiu",
            value={"accio": "rebutjar", "motiu": "El certificat aportat ha caducat."},
            request_only=True,
        ),
        OpenApiExample(
            name="Resposta aprovació",
            value={
                "detail": "Verificació #42 aprovada.",
                "edifici": 7,
                "administrador_assignat": "admin@finca.cat",
            },
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            name="Resposta rebuig",
            value={
                "detail": "Verificació #42 rebutjada.",
                "motiu": "El certificat aportat ha caducat.",
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)