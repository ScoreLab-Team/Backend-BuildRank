"""
Management command: bump_stream_user_id

Incrementa `chat_stream_id_version` per a un o més usuaris Django, perquè
emetin un nou `user_id` cap a GetStream. Necessari quan el `user_id` previ
ha quedat hard-deleted (tombstoned) a GetStream i no es pot recrear amb el
mateix identificador.

Després de bumpar la versió, l'usuari ha de fer login de nou (o refrescar
el seu token de xat) perquè el front rebi el `user_id` nou i es connecti
com un usuari verge.

Ús:
    python manage.py bump_stream_user_id --emails user1@example.com user2@example.com
    python manage.py bump_stream_user_id --ids 17 23 45
    python manage.py bump_stream_user_id --all-broken   # bumpea tots els usuaris
                                                          # detectats com a
                                                          # tombstoned a GetStream
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.chat.services import get_stream_client, get_stream_user_id

User = get_user_model()


class Command(BaseCommand):
    help = "Bump chat_stream_id_version to give selected users a fresh GetStream user_id."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--emails",
            nargs="+",
            help="Emails dels usuaris a bumpar.",
        )
        group.add_argument(
            "--ids",
            nargs="+",
            type=int,
            help="IDs Django dels usuaris a bumpar.",
        )
        group.add_argument(
            "--all-broken",
            action="store_true",
            help="Detecta automàticament tots els usuaris amb user_id "
            "tombstoned a GetStream i els bumpa.",
        )

    def handle(self, *args, **options):
        if options["all_broken"]:
            users = self._detect_broken_users()
        elif options["emails"]:
            users = list(User.objects.filter(email__in=options["emails"]))
            missing = set(options["emails"]) - {u.email for u in users}
            if missing:
                self.stdout.write(self.style.WARNING(
                    f"Emails no trobats: {', '.join(missing)}"
                ))
        else:
            users = list(User.objects.filter(id__in=options["ids"]))
            missing = set(options["ids"]) - {u.id for u in users}
            if missing:
                self.stdout.write(self.style.WARNING(
                    f"IDs no trobats: {', '.join(map(str, missing))}"
                ))

        if not users:
            self.stdout.write("Cap usuari per processar.")
            return

        with transaction.atomic():
            for user in users:
                old_uid = get_stream_user_id(user)
                user.chat_stream_id_version = (user.chat_stream_id_version or 1) + 1
                user.save(update_fields=["chat_stream_id_version"])
                new_uid = get_stream_user_id(user)
                self.stdout.write(self.style.SUCCESS(
                    f"  {user.email} (id={user.id}): {old_uid} -> {new_uid}"
                ))

        self.stdout.write(self.style.SUCCESS(
            f"\nBumped {len(users)} usuari(s). Recorda dir-los que tanquin i "
            f"reobrin sessió perquè es reconnectin amb el nou user_id."
        ))

    def _detect_broken_users(self):
        """Detecta usuaris Django amb el seu actual user_id tombstoned a GetStream."""
        client = get_stream_client()
        broken = []
        for user in User.objects.iterator():
            uid = get_stream_user_id(user)
            try:
                resp = client.query_users({"id": uid})
                stream_user = (resp.get("users") or [None])[0]
                if stream_user and stream_user.get("deleted_at"):
                    broken.append(user)
                    self.stdout.write(f"  detectat tombstoned: {user.email} ({uid})")
            except Exception as exc:
                self.stdout.write(self.style.WARNING(
                    f"  no s'ha pogut consultar {uid}: {exc}"
                ))
        return broken
