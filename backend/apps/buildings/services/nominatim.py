# apps/buildings/services/nominatim.py
import time
import logging
import requests

logger = logging.getLogger(__name__)

NOMINATIM_URL     = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_HEADERS = {"User-Agent": "BuildingHealthScoreApp/1.0"}

# Bounding box de Barcelona ciutat (lat_min, lat_max, lng_min, lng_max).
# Fallback geomètric quan Nominatim no retorna city="Barcelona".
BARCELONA_BOUNDS = (41.320, 41.470, 2.069, 2.228)

# Política d'ús Nominatim: màxim 1 req/s.
NOMINATIM_MIN_INTERVAL = 1.1  # segons


class NominatimRateLimiter:
    """
    Controla que no es facin més d'1 crida/segon a Nominatim.
    Instancia-la una vegada per bulk i passa-la a reverse_geocode.
    """
    def __init__(self):
        self._last_call = 0.0

    def wait(self):
        elapsed = time.monotonic() - self._last_call
        if elapsed < NOMINATIM_MIN_INTERVAL:
            time.sleep(NOMINATIM_MIN_INTERVAL - elapsed)
        self._last_call = time.monotonic()


def reverse_geocode(lat: float, lng: float, rate_limiter: NominatimRateLimiter) -> dict | None:
    """
    Crida Nominatim reverse geocoding respectant el rate limit.
    Retorna el dict 'address' de la resposta, o None si falla.
    """
    rate_limiter.wait()

    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"lat": lat, "lon": lng, "format": "json", "addressdetails": 1},
            headers=NOMINATIM_HEADERS,
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("address", {})
    except Exception as exc:
        logger.warning("Nominatim error per (%s, %s): %s", lat, lng, exc)
        return None


def es_barcelona(address: dict, lat: float, lng: float) -> bool:
    """
    Comprova si les coordenades pertanyen a Barcelona.
    Estratègia doble:
      1. El camp city/town/municipality de Nominatim conté "Barcelona".
      2. Fallback: les coordenades estan dins el bounding box de la ciutat.
    """
    city = (
        address.get("city")
        or address.get("town")
        or address.get("municipality")
        or ""
    ).lower()

    if "barcelona" in city:
        return True

    lat_min, lat_max, lng_min, lng_max = BARCELONA_BOUNDS
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def parse_carrer_numero(address: dict) -> tuple[str | None, int | None]:
    """
    Extreu el nom del carrer i el número de la resposta de Nominatim.
    Retorna (carrer, numero) o (None, None) si no s'ha pogut parsejar.
    """
    carrer = (
        address.get("road")
        or address.get("pedestrian")
        or address.get("footway")
    )

    if not carrer:
        return None, None

    carrer = carrer.strip()

    numero_raw = address.get("house_number")
    numero = None
    if numero_raw:
        # Agafem el primer token numèric: "12-14" → 12, "12 bis" → 12.
        try:
            numero = int("".join(filter(str.isdigit, numero_raw.split()[0])))
        except (ValueError, IndexError):
            numero = None

    return carrer, numero