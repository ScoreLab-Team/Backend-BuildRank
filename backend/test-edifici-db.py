import os
import django

# 🔹 Configuración Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.buildings.models import Localitzacio, Edifici
from django.db import connection

# 🔹 Leer una fila de la tabla raw
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            "NUM_CAS", "ADREÇA", "NUMERO", "ESCALA", "PIS", "PORTA", 
            "CODI_POSTAL", "POBLACIO", "COMARCA", "NOM_PROVINCIA", 
            "CODI_POBLACIO", "CODI_COMARCA", "CODI_PROVINCIA", 
            "ANY_CONSTRUCCIO", "ZONA CLIMATICA", "METRES_CADASTRE"
        FROM energia_certificats_raw
        LIMIT 1
    """)
    row = cursor.fetchone()

# 🔹 Mapear columnas a variables
(
    num_cas, adreca, numero, escala, pis, porta,
    codi_postal, poblacio, comarca, nom_provincia,
    codi_poblacio, codi_comarca, codi_provincia,
    any_construccio, zona_climatica, metres_cadastre
) = row

# 🔹 Crear objeto Localitzacio en memoria
localitzacio = Localitzacio(
    carrer=adreca,
    numero=int(numero) if numero else 0,
    codi_postal=codi_postal,
    barri=comarca,
    latitud=0.0,   # si no hay lat/lon en raw
    longitud=0.0,
    zona_climatica=zona_climatica or ""
)

# 🔹 Crear objeto Edifici en memoria
edifici = Edifici(
    id_edifici=num_cas,  # usar NUM_CAS como id
    any_construccio=int(any_construccio) if any_construccio else None,
    tipologia="Residencial",  # ejemplo, puedes mapear según US_EDIFICI si quieres
    superficie_total = float(metres_cadastre.replace(",", ".")) if metres_cadastre else 0.0,
    reglament="manual",
    orientacio_principal="N",
    puntuacio_base=0,
    localitzacio=localitzacio
)

# 🔹 Imprimir para verificar
print("==== LOCALITZACIO ====")
print(f"Carrer: {localitzacio.carrer}, Número: {localitzacio.numero}")
print(f"Codi Postal: {localitzacio.codi_postal}, Barri: {localitzacio.barri}")
print(f"Zona climàtica: {localitzacio.zona_climatica}")

print("\n==== EDIFICI ====")
print(f"ID: {edifici.id_edifici}")
print(f"Año construcció: {edifici.any_construccio}")
print(f"Tipologia: {edifici.tipologia}")
print(f"Superficie total: {edifici.superficie_total} m²")
print(f"Reglament: {edifici.reglament}")
print(f"Orientació: {edifici.orientacio_principal}")
print(f"Puntuació base: {edifici.puntuacio_base}")
print(f"Localització: {edifici.localitzacio}")