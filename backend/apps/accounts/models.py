from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.accounts.managers import UserManager


class RoleChoices(models.TextChoices):
    ADMIN = "admin", "Administrador"
    OWNER = "owner", "Propietari"
    TENANT = "tenant", "Llogater"

class ValidacioAdmin(models.TextChoices):
    PENDENT = "pendent", "Pendent de validació"
    APROVAT = "aprovat", "Aprovat"
    REBUTJAT = "rebutjat", "Rebutjat"


class AccountStatus(models.TextChoices):
    ACTIVE = "active", "Actiu"
    BLOCKED = "blocked", "Bloquejat"
    SUSPENDED = "suspended", "Suspès"

class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    class AuthProvider(models.TextChoices):
        PASSWORD = "password", "Password"
        GOOGLE = "google", "Google"

    auth_provider = models.CharField(
        max_length=20,
        choices=AuthProvider.choices,
        default=AuthProvider.PASSWORD,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.OWNER,
    )

    # Validació Admin de Finca
    estatValidacioAdmin = models.CharField(
        max_length=50,
        choices=ValidacioAdmin.choices,
        default=ValidacioAdmin.PENDENT,
    )

    documentPadro = models.FileField(
        upload_to='documents_admin/',
        null = True,
        blank=True,
        help_text="Document acreditatiu de l'administrador de finca."
    )

    avatar = models.ImageField(
        upload_to="avatars/",
        null=True,
        blank=True,
        help_text="Imatge/avatar del perfil de l'usuari."
    )

    account_status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
        db_index=True,
    )
    suspension_reason = models.TextField(blank=True)
    suspended_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Null indica suspensió indefinida. Ignorat si account_status != suspended.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.role} ({self.estatValidacioAdmin})"

    @property
    def is_access_allowed(self):
        """Retorna True si l'usuari pot accedir al sistema."""
        if self.account_status == AccountStatus.BLOCKED:
            return False
        if self.account_status == AccountStatus.SUSPENDED:
            from django.utils import timezone
            return self.suspended_until is not None and self.suspended_until <= timezone.now()
        return True


class TokenLoginLog(models.Model):
    """
    Registro de auditoría de logins/logouts para análisis de patrones de acceso.
    Se mantiene separado de los tokens activos (OutstandingToken/BlacklistedToken) 
    para evitar impacto en performance y tener histórico limpio.
    """
    LOGIN = 'login'
    LOGOUT = 'logout'
    EXPIRED = 'expired'
    REVOKED = 'revoked'
    
    STATUS_CHOICES = [
        (LOGIN, 'Login'),
        (LOGOUT, 'Logout'),
        (EXPIRED, 'Expirado'),
        (REVOKED, 'Revocado'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='token_login_logs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    login_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    logout_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    jti = models.CharField(max_length=255, unique=True, db_index=True)
    
    class Meta:
        ordering = ['-login_at']
        verbose_name_plural = 'Token Login Logs'
        indexes = [
            models.Index(fields=['user', '-login_at']),
            models.Index(fields=['status', '-login_at']),
        ]
    
    def __str__(self):
        return f"{self.user.email} – {self.status} @ {self.login_at}"


class AccessDenialLog(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='access_denials',
    )
    role = models.CharField(max_length=20, blank=True)
    edifici_sol_licitat = models.CharField(max_length=50, blank=True)
    accio = models.CharField(max_length=100)
    motiu = models.CharField(max_length=255)
    ip = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp}] {self.role} → {self.accio} – {self.motiu}"