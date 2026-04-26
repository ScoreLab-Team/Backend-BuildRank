# apps/buildings/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

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
    PENDENT_DOCUMENTACIO = 'PendentDocumentacio', 'Pendent de documentació'
    EN_REVISIO = 'EnRevisió', 'En revisió'
    VALIDADA = 'Validada', 'Validada'
    REBUTJADA = 'Rebutjada', 'Rebutjada'

# --- US20: Accions d'auditoria possibles ---
class AccioAudit(models.TextChoices):
    DESACTIVAR  = 'DESACTIVAR',  'Desactivar'
    REACTIVAR   = 'REACTIVAR',   'Reactivar'
    CREAR       = 'CREAR',       'Crear'
    ACTUALITZAR = 'ACTUALITZAR', 'Actualitzar'
    ELIMINAR    = 'ELIMINAR',    'Eliminar'
 
# --- EPIC 4
class AmbitActuacio(models.TextChoices):
    # En quina part de l'edifici s'aplica la millora
    HABITATGE = 'Privat', 'Habitatge privat'
    COMU = 'Comu', 'Element comú'
    EDIFICI = 'Edifici', 'Edifici complet'

class TipusAcord(models.TextChoices):
    NO_CAL = 'No cal', 'No sol requerir acord'
    MAJORIA_SIMPLE = 'MajoriaSimple', 'Majoria simple'
    MAJORIA_3_5 = 'Majoria35', 'Majoria de 3/5'
    UNANIMITAT = 'Unanimitat', 'Unanimitat'

class NivellConfianca(models.TextChoices):
    # com de fiables o exactes són els càlculs de la millora
    BAIX = 'Baix', 'Baix'
    MIG = 'Mig', 'Mig'
    ALT = 'Alt', 'Alt'

class CategoriaMillora(models.TextChoices):
    ENVOLUPANT = 'envolupant', 'Envolupant tèrmica'
    INSTAL_LACIO_TERMICA = 'instal_lacio_termica', 'Instal·lació tèrmica'
    RENOVABLES = 'renovables', 'Energies renovables'
    ELECTRICITAT = 'electricitat', 'Electricitat'
    MOBILITAT = 'mobilitat', 'Mobilitat'
    CONTROL_MONITORATGE = 'control_i_monitoratge', 'Control i monitoratge'

class UnitatBaseMillora(models.TextChoices):
    M2 = 'm2', 'm²'
    UNITAT = 'unitat', 'Unitat'
    KWP = 'kwp', 'kWp'
    KWH = 'kwh', 'kWh'
    HABITATGE = 'habitatge', 'Habitatge'
    EDIFICI = 'edifici', 'Edifici'

class Localitzacio(models.Model):
    carrer = models.CharField(max_length=255)
    numero = models.IntegerField()
    codiPostal = models.CharField(max_length=10)
    barri = models.CharField(max_length=100)
    latitud = models.FloatField(null=True, blank=True)
    longitud = models.FloatField(null=True, blank=True)
    zonaClimatica = models.CharField(max_length=10, null=True, blank=True)

    def __str__(self):
        return f"{self.carrer}, {self.numero} ({self.codiPostal})"
    def save(self, *args, **kwargs):
        # Si la zona climática no está definida, poner un valor por defecto
        if not self.zonaClimatica:
            self.zonaClimatica = "N/A"

        # Si latitud o longitud no están definidas, poner 0.0
        if self.latitud is None:
            self.latitud = 0.0
        if self.longitud is None:
            self.longitud = 0.0

        super().save(*args, **kwargs)


class GrupComparable(models.Model):
    idGrup = models.IntegerField()
    zonaClimatica = models.CharField(max_length=10)
    tipologia = models.CharField(max_length=20, choices=TipusEdifici.choices)
    rangSuperficie = models.CharField(max_length=100)

    def __str__(self):
        return f"Grup Comparable {self.idGrup}"


class EdificiActiuManager(models.Manager):
    """Retorna només edificis actius (no desactivats lògicament)."""
    def get_queryset(self):
        return super().get_queryset().filter(actiu=True)


class Edifici(models.Model):
    # Django crea automaticament l'id de Edifici.
    idEdifici = models.AutoField(primary_key=True)
    anyConstruccio = models.IntegerField()
    tipologia = models.CharField(max_length=20, choices=TipusEdifici.choices)
    superficieTotal = models.FloatField()
    nombrePlantes = models.IntegerField(default=1)
    reglament = models.CharField(max_length=100)
    orientacioPrincipal = models.CharField(max_length=50, choices=TipusOrientacio.choices)
    puntuacioBase = models.FloatField(editable=False, null=True)

    actiu = models.BooleanField(default=True)
    dataDesactivacio = models.DateTimeField(null=True, blank=True)
    motivDesactivacio = models.TextField(blank=True)

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

    # relacio 1..* a 0..1
    grupComparable = models.ForeignKey(
        GrupComparable,
        on_delete=models.PROTECT,
        related_name='edificis',
        null=True,
        blank=True
    )

    objects = models.Manager()  # opcional: Per defecte 
    actius = EdificiActiuManager() # Manager personalitzat per només retornar edificis actius

    def __str__(self):
        return f"Edifici{self.idEdifici} - {self.localitzacio}"
    
    def save(self, *args, **kwargs):
        # Calcul de exemple.
        if self.superficieTotal:
            self.puntuacioBase = self.superficieTotal * 0.1

        super().save(*args, **kwargs)


class EdificiAuditLog(models.Model):
    """
    Registra cada operació rellevant sobre un Edifici:
    desactivació, reactivació, creació, actualització, eliminació.
 
    - camps_modificats: JSON amb {nom_camp: [valor_anterior, valor_nou]}
      Permet reconstruir l'historial complet de canvis.
    - edifici_id_snapshot: guarda l'id fins i tot si l'edifici s'elimina físicament.
    """
    edifici = models.ForeignKey(
        Edifici,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    # Snapshot de l'id per si l'edifici s'esborra físicament en el futur
    edifici_id_snapshot = models.IntegerField()
 
    accio = models.CharField(max_length=20, choices=AccioAudit.choices)
    usuari = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs_edificis'
    )
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
 
    # {nom_camp: [valor_anterior, valor_nou]}  — null per a CREAR/ELIMINAR
    camps_modificats = models.JSONField(null=True, blank=True)
 
    motiu = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
 
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Registre d\'auditoria d\'edifici'
        verbose_name_plural = 'Registres d\'auditoria d\'edificis'
 
    def __str__(self):
        return (
            f"[{self.timestamp:%Y-%m-%d %H:%M}] "
            f"{self.accio} · Edifici {self.edifici_id_snapshot} "
            f"· {self.usuari}"
        )


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
        return f"{self.edifici} - {self.planta}, {self.porta}"


class BuildingHealthScore(models.Model):
    edificio = models.ForeignKey(
        'Edifici', on_delete=models.CASCADE, related_name='bhs_history'
    )
    version = models.CharField(max_length=10)
    score = models.FloatField()
    pesos = models.JSONField()  # guarda los pesos usados en la versión
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"BHS {self.score} v{self.version} para Edificio {self.edificio.idEdifici}"

   
class Normativa(models.Model):
    codi = models.CharField(max_length=50)
    nom = models.CharField(max_length=255)
    urlReferencia = models.URLField(blank=True)

    def __str__(self):
        return self.codi


class AjudaVigent(models.Model):
    titol = models.CharField(max_length=255)
    organisme = models.CharField(max_length=100)
    percentatgeMax = models.FloatField()
    activa = models.BooleanField(default=True)
    dataLimit = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.titol


class CatalegMillora(models.Model):
    idMillora = models.AutoField(primary_key=True)

    # Identificació funcional
    slug = models.SlugField(
        max_length=120,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Identificador estable per seeds, frontend i motor de simulació."
    )
    nom = models.CharField(max_length=255)
    descripcio = models.TextField(blank=True)
    categoria = models.CharField(
        max_length=100,
        choices=CategoriaMillora.choices,
        default=CategoriaMillora.ENVOLUPANT
    )
    activa = models.BooleanField(default=True)

    # Bloc econòmic antic conservat per compatibilitat
    costMinim = models.FloatField(default=0)
    costMaxim = models.FloatField(default=0)
    roiEstimatAnys = models.FloatField(null=True, blank=True)
    estalviEnergeticEstimat = models.FloatField(help_text="% d'estalvi", default=0.0)
    impactePunts = models.FloatField(help_text="Punts que aporta al rànquing", default=0.0)
    nivellConfianca = models.CharField(
        max_length=10,
        choices=NivellConfianca.choices,
        default=NivellConfianca.MIG
    )

    # Bloc nou per US29: catàleg parametritzable
    unitatBase = models.CharField(
        max_length=30,
        choices=UnitatBaseMillora.choices,
        default=UnitatBaseMillora.EDIFICI
    )
    costEstimatBase = models.FloatField(
        default=0,
        help_text="Cost orientatiu per unitat base. No és pressupost oficial."
    )
    mantenimentAnual = models.FloatField(
        default=0,
        help_text="Cost orientatiu anual de manteniment per unitat base."
    )
    vidaUtil = models.IntegerField(
        default=0,
        help_text="Vida útil orientativa en anys."
    )
    parametresBase = models.JSONField(
        default=dict,
        blank=True,
        help_text="Paràmetres tècnics simplificats que utilitza el motor de simulació."
    )

    # Bloc legal
    ambit = models.CharField(
        max_length=20,
        choices=AmbitActuacio.choices,
        default=AmbitActuacio.EDIFICI
    )
    requereixAcordComunitat = models.BooleanField(default=False)
    tipusAcordEstimat = models.CharField(
        max_length=20,
        choices=TipusAcord.choices,
        default=TipusAcord.NO_CAL
    )
    requereixLlicenciaMunicipal = models.BooleanField(default=False)
    requereixTecnicCompetent = models.BooleanField(default=False)
    requereixCeePrePost = models.BooleanField(
        default=False,
        help_text="Certificat Energètic abans i després"
    )

    # Relacions
    normativaAplicable = models.ManyToManyField(Normativa, blank=True)
    ajudesDisponibles = models.ManyToManyField(AjudaVigent, blank=True)

    bloquejadorsFrequents = models.JSONField(
        default=list,
        blank=True,
        help_text="Ex: Edifici protegit, façana catalogada."
    )

    class Meta:
        ordering = ['categoria', 'nom']
        verbose_name = 'Millora del catàleg'
        verbose_name_plural = 'Catàleg de millores'

    def __str__(self):
        return self.nom

    @property
    def cost_orientatiu_unitari(self):
        """
        Retorna el cost base preferent.
        Si encara no s'ha migrat el catàleg nou, usa la mitjana costMinim/costMaxim.
        """
        if self.costEstimatBase:
            return self.costEstimatBase

        if self.costMinim and self.costMaxim:
            return (self.costMinim + self.costMaxim) / 2

        if self.costMaxim:
            return self.costMaxim

        return self.costMinim or 0

   
class SimulacioMillora(models.Model):
    descripcio = models.CharField(max_length=255, blank=True)
    reduccioConsumPrevista = models.FloatField(default=0)
    reduccioEmissionsPrevista = models.FloatField(default=0)
    costEstimat = models.FloatField(default=0)
    estalviAnual = models.FloatField(default=0)
    dataSimulacio = models.DateField(auto_now_add=True)

    versioMotor = models.CharField(max_length=20, default="SIM-1.0")
    resultat = models.JSONField(
        default=dict,
        blank=True,
        help_text="Resultat complet de la simulació: abans, després, deltes i hipòtesis."
    )

    hipotesiBase = models.JSONField(
        null=True,
        blank=True,
        help_text="Còpia de les dades energètiques en el moment de la simulació."
    )

    # Es manté nullable per compatibilitat amb la versió antiga d'una sola millora
    millora = models.ForeignKey(
        CatalegMillora,
        on_delete=models.SET_NULL,
        related_name='simulacions_directes',
        null=True,
        blank=True
    )

    edifici = models.ForeignKey(
        Edifici,
        on_delete=models.CASCADE,
        related_name='simulacions'
    )

    creadaPer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='simulacions_millores'
    )

    def __str__(self):
        return f"Simulació millores edifici {self.edifici.idEdifici} - {self.dataSimulacio}"


class SimulacioMilloraItem(models.Model):
    simulacio = models.ForeignKey(
        SimulacioMillora,
        on_delete=models.CASCADE,
        related_name='items'
    )
    millora = models.ForeignKey(
        CatalegMillora,
        on_delete=models.PROTECT,
        related_name='items_simulacio'
    )

    quantitat = models.FloatField(
        null=True,
        blank=True,
        help_text="Quantitat aplicada. Si és null, el motor en fa una estimació segons unitatBase."
    )
    coberturaPercent = models.FloatField(
        default=100,
        help_text="Percentatge d'aplicació de la millora sobre l'edifici o sistema afectat."
    )

    costEstimatParcial = models.FloatField(default=0)
    reduccioConsumParcial = models.FloatField(default=0)
    reduccioEmissionsParcial = models.FloatField(default=0)
    impactePuntsParcial = models.FloatField(default=0)
    resultatParcial = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.millora.nom} ({self.coberturaPercent}%)"


class MilloraImplementada(models.Model):
    # id = models.CharField(max_length=255)
    dataExecucio = models.DateField()
    costReal = models.FloatField()
    documentacioAdjunta = models.FileField(upload_to='documents_millores/', blank=True, null=True)
    estatValidacio = models.CharField(max_length=20, choices=EstatValidacio.choices, default=EstatValidacio.PENDENT_DOCUMENTACIO)
    observacionsAdmin = models.TextField(blank=True, help_text="Motiu del rebutj o indicacions")

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


class carrersBarcelona(models.Model):
    codi_via = models.AutoField(primary_key=True)                # serial4
    codi_carrer_ine = models.CharField(max_length=50, null=True, blank=True)  # varchar50
    tipus_via = models.CharField(max_length=50)                  # varchar50
    nom_curt = models.CharField(max_length=100)                  # varchar100
    nom_oficial = models.CharField(max_length=150)               # varchar150
    nre_min = models.IntegerField(null=True, blank=True)  # Pemetre que sigui null perquè no tots els carrers tenen número mínim
    nre_max = models.IntegerField(null=True, blank=True)  # Pemetre que sigui null perquè no tots els carrers tenen número máxim

    def __str__(self):
        return f"{self.tipus_via} {self.nom_oficial}"