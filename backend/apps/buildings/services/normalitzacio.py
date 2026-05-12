import unicodedata
import re


def normalitzar_carrer(carrer: str) -> str:
    carrer = carrer.lower().strip()

    carrer = unicodedata.normalize('NFD', carrer)
    carrer = ''.join(c for c in carrer if unicodedata.category(c) != 'Mn')

    prefixes = [
        r"^carrer d[e\u2019']l?\s+",  # també cobreix "carrer d'el" i "carrer d’l" (amb apostrof tipogràfic)
        r"^carrer d[e']l?\s+",
        r"^carrer\s+",
        r"^c/\s*",
        r"^avinguda d[e']l?\s+",
        r"^avinguda\s+",
        r"^avda\.?\s+",
        r"^passeig d[e']l?\s+",
        r"^passeig\s+",
        r"^passatge d[e']l?\s+",
        r"^passatge\s+",
        r"^placa d[e']l?\s+",
        r"^placa\s+",
        r"^ronda d[e']l?\s+",
        r"^ronda\s+",
        r"^travessera d[e']l?\s+",
        r"^travessera\s+",
    ]
    for prefix in prefixes:
        carrer = re.sub(prefix, '', carrer)

    return carrer.strip()