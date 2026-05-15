from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.chat.services import get_stream_client, sync_user_to_stream

User = get_user_model()


class Command(BaseCommand):
    help = "Re-sincronitza tots els usuaris de Django a GetStream (nom, email, rol)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Usuaris processats per lot (default: 100)",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        qs = User.objects.select_related("profile").order_by("id")
        total = qs.count()
        self.stdout.write(f"Sincronitzant {total} usuaris a GetStream...")

        client = get_stream_client()
        ok = 0
        errors = 0

        for i, user in enumerate(qs.iterator(chunk_size=batch_size), start=1):
            try:
                sync_user_to_stream(client, user)
                ok += 1
            except Exception as exc:
                errors += 1
                self.stderr.write(f"  [ERROR] user_id={user.id} ({user.email}): {exc}")

            if i % batch_size == 0 or i == total:
                self.stdout.write(f"  {i}/{total} processats...")

        if errors:
            self.stdout.write(self.style.WARNING(f"Fet: {ok} OK, {errors} errors."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Fet: {ok} usuaris sincronitzats sense errors."))
