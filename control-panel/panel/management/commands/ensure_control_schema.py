from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Create the isolated PostgreSQL schema and migration recorder for this panel."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("The Control Panel requires PostgreSQL.")
        schema = settings.CONTROL_SCHEMA
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            cursor.execute(
                f'CREATE TABLE IF NOT EXISTS "{schema}"."django_migrations" '
                "(id serial PRIMARY KEY, app varchar(255) NOT NULL, "
                "name varchar(255) NOT NULL, applied timestamp with time zone NOT NULL, "
                "UNIQUE (app, name))"
            )
        self.stdout.write(self.style.SUCCESS(f"Isolated schema {schema} is ready."))
