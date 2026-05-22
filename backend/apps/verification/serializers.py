# apps/verification/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from apps.buildings.models import Edifici

from .models import (
    AdminFincaDocumentVerification,
    AdminFincaVerificationDocument,
    AdminFincaVerificationResult,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Sub-serializer per a cada document en el moment de la creació
# ---------------------------------------------------------------------------

class DocumentInputSerializer(serializers.Serializer):
    """
    Representa un parell (fitxer + tipus declarat per l'usuari).
    Usat exclusivament dins de AdminFincaDocumentVerificationCreateSerializer.

    Flutter ha d'enviar multipart amb aquesta estructura per cada document:
        documents[0][fitxer]   = <binary>
        documents[0][doc_type] = "certificat"
        documents[1][fitxer]   = <binary>
        documents[1][doc_type] = "acta_junta"
    """

    ALLOWED_CONTENT_TYPES = {
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/webp',
    }
    MAX_SIZE_MB = 10

    fitxer = serializers.FileField()
    doc_type = serializers.ChoiceField(
        choices=AdminFincaVerificationDocument.DocType.choices,
        help_text="Tipus de document declarat per l'usuari.",
    )

    def validate_fitxer(self, value):
        if value.content_type not in self.ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError(
                f"Tipus de fitxer no permès: '{value.content_type}'. "
                f"Utilitza PDF, JPEG, PNG o WEBP."
            )
        if value.size > self.MAX_SIZE_MB * 1024 * 1024:
            raise serializers.ValidationError(
                f"El fitxer '{value.name}' supera els {self.MAX_SIZE_MB} MB."
            )
        return value


# ---------------------------------------------------------------------------
# Serializers de lectura
# ---------------------------------------------------------------------------

class AdminFincaVerificationDocumentSerializer(serializers.ModelSerializer):
    """Lectura d'un document individual."""

    doc_type_display = serializers.CharField(
        source='get_doc_type_display',
        read_only=True,
    )

    class Meta:
        model = AdminFincaVerificationDocument
        fields = [
            'id',
            'fitxer',
            'doc_type',
            'doc_type_display',
            'ocr_text',
            'extracted_data',
            'confidence',
            'created_at',
        ]
        read_only_fields = fields


class AdminFincaVerificationResultSerializer(serializers.ModelSerializer):

    class Meta:
        model = AdminFincaVerificationResult
        fields = [
            'id',
            'confidence',
            'nom_detectat',
            'dni_detectat',
            'carrec_detectat',
            'comunitat_detectada',
            'vigencia_detectada',
            'explicacio',
            'reviewed_by',
            'reviewed_at',
            'created_at',
        ]
        read_only_fields = fields

class VerificationUserDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'first_name',
            'last_name',
            'email',
        ]
        read_only_fields = fields


class VerificationEdificiDetailSerializer(serializers.ModelSerializer):
    localitzacio = serializers.SerializerMethodField()
    adreca = serializers.SerializerMethodField()

    class Meta:
        model = Edifici
        fields = [
            'idEdifici',
            'localitzacio',
            'adreca',
        ]
        read_only_fields = fields

    def get_localitzacio(self, obj):
        loc = getattr(obj, 'localitzacio', None)

        if loc is None:
            return None

        return {
            'carrer': loc.carrer,
            'numero': loc.numero,
            'codiPostal': loc.codiPostal,
            'barri': loc.barri,
        }

    def get_adreca(self, obj):
        loc = getattr(obj, 'localitzacio', None)

        if loc is None:
            return f"Edifici {obj.idEdifici}"

        carrer = loc.carrer or ''
        numero = loc.numero
        codi_postal = loc.codiPostal or ''

        base = carrer.strip()

        if numero is not None:
            base = f"{base}, {numero}".strip(', ')

        if codi_postal:
            return f"{base} ({codi_postal})".strip()

        return base or f"Edifici {obj.idEdifici}"

class AdminFincaDocumentVerificationSerializer(serializers.ModelSerializer):
    """Serialitzador de lectura complet: inclou documents i resultat."""

    documents = AdminFincaVerificationDocumentSerializer(many=True, read_only=True)
    result = AdminFincaVerificationResultSerializer(read_only=True)

    user_detail = VerificationUserDetailSerializer(source='user', read_only=True)
    edifici_detail = VerificationEdificiDetailSerializer(source='edifici', read_only=True)

    class Meta:
        model = AdminFincaDocumentVerification
        fields = [
            'id',
            'user',
            'user_detail',
            'edifici',
            'edifici_detail',
            'status',
            'celery_task_id',
            'documents',
            'result',
            'created_at',
            'updated_at',
            'score',
            'score_flags',
            'suggeriment',
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Serializer de creació
# ---------------------------------------------------------------------------

class AdminFincaDocumentVerificationCreateSerializer(serializers.ModelSerializer):
    """
    Escriptura: rep edifici + llistes paral·leles de fitxers i tipus.

    Camp recomanat:
        edifici              = 1
        documents_fitxer     = <file1>
        documents_fitxer     = <file2>
        documents_doc_type   = identificatiu
        documents_doc_type   = certificat

    Per compatibilitat temporal també s'accepta:
        documents_doctype
    """

    documents_fitxer = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
    )

    documents_doc_type = serializers.ListField(
        child=serializers.ChoiceField(
            choices=AdminFincaVerificationDocument.DocType.choices
        ),
        write_only=True,
        required=False,
    )

    documents_doctype = serializers.ListField(
        child=serializers.ChoiceField(
            choices=AdminFincaVerificationDocument.DocType.choices
        ),
        write_only=True,
        required=False,
    )

    class Meta:
        model = AdminFincaDocumentVerification
        fields = [
            'edifici',
            'documents_fitxer',
            'documents_doc_type',
            'documents_doctype',
        ]

    def validate(self, attrs):
        fitxers = attrs.get('documents_fitxer', [])

        # Nom nou recomanat. Si no arriba, acceptem el nom antic.
        doctypes = attrs.get('documents_doc_type') or attrs.get('documents_doctype') or []

        if not fitxers:
            raise serializers.ValidationError("Cal adjuntar almenys un document.")

        if len(fitxers) > 10:
            raise serializers.ValidationError("Màxim 10 documents per verificació.")

        if not doctypes:
            raise serializers.ValidationError(
                "Cal indicar el tipus de cada document amb 'documents_doc_type'."
            )

        if len(fitxers) != len(doctypes):
            raise serializers.ValidationError(
                f"El nombre de fitxers ({len(fitxers)}) i de tipus "
                f"({len(doctypes)}) ha de coincidir."
            )
        allowed = {'application/pdf', 'image/jpeg', 'image/png', 'image/webp'}
        for f in fitxers:
            if f.content_type not in allowed:
                raise serializers.ValidationError(
                    f"Tipus no permès: {f.content_type}"
                )
            if f.size > 10 * 1024 * 1024:
                raise serializers.ValidationError(
                    f"'{f.name}' supera els 10 MB."
                )

        user = self.context['request'].user
        edifici = attrs['edifici']
        actives = [
            AdminFincaDocumentVerification.Status.PENDING,
            AdminFincaDocumentVerification.Status.RUNNING,
            AdminFincaDocumentVerification.Status.REVIEW,
        ]

        if AdminFincaDocumentVerification.objects.filter(
            user=user,
            edifici=edifici,
            status__in=actives,
        ).exists():
            raise serializers.ValidationError(
                "Ja tens una verificació en curs per aquest edifici."
            )

        # Normalitzem internament a un únic nom.
        attrs['documents_doc_type'] = doctypes
        attrs.pop('documents_doctype', None)

        return attrs

    def create(self, validated_data):
        fitxers = validated_data.pop('documents_fitxer')
        doctypes = validated_data.pop('documents_doc_type')
        user = self.context['request'].user

        verification = AdminFincaDocumentVerification.objects.create(
            user=user,
            **validated_data,
        )

        for fitxer, doctype in zip(fitxers, doctypes):
            AdminFincaVerificationDocument.objects.create(
                verification=verification,
                fitxer=fitxer,
                doc_type=doctype,
            )
        return verification