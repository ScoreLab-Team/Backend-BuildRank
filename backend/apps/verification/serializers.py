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
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Serializer de creació
# ---------------------------------------------------------------------------

class AdminFincaDocumentVerificationCreateSerializer(serializers.ModelSerializer):
    """
    Escriptura: rep edifici + llista de {fitxer, doc_type}.
    L'usuari s'extreu del request (no s'exposa al payload).

    Validacions:
    - Mínim 1 document, màxim 10
    - Cada fitxer: PDF/JPEG/PNG/WEBP, màx 10 MB
    - No pot haver-hi una verificació PENDING o RUNNING activa pel mateix edifici
    """

    documents = DocumentInputSerializer(
        many=True,
        write_only=True,
    )

    class Meta:
        model = AdminFincaDocumentVerification
        fields = ['edifici', 'documents']

    def validate_documents(self, value):
        if len(value) < 1:
            raise serializers.ValidationError(
                "Cal adjuntar almenys un document."
            )
        if len(value) > 10:
            raise serializers.ValidationError(
                "No es poden pujar més de 10 documents per verificació."
            )
        return value

    def validate(self, attrs):
        user = self.context['request'].user
        edifici = attrs['edifici']

        active_statuses = [
            AdminFincaDocumentVerification.Status.PENDING,
            AdminFincaDocumentVerification.Status.RUNNING,
        ]
        if AdminFincaDocumentVerification.objects.filter(
            user=user,
            edifici=edifici,
            status__in=active_statuses,
        ).exists():
            raise serializers.ValidationError(
                "Ja tens una verificació en curs per aquest edifici. "
                "Espera que es resolgui abans de pujar nous documents."
            )
        return attrs

    def create(self, validated_data):
        documents_data = validated_data.pop('documents')
        user = self.context['request'].user

        verification = AdminFincaDocumentVerification.objects.create(
            user=user,
            **validated_data,
        )

        for doc_data in documents_data:
            AdminFincaVerificationDocument.objects.create(
                verification=verification,
                fitxer=doc_data['fitxer'],
                doc_type=doc_data['doc_type'],  # ← declarat per l'usuari
            )

        return verification