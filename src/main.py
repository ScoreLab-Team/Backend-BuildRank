from fixtures.edifici_exemple import crear_edifici_exemple
from scoring.buildingHealthScore import calcular_building_health_score

def main():
    edifici = crear_edifici_exemple()
    print("=== EDIFICI ===")
    print(edifici)

    print("\n=== HABITATGES ===")
    for idx, h in enumerate(edifici.habitatges, 1):
        print(f"\nHabitatge #{idx}")
        print(h)

        # Calcular BHS
        resultat = calcular_building_health_score(h.dades_energetiques)
        print(f"BHS: {resultat['score']:.2f} (v{resultat['version']})")
        print(f"Pesos aplicats: {resultat['pesos']}")

if __name__ == "__main__":
    main()