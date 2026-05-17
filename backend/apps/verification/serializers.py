# apps/verification/serializers.py
from rest_framework import serializers

from .models import (
    AdminFincaDocumentVerification,
    AdminFincaVerificationDocument,
    AdminFincaVerificationResult,
)


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


class AdminFincaDocumentVerificationSerializer(serializers.ModelSerializer):
    """Serialitzador de lectura complet: inclou documents i resultat."""

    documents = AdminFincaVerificationDocumentSerializer(many=True, read_only=True)
    result = AdminFincaVerificationResultSerializer(read_only=True)

    class Meta:
        model = AdminFincaDocumentVerification
        fields = [
            'id',
            'user',
            'edifici',
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
 
    Postman / Flutter han d'enviar:
        edifici               = 1
        documents_fitxer      = <file1>
        documents_fitxer      = <file2>
        documents_doctype     = identificatiu
        documents_doctype     = certificat
    """
 
    documents_fitxer  = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
    )
    documents_doctype = serializers.ListField(
        child=serializers.ChoiceField(
            choices=AdminFincaVerificationDocument.DocType.choices
        ),
        write_only=True,
    )
 
    class Meta:
        model = AdminFincaDocumentVerification
        fields = ['edifici', 'documents_fitxer', 'documents_doctype']
 
    def validate(self, attrs):
        fitxers  = attrs.get('documents_fitxer', [])
        doctypes = attrs.get('documents_doctype', [])
 
        if not fitxers:
            raise serializers.ValidationError("Cal adjuntar almenys un document.")
        if len(fitxers) > 10:
            raise serializers.ValidationError("Màxim 10 documents per verificació.")
        if len(fitxers) != len(doctypes):
            raise serializers.ValidationError(
                f"El nombre de fitxers ({len(fitxers)}) i de tipus "
                f"({len(doctypes)}) ha de coincidir."
            )
 
        # Valida cada fitxer
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
 
        # Verifica que no hi ha verificació activa pel mateix edifici
        user    = self.context['request'].user
        edifici = attrs['edifici']
        actives = [
            AdminFincaDocumentVerification.Status.PENDING,
            AdminFincaDocumentVerification.Status.RUNNING,
        ]
        if AdminFincaDocumentVerification.objects.filter(
            user=user, edifici=edifici, status__in=actives
        ).exists():
            raise serializers.ValidationError(
                "Ja tens una verificació en curs per aquest edifici."
            )
 
        return attrs
 
    def create(self, validated_data):
        fitxers  = validated_data.pop('documents_fitxer')
        doctypes = validated_data.pop('documents_doctype')
        user     = self.context['request'].user
 
        verification = AdminFincaDocumentVerification.objects.create(
            user=user, **validated_data
        )
        for fitxer, doctype in zip(fitxers, doctypes):
            AdminFincaVerificationDocument.objects.create(
                verification=verification,
                fitxer=fitxer,
                doc_type=doctype,
            )
        return verification