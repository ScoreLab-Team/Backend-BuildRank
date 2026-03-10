from typing import Optional
from models.dadesEnergetiques import DadesEnergetiques

class Habitatge:
   def __init__(
      self,
      referencia_cadastral: str,
      planta: str,
      porta: str,
      superficie: float,
      any_reforma: Optional[int] = None
   ):
      self.referencia_cadastral = referencia_cadastral
      self.planta = planta
      self.porta = porta
      self.superficie = superficie
      self.any_reforma = any_reforma

      # Relaciones
      self.dades_energetiques: Optional['DadesEnergetiques'] = None
      # self.resident: Optional['Usuari'] = None

   def set_dades_energetiques(self, dades: 'DadesEnergetiques'):
      self.dades_energetiques = dades
   
   # def assignar_resident(self, usuari: 'Usuari'):
   #  self.resident = usuari
   def __str__(self):
      dades_str = f"\n{self.dades_energetiques}" if self.dades_energetiques else ""
      return (
         f"Habitatge {self.planta}{self.porta}:\n"
         f"  Referencia cadastral: {self.referencia_cadastral}\n"
         f"  Superficie: {self.superficie}\n"
         f"  Any reforma: {self.any_reforma if self.any_reforma else 'N/A'}"
         f"{dades_str}"
      )