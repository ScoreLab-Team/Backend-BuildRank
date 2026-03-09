class DadesEnergetiques:
    def __init__(
        self,
        qualificacio_global: str,  # LletraEnergetica
        consum_energia_primaria: float,
        consum_energia_final: float,
        emissions_co2: float,
        cost_anual_energia: float
    ):
        self.qualificacio_global = qualificacio_global
        self.consum_energia_primaria = consum_energia_primaria
        self.consum_energia_final = consum_energia_final
        self.emissions_co2 = emissions_co2
        self.cost_anual_energia = cost_anual_energia

        # Energías específicas
        self.energia_calefaccio = 0.0
        self.energia_refrigeracio = 0.0
        self.energia_acs = 0.0
        self.energia_enllumenament = 0.0
    
    def __str__(self):
        return (
            f"DadesEnergetiques:\n"
            f"  Qualificació global: {self.qualificacio_global}\n"
            f"  Consum energia primaria: {self.consum_energia_primaria}\n"
            f"  Consum energia final: {self.consum_energia_final}\n"
            f"  Emissions CO2: {self.emissions_co2}\n"
            f"  Cost anual energia: {self.cost_anual_energia}\n"
            f"  Energia calefaccio: {self.energia_calefaccio}\n"
            f"  Energia refrigeracio: {self.energia_refrigeracio}\n"
            f"  Energia ACS: {self.energia_acs}\n"
            f"  Energia enllumenament: {self.energia_enllumenament}"
        )