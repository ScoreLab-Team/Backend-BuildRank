"""
Management command: cleanup_stream_users

Detecta usuaris a GetStream que ja no existeixen a Django.
- Sense flags: dry-run, només informa.
- --delete:    hard-delete dels usuaris sobrantes (allibera l'ID).
- --reactivate: reactiva els usuaris soft-deleted perquè tornin a ser usables.

Ús:
    python manage.py cleanup_stream_users
    python manage.py cleanup_stream_users --delete
    python manage.py cleanup_stream_users --reactivate
"""
import time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.chat.services import get_stream_client, get_stream_user_id

User = get_user_model()

_PAGE_SIZE = 100


class Command(BaseCommand):
    help = "Manage surplus GetStream users that have no matching Django user."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--delete",
            action="store_true",
            help="Hard-delete surplus users, freeing their IDs permanently.",
        )
        group.add_argument(
            "--reactivate",
            action="store_true",
            help="Reactivate soft-deleted surplus users (use after accidental soft-delete).",
        )

    def handle(self, *args, **options):
        do_delete = options["delete"]
        do_reactivate = options["reactivate"]
        dry_run = not do_delete and not do_reactivate

        client = get_stream_client()

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "Mode dry-run. Usa --delete o --reactivate per actuar."
            ))

        existing_stream_ids = set(
            get_stream_user_id(u)
            for u in User.objects.only("id").iterator()
        )

        surplus = self._find_surplus_users(client, existing_stream_ids)

        if not surplus:
            self.stdout.write(self.style.SUCCESS("Cap usuari sobrant a GetStream."))
            return

        self.stdout.write(f"Usuaris sobrantes trobats: {len(surplus)}")
        for uid in surplus:
            self.stdout.write(f"  - {uid}")

        if dry_run:
            return

        ok, failed = 0, 0

        for uid in surplus:
            try:
                if do_delete:
                    self._hard_delete(client, uid)
                    self.stdout.write(f"  [OK] hard-deleted {uid}")
                elif do_reactivate:
                    client.reactivate_user(uid)
                    self.stdout.write(f"  [OK] reactivated {uid}")
                ok += 1
                time.sleep(0.1)
            except Exception as exc:
                self.stderr.write(f"  [ERROR] {uid}: {exc}")
                failed += 1

        action = "eliminats" if do_delete else "reactivats"
        self.stdout.write(self.style.SUCCESS(f"Finalitzat: {ok} {action}, {failed} errors."))

    def _hard_delete(self, client, uid):
        # La llibreria requests serialitza True → "True" (majúscula).
        # GetStream espera "true" en minúscula, per això passem strings explícits.
        client.delete_user(uid, **{"hard_delete": "true", "mark_messages_deleted": "true"})

    def _find_surplus_users(self, client, existing_stream_ids):
        surplus = []
        offset = 0

        while True:
            response = client.query_users(
                {"id": {"$gt": ""}},
                sort=[{"field": "id", "direction": 1}],
                **{"limit": _PAGE_SIZE, "offset": offset},
            )
            users = response.get("users", [])
            if not users:
                break

            for u in users:
                uid = u["id"]
                if not uid.startswith("user_"):
                    continue
                if not uid[len("user_"):].isdigit():
                    continue
                if uid not in existing_stream_ids:
                    surplus.append(uid)

            if len(users) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE

        return surplus
