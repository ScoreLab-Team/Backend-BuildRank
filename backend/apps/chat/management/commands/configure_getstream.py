import json

from django.core.management.base import BaseCommand

from apps.chat.services import get_stream_client

# Permissions to mirror from channel_member → user (all basic, no moderation/ban)
GRANTS_TO_ADD = [
    "add-links",
    "add-own-channel-membership",
    "cast-vote",
    "create-attachment",
    "create-call",
    "create-mention",
    "create-message",
    "create-reaction",
    "create-reply",
    "flag-message",
    "join-call",
    "mute-channel",
    "notify-channel",
    "notify-group",
    "notify-here",
    "notify-role",
    "pin-message",
    "query-votes",
    "read-channel",
    "read-channel-members",
    "remove-own-channel-membership",
    "run-message-action",
    "send-custom-event",
    "send-poll",
    "share-location-any-team",
    "upload-attachment",
]
LEGACY_RESOURCES_TO_ADD = [
    "AddLinks",
    "AddOwnChannelMembership",
    "CreateCall",
    "CreateMessage",
    "CreateReaction",
    "JoinCall",
    "PinMessage",
    "ReadChannel",
    "ReadChannelMembers",
    "RemoveOwnChannelMembership",
    "RunMessageAction",
    "SendCustomEvent",
    "UploadAttachment",
    "CastVote",
    "QueryVotes",
]


class Command(BaseCommand):
    help = "Configura i/o consulta els permisos del tipus de canal 'messaging' a GetStream"

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Mostra la configuració actual sense modificar-la",
        )

    def handle(self, *args, **options):
        client = get_stream_client()

        if options["check"]:
            self._check(client)
            return

        self._check(client)
        self.stdout.write("")
        self._apply_grants(client)
        self.stdout.write("")
        self._apply_legacy_permissions(client)
        self.stdout.write("")
        self.stdout.write("=== Verificació final ===")
        self._check(client)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def _check(self, client):
        self.stdout.write("=== Configuració actual de 'messaging' ===")
        try:
            resp = client.get_channel_type("messaging")
            data = dict(resp)

            user_grants = data.get("grants", {}).get("user", [])
            self.stdout.write(f"grants['user'] ({len(user_grants)} items):")
            self.stdout.write(json.dumps(sorted(user_grants), indent=2))

            user_legacy = [
                p for p in data.get("permissions", [])
                if "user" in p.get("roles", [])
            ]
            self.stdout.write("permissions (legacy) per al rol 'user':")
            self.stdout.write(json.dumps(user_legacy, indent=2))

        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Error llegint canal type: {exc}"))

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def _apply_grants(self, client):
        """Afegeix read-channel / read-channel-members al rol 'user' en el sistema nou (kebab-case)."""
        self.stdout.write("Actualitzant grants (sistema nou)...")
        try:
            resp = client.get_channel_type("messaging")
            data = dict(resp)
            current_grants = data.get("grants", {})

            user_grants = list(current_grants.get("user", []))
            added = []
            for perm in GRANTS_TO_ADD:
                if perm not in user_grants:
                    user_grants.append(perm)
                    added.append(perm)

            if not added:
                self.stdout.write("  Grants ja presents, res a canviar.")
                return

            updated_grants = {**current_grants, "user": user_grants}
            client.update_channel_type("messaging", grants=updated_grants)
            self.stdout.write(self.style.SUCCESS(f"  Grants afegits: {added}"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  Error: {exc}"))
            raise

    def _apply_legacy_permissions(self, client):
        """Afegeix ReadChannel / ReadChannelMembers al rol 'user' en el sistema legacy (PascalCase)."""
        self.stdout.write("Actualitzant permissions (sistema legacy)...")
        try:
            resp = client.get_channel_type("messaging")
            data = dict(resp)
            permissions = list(data.get("permissions", []))

            # Find the user-role permission entry and patch its resources
            user_perm = next(
                (p for p in permissions if "user" in p.get("roles", []) and not p.get("owner", False)),
                None,
            )

            if user_perm is None:
                # Create a new rule for user role
                permissions.append({
                    "name": "Users can read channels",
                    "action": "Allow",
                    "resources": LEGACY_RESOURCES_TO_ADD,
                    "roles": ["user"],
                    "owner": False,
                    "priority": 65,
                })
                self.stdout.write("  Creada nova regla per al rol 'user'.")
            else:
                resources = list(user_perm.get("resources", []))
                added = []
                for res in LEGACY_RESOURCES_TO_ADD:
                    if res not in resources:
                        resources.append(res)
                        added.append(res)
                user_perm["resources"] = resources

                if not added:
                    self.stdout.write("  Recursos legacy ja presents, res a canviar.")
                    return
                self.stdout.write(f"  Recursos afegits a la regla existent: {added}")

            client.update_channel_type("messaging", permissions=permissions)
            self.stdout.write(self.style.SUCCESS("  Permissions legacy actualitzades."))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  Error: {exc}"))
            raise
