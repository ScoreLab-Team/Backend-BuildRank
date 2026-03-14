import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.buildings.models import Localitzacio, Edifici, TipusEdifici
from django.db import connection

def run_seed():
    print("Iniciant el procés de Seed des de la taula RAW...")
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                "NUM_CAS", "ADREÇA", "NUMERO", "CODI_POSTAL", "POBLACIO", "COMARCA", 
                "ANY_CONSTRUCCIO", "ZONA CLIMATICA", "METRES_CADASTRE"
            FROM energia_certificats_raw
            LIMIT 20
        """)
        rows = cursor.fetchall()

    for row in rows:
        (num_cas, adreca, numero, cp, poblacio, comarca, any_c, zona, metres) = row

        try:
            net_metres = float(metres.replace(",", ".")) if isinstance(metres, str) else float(metres or 0)
            net_any = int(any_c) if any_c and str(any_c).isdigit() else 2000

            # 1. Localitzacio
            loc, _ = Localitzacio.objects.get_or_create(
                carrer=adreca,
                numero=int(numero) if (numero and str(numero).isdigit()) else 0,
                codiPostal=cp or "08000",
                defaults={
                    'barri': comarca or "",
                    'latitud': 0.0,
                    'longitud': 0.0,
                    'zonaClimatica': zona or ""
                }
            )

            # 2. Edifici
            edifici, created = Edifici.objects.get_or_create(
                idEdifici=num_cas,
                defaults={
                    'anyConstruccio': net_any,
                    'tipologia': TipusEdifici.RESIDENCIAL,
                    'superficieTotal': net_metres,
                    'orientacioPrincipal': 'Nord',
                    'puntuacioBase': 0
                }
            )
        
            edifici.localitzacio = loc
            edifici.save()
        
            if created: print(f"Edifici {num_cas} creat.")

        except Exception as e:
            print("Error a {num_cas}: {e}")

if __name__ == "__main__":
    run_seed()