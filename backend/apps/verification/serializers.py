from rest_framework import serializers

from .models import AdminFincaDocumentVerification, AdminFincaVerificationDocument, AdminFincaVerificationResult


class AdminFincaVerificationDocumentSerializer(serializers.ModelSerializer):
   """Serialitzador per a cada document dins d'una verificació."""

   class Meta:
      model = AdminFincaVerificationDocument
      fields = ['id','fitxer','doc_type','ocr_text','extracted_data','confidence','created_at']
      read_only_fields = [
         'id',
         'doc_type',
         'ocr_text',
         'extracted_data',
         'confidence',
         'created_at',
      ]


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
   """Serialitzador de lectura: inclou documents i resultat."""

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


class AdminFincaDocumentVerificationCreateSerializer(serializers.ModelSerializer):
   """Serialitzador d'escriptura: rep edifici_id + llista de fitxers, el usuari s'extreu de la sol·licitud.
      Es qui crea la instància de AdminFincaDocumentVerification i els AdminFincaVerificationDocument associats.
   """

   fitxers = serializers.ListField(
      child=serializers.FileField(),
      write_only=True,
      min_length=1,
      max_length=10,
      help_text='Un o més fitxers (PDF o imatge).',
   )

   class Meta:
      model = AdminFincaDocumentVerification
      fields = ['edifici', 'fitxers']

   def validate_fitxers(self, fitxers):
      allowed_types = {
         'application/pdf',
         'image/jpeg',
         'image/png',
         'image/webp',
      }
      max_size_mb = 10
      for fitxer in fitxers:
         if fitxer.content_type not in allowed_types:
               raise serializers.ValidationError(
                  f"Tipus de fitxer no permès: {fitxer.content_type}. "
                  f"Utilitza PDF, JPEG, PNG o WEBP."
               )
         if fitxer.size > max_size_mb * 1024 * 1024:
               raise serializers.ValidationError(
                  f"El fitxer '{fitxer.name}' supera els {max_size_mb} MB."
               )
      return fitxers

   def create(self, validated_data):
      fitxers = validated_data.pop('fitxers')
      user = self.context['request'].user

      verification = AdminFincaDocumentVerification.objects.create(
         user=user,
         **validated_data,
      )

      for fitxer in fitxers:
         AdminFincaVerificationDocument.objects.create(
               verification=verification,
               fitxer=fitxer,
         )

      return verification