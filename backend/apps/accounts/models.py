from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.accounts.managers import UserManager


class RoleChoices(models.TextChoices):
    ADMIN = "admin", "Administrador"
    OWNER = "owner", "Propietari"
    TENANT = "tenant", "Llogater"

class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.role}"


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