class Edifici:
    def __init__(self, id_edifici: str, any_construccio: int, tipologia: str,
                 superficie_total: float, reglament: str, orientacio_principal: str,
                 puntuacio_base: float):
        self._id_edifici = id_edifici
        self._any_construccio = any_construccio
        self._tipologia = tipologia
        self._superficie_total = superficie_total
        self._reglament = reglament
        self._orientacio_principal = orientacio_principal
        self._puntuacio_base = puntuacio_base

        self._habitatges = []
        self._localitzacio = None

    def __str__(self):
        return (
            f"Edifici {self.id_edifici}\n"
            f"  Any construcció: {self.any_construccio}\n"
            f"  Tipologia: {self.tipologia}\n"
            f"  Superfície total: {self.superficie_total} m²\n"
            f"  Habitatges: {len(self.habitatges)}"
        )
    
    # Getters
    @property
    def id_edifici(self):
        return self._id_edifici

    @property
    def any_construccio(self):
        return self._any_construccio

    @property
    def tipologia(self):
        return self._tipologia

    @property
    def superficie_total(self):
        return self._superficie_total

    @property
    def habitatges(self):
        return self._habitatges

    # Setters
    @tipologia.setter
    def tipologia(self, valor):
        if valor not in ["Residencial", "Comercial", "Mixt"]:
            raise ValueError("Tipologia no válida")
        self._tipologia = valor

    @superficie_total.setter
    def superficie_total(self, valor):
        if valor < 0:
            raise ValueError("Superficie total no puede ser negativa")
        self._superficie_total = valor

    # Métodos de relación
    def afegir_habitatge(self, habitatge):
        self._habitatges.append(habitatge)

    def set_localitzacio(self, localitzacio):
        self._localitzacio = localitzacio