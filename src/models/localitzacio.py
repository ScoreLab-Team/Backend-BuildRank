class Localitzacio:
    def __init__(
        self, 
        carrer: str,
        numero: int,
        codi_postal: str,
        barri: str,
        latitud: float,
        longitud: float,
        zona_climatica: str
    ):
        self.carrer = carrer
        self.numero = numero
        self.codi_postal = codi_postal
        self.barri = barri
        self.latitud = latitud
        self.longitud = longitud
        self.zona_climatica = zona_climatica