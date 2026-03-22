import requests
import re

import unicodedata

def quitar_acentos(texto):
    """
    Convierte texto a su forma base, eliminando acentos.
    """
    if not texto:
        return ""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )

def limpiar_nombre_calle(nombre):
    """
    Normaliza el nombre de la calle: minúsculas, quitar prefijos y acentos.
    """
    if not nombre:
        return ""
    nombre = nombre.lower().strip()
    prefijos = ["carrer ", "avinguda ", "plaça ", "passeig ", "camí ", "ronda "]
    for p in prefijos:
        if nombre.startswith(p):
            nombre = nombre[len(p):]
            break
    nombre = re.sub(r'\s+', ' ', nombre)
    nombre = quitar_acentos(nombre)  # quitar acentos
    return nombre

def validar_direccion_osm(carrer, numero, barri, codi_postal=None):
    """
    Valida si la dirección existe usando Nominatim y devuelve datos normalizados.
    Flexible: acepta coincidencias aproximadas de la calle, pero el número debe existir.
    """
    url = "https://nominatim.openstreetmap.org/search"
    address = f"{numero} {carrer}, {barri}, Spain"
    params = {
        "q": address,
        "format": "json",
        "addressdetails": 1,
        "limit": 1
    }
    headers = {"User-Agent": "mi-app-django"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        print(f"Respuesta de OSM para '{address}': {response.text}")
    except requests.exceptions.RequestException:
        print(f"Error al conectar con OSM para '{address}'")
        return None

    data = response.json()
    if not data:
        print(f"No se encontró la dirección en OSM para '{address}'")
        return None

    result = data[0]
    direccion = result.get("address", {})
    print(f"Dirección normalizada de OSM: {direccion}")

    road_osm = direccion.get("road", "")
    suburb_osm = direccion.get("suburb", "")

    # Normalizamos nombres
    carrer_input = limpiar_nombre_calle(carrer)
    road_osm_clean = limpiar_nombre_calle(road_osm)

    # Validación flexible: el nombre de la calle del usuario debe aparecer en la calle de OSM
    if carrer_input not in road_osm_clean:
        print(f"La calle no coincide suficientemente: '{carrer}' vs '{road_osm}'")
        return None

    # Comprobamos que el número coincide (incluso si OSM devuelve rango tipo "7-11")
    house_number = direccion.get("house_number", "")
    # eliminamos espacios y guiones
    numeros_osm = re.findall(r'\d+', house_number)
    if str(numero) not in numeros_osm:
        print(f"El número no coincide: '{numero}' vs '{house_number}'")
        return None

    # Validamos barrio (podemos flexibilizar más si se quiere)
    if suburb_osm.lower() != barri.lower():
        print(f"El barrio no coincide: '{barri}' vs '{suburb_osm}'")
        return None

    return {
        "carrer": road_osm,
        "numero": numero,
        "barri": suburb_osm,
        "codiPostal": direccion.get("postcode", codi_postal),
        "latitud": float(result.get("lat", 0)),
        "longitud": float(result.get("lon", 0))
    }