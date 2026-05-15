r"""
Management command para limpiar tokens expirados.
Acciones:
1. Marca tokens expirados en TokenLoginLog como 'expired'
2. Ejecuta flushexpiredtokens de simplejwt para limpiar OutstandingToken/BlacklistedToken
3. Registra en log el resultado
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from apps.accounts.models import TokenLoginLog


class Command(BaseCommand):
    help = "Limpia tokens expirados de OutstandingToken y actualiza TokenLoginLog"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== Iniciando limpieza de tokens ==="))
        
        # 1. Marcar logins sin logout y expirados en TokenLoginLog
        now = timezone.now()
        updated = TokenLoginLog.objects.filter(
            status=TokenLoginLog.LOGIN,
            logout_at__isnull=True,
            expires_at__lt=now
        ).update(status=TokenLoginLog.EXPIRED)
        
        self.stdout.write(f"✓ Marcados {updated} tokens como expirados en TokenLoginLog")
        
        # 2. Limpiar OutstandingToken y BlacklistedToken de simplejwt
        try:
            call_command("flushexpiredtokens", verbosity=0)
            self.stdout.write(self.style.SUCCESS("✓ Tokens expirados eliminados de OutstandingToken/BlacklistedToken"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error al limpiar simplejwt: {e}"))
        
        total_logs = TokenLoginLog.objects.count()
        active_logins = TokenLoginLog.objects.filter(status=TokenLoginLog.LOGIN, logout_at__isnull=True).count()
        
        self.stdout.write(self.style.SUCCESS(f"\n=== Limpieza completada ==="))
        self.stdout.write(f"Total registros TokenLoginLog: {total_logs}")
        self.stdout.write(f"Sesiones activas (sin logout): {active_logins}")
