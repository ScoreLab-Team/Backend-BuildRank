# main.py
from fixtures.edifici_exemple import crear_edifici_exemple

def main():
    # Crear edificio de ejemplo
    edifici = crear_edifici_exemple()

    # Imprimir info general del edificio
    print("=== INFORMACIÓ EDIFICI ===")
    print(edifici)

    # Separador
    print("\n=== HABITATGES ===")

    # Imprimir todos los habitatges y sus dades energètiques
    for idx, h in enumerate(edifici.habitatges, start=1):
        print(f"\nHabitatge #{idx}")
        print(h)

if __name__ == "__main__":
    main()