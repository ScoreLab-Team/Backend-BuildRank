# apps/buildings/models.py
from django.db import models
from django.conf import settings

class TipusEdifici(models.TextChoices):
    RESIDENCIAL = 'Residencial', 'Residencial'
    COMERCIAL = 'Comercial', 'Comercial'
    SANITARI = 'Sanitari', 'Sanitari'
    EDUCATIU = 'Educatiu', 'Educatiu'
    MIXT = 'Mixt', 'Mixt'

class TipusOrientacio(models.TextChoices):
    NORD = 'Nord', 'Nord'
    SUD = 'Sud', 'Sud'
    EST = 'Est', 'Est'
    OEST = 'Oest', 'Oest'

class LletraEnergetica(models.TextChoices):
    A = 'A', 'A'
    B = 'B', 'B'
    C = 'C', 'C'
    D = 'D', 'D'
    E = 'E', 'E'
    F = 'F', 'F'
    G = 'G', 'G'

class EstatValidacio(models.TextChoices):
    EN_PROCES = 'EnProces', 'En procés'
    VALIDADA = 'Validada', 'Validada'
    REBUTJADA = 'Rebutjada', 'Rebutjada'

class Localitzacio(models.Model):
    carrer = models.CharField(max_length=255)
    numero = models.IntegerField()
    codiPostal = models.CharField(max_length=10)
    barri = models.CharField(max_length=100)
    latitud = models.FloatField()
    longitud = models.FloatField()
    zonaClimatica = models.CharField(max_length=10)

    def __str__(self):
        return f"{self.carrer}, {self.numero} ({self.codiPostal})"
    
class GrupComparable(models.Model):
    idGrup = models.IntegerField()
    zonaClimatica = models.CharField(max_length=10)
    tipologia = models.CharField(max_length=20, choices=TipusEdifici.choices)
    rangSuperficie = models.CharField(max_length=100)

    def __str__(self):
        return f"Grup Comparable {self.idGrup}"
    

class Edifici(models.Model):
    idEdifici = models.CharField(max_length=50, primary_key=True)
    anyConstruccio = models.IntegerField()
    tipologia = models.CharField(max_length=20, choices=TipusEdifici.choices)
    superficieTotal = models.FloatField()
    nombrePlantes = models.IntegerField(default=1)
    reglament = models.CharField(max_length=100)
    orientacioPrincipal = models.CharField(max_length=50, choices=TipusOrientacio.choices)
    puntuacioBase = models.FloatField()

    # relacio 1 a 1: un edifici te una unica localitzacio
    localitzacio = models.OneToOneField(
        Localitzacio, 
        on_delete=models.CASCADE, 
        related_name='edifici', 
        null=True, 
        blank=True
    )

    # relacio 1..* a 0..1
    administradorFinca = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='edificis_administrats'
    )

    # relacio 1..* a 1
    grupComparable = models.ForeignKey(
        GrupComparable,
        on_delete=models.PROTECT,
        related_name='edificis'
    )

    def __str__(self):
        return f"Edifici{self.idEdifici} - {self.tipologia}"
    


class DadesEnergetiques(models.Model):
    qualificacioGlobal = models.CharField(max_length=1, choices=LletraEnergetica.choices)
    consumEnergiaPrimaria = models.FloatField()
    consumEnergiaFinal = models.FloatField()
    emissionsCO2 = models.FloatField()
    costAnualEnergia = models.FloatField()

    energiaCalefaccio = models.FloatField()
    energiaRefrigeracio = models.FloatField()
    energiaACS = models.FloatField()
    energiaEnllumenament = models.FloatField()

    emissionsCalefaccio = models.FloatField()
    emissionsRefrigeracio = models.FloatField()
    emissionsACS = models.FloatField()
    emissionsEnllumenament = models.FloatField()

    aillamentTermic = models.FloatField()
    valorFinestres = models.FloatField()

    normativa = models.CharField(max_length=255)
    einaCertificacio = models.CharField(max_length=255)
    motiuCertificacio = models.CharField(max_length=255)
    rehabilitacioEnergetica = models.BooleanField(default=False)
    dataEntrada = models.DateField()

    def __str__(self):
        return f"Qualificacio {self.qualificacioGlobal} - Data entrada: {self.dataEntrada}"


class Habitatge(models.Model):
    referenciaCadastral = models.CharField(max_length=50, primary_key=True)
    planta = models.CharField(max_length=10)
    porta = models.CharField(max_length=10)
    superficie = models.FloatField()
    anyReforma = models.IntegerField(null=True, blank=True)
    
    # relacio 1 a *: un edifici pot tenir molts habitatges
    edifici = models.ForeignKey(
        Edifici,
        on_delete=models.CASCADE,
        related_name='habitatges'
    )

    ''' # relacio 0..1 a * '''
    usuari = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='habitatges_on_resideix'
    )

    # relacio amb DadesEnergetiques (relacio 1 a 1)
    dadesEnergetiques = models.OneToOneField(
        DadesEnergetiques, 
        on_delete=models.CASCADE, 
        related_name='dades_energetiques', 
        null=True, 
        blank=True
    )

    def __str__(self):
        return f"Habitatge{self.referenciaCadastral} ({self.planta}-{self.porta})"
    

class CatalegMillora(models.Model):
    idMillora = models.AutoField(primary_key=True)
    nom = models.CharField(max_length=255)
    descripcio = models.TextField(blank=True)
    categoria = models.CharField(max_length=100)
    impactePunts = models.FloatField(help_text="Punts que aporta al rànquing")
    parametres = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.nom} ({self.categoria})"
    
class SimulacioMillora(models.Model):
    descripcio = models.CharField(max_length=255)
    reduccioConsumPrevista = models.FloatField()
    reduccioEmissionsPrevista = models.FloatField()
    costEstimat = models.FloatField()
    estalviAnual = models.FloatField()
    dataSimulacio = models.DateField(auto_now_add=True)

    # relacio 1 a *: una millora pot tenir moltes simulacions
    millora = models.ForeignKey(
        CatalegMillora,
        on_delete=models.CASCADE,
        related_name='simulacions'
    )

    # relacio 1 a *: una simulació es fa sobre un edifici
    edifici = models.ForeignKey(
        Edifici,
        on_delete=models.CASCADE,
        related_name='simulacions'
    )

    def __str__(self):
        return f"Simulació {self.millora.nom} a {self.edifici.idEdifici}"


class MilloraImplementada(models.Model):
    # id = models.CharField(max_length=255)
    dataExecucio = models.DateField()
    costReal = models.FloatField()
    documentacioAdjunta = models.FileField(upload_to='documents_millores/', blank=True, null=True)
    estatValidacio = models.CharField(max_length=20, choices=EstatValidacio.choices, default=EstatValidacio.EN_PROCES)

    # relacio 1 a *: una millora pot tenir moltes millores implementades
    millora = models.ForeignKey(
        CatalegMillora,
        on_delete=models.CASCADE,
        related_name='implementacions'
    )

    # relacio 1 a *: un edifici pot tenir moltes millores implementades
    edifici = models.ForeignKey(
        Edifici,
        on_delete=models.CASCADE,
        related_name='implementacions'
    )

    # relacio 1 a 0..1: una millora implementada es validada per un administrador de finca
    administradorFinca = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='validacions',
        null=True,
        blank=True
    )

    def __str__(self):
        return f"Implementació {self.millora.nom} a {self.edifici.idEdifici}"