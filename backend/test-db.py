# test_db.py
import os
import django
from django.conf import settings
from django.db import connections, OperationalError

# Configurar Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")  # Ajusta si tu settings.py está en otro sitio
django.setup()

# Intentar conectar
db_conn = connections['default']
try:
    c = db_conn.cursor()
    c.execute("SELECT 1;")  # Prueba simple
    print("Conexión a la DB OK")
except OperationalError as e:
    print("No se pudo conectar a la DB")
    print(e)