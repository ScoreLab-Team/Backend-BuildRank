from rest_framework import serializers
from .models import Votacio, OpcioVot, Vot


class OpcioVotSerializer(serializers.ModelSerializer):
    num_vots = serializers.SerializerMethodField()

    class Meta:
        model = OpcioVot
        fields = ['id', 'text', 'ordre', 'num_vots']

    def get_num_vots(self, obj):
        return obj.vots.count()


class VotacioCreateSerializer(serializers.ModelSerializer):
    opcions = serializers.ListField(
        child=serializers.CharField(max_length=200),
        min_length=2,
        write_only=True,
    )

    class Meta:
        model = Votacio
        fields = ['id', 'edifici', 'titol', 'descripcio', 'dataLimit', 'opcions']

    def validate_opcions(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Les opcions no poden ser duplicades.")
        return value

    def create(self, validated_data):
        opcions_texts = validated_data.pop('opcions')
        validated_data['creador'] = self.context['request'].user
        votacio = Votacio.objects.create(**validated_data)
        for i, text in enumerate(opcions_texts):
            OpcioVot.objects.create(votacio=votacio, text=text, ordre=i)
        return votacio


class VotacioListSerializer(serializers.ModelSerializer):
    num_vots_total = serializers.SerializerMethodField()

    class Meta:
        model = Votacio
        fields = ['id', 'titol', 'estat', 'dataCreacio', 'dataLimit', 'num_vots_total']

    def get_num_vots_total(self, obj):
        return obj.vots.count()


class VotacioDetailSerializer(serializers.ModelSerializer):
    opcions = OpcioVotSerializer(many=True, read_only=True)
    num_vots_total = serializers.SerializerMethodField()
    ha_votat = serializers.SerializerMethodField()

    class Meta:
        model = Votacio
        fields = [
            'id', 'edifici', 'titol', 'descripcio', 'estat',
            'dataCreacio', 'dataLimit', 'opcions', 'num_vots_total', 'ha_votat',
        ]

    def get_num_vots_total(self, obj):
        return obj.vots.count()

    def get_ha_votat(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.vots.filter(usuari=request.user).exists()
        return False


class EmitreVotSerializer(serializers.Serializer):
    opcio_id = serializers.IntegerField()

    def validate_opcio_id(self, value):
        votacio = self.context['votacio']
        if not votacio.opcions.filter(id=value).exists():
            raise serializers.ValidationError("Opció no vàlida per aquesta votació.")
        return value

    def validate(self, data):
        votacio = self.context['votacio']
        user = self.context['request'].user
        if votacio.estat != 'oberta':
            raise serializers.ValidationError("Aquesta votació no està oberta.")
        if votacio.vots.filter(usuari=user).exists():
            raise serializers.ValidationError("Ja has emès el vot en aquesta votació.")
        return data

    def create(self, validated_data):
        votacio = self.context['votacio']
        user = self.context['request'].user
        opcio = votacio.opcions.get(id=validated_data['opcio_id'])
        return Vot.objects.create(votacio=votacio, opcio=opcio, usuari=user)


class VotacioUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Votacio
        fields = ['titol', 'descripcio', 'dataLimit', 'estat']
        extra_kwargs = {
            'titol': {'required': False},
            'descripcio': {'required': False},
            'dataLimit': {'required': False},
            'estat': {'required': False},
        }

    def validate_estat(self, value):
        current = self.instance.estat if self.instance else None
        if current == 'cancel·lada' and value == 'oberta':
            raise serializers.ValidationError("No es pot reobrir una votació cancel·lada.")
        return value


class ResultatsVotacioSerializer(serializers.ModelSerializer):
    opcions = serializers.SerializerMethodField()
    num_vots_total = serializers.SerializerMethodField()

    class Meta:
        model = Votacio
        fields = ['id', 'titol', 'estat', 'dataLimit', 'num_vots_total', 'opcions']

    def get_num_vots_total(self, obj):
        return obj.vots.count()

    def get_opcions(self, obj):
        total = obj.vots.count()
        result = []
        for opcio in obj.opcions.all():
            count = opcio.vots.count()
            result.append({
                'id': opcio.id,
                'text': opcio.text,
                'num_vots': count,
                'percentatge': round(count / total * 100, 1) if total > 0 else 0.0,
            })
        return result
