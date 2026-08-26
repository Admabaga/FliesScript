"""Lee el panel de tarifas: qué equipaje trae cada precio.

La lista de resultados de las tres aerolíneas muestra un solo precio, el más
barato, que siempre es "solo un bolso pequeño". La escalera completa aparece un
clic adentro, en un panel que describe el equipaje con palabras
("Equipaje de mano hasta 12 Kg", "Equipaje de bodega"). Ese texto es el dato
duro: el nivel sale de ahí, no del nombre comercial de la tarifa.

Cada aerolínea ordena el panel a su manera y por eso `side`:

    Wingo      nombre, precio, y debajo el equipaje          -> side="after"
    JetSMART   el equipaje del pack y debajo el "+ $"        -> side="before"

y hay dos formas de cotizar: precio absoluto por tarifa (Wingo) o sobreprecio
sobre la tarifa base (JetSMART, "+ $93.177"). Las dos se normalizan a lo mismo:
el salto en pesos, por pasajero y por trayecto, sobre el precio de la lista.
"""

import re

LEVELS = ["personal", "carry_on", "checked"]
RANK = {level: i for i, level in enumerate(LEVELS)}

# El texto con el que cada aerolínea describe el equipaje incluido.
BAG_RE = [
    (
        "checked",
        re.compile(
            r"equipaje\s+(?:en\s+|de\s+)?bodega|maleta\s+(?:en\s+)?bodega"
            r"|equipaje\s+facturado|documentad[oa]",
            re.I,
        ),
    ),
    (
        "carry_on",
        re.compile(
            r"equipaje\s+de\s+(?:mano|cabina)|maleta\s+de\s+(?:mano|cabina)|carry[\s-]?on",
            re.I,
        ),
    ),
    (
        "personal",
        re.compile(r"morral|mochila|cartera|art[íi]culo\s+personal|bolso|personal\s+item", re.I),
    ),
]

# "$ 114,102" · "COP 131.900" · "+ $93.177" · "+ 0" (el pack sin sobreprecio)
MONEY = re.compile(
    r"(?P<plus>\+)?\s*(?:\$|COP)\s*(?P<num>\d[\d.,]*)"
    r"|(?P<zplus>\+)\s*(?P<zero>0)(?![\d.,])"
)

# El nombre comercial es solo decorativo, así que se acepta únicamente lo que se
# reconoce de verdad. Cualquier otra línea del panel (taglines, millas, avisos)
# quedaría como un nombre falso, y es mejor no mostrar nada.
FARE_NAME = re.compile(
    r"^(?:Go\s+\w+|Basic|B[áa]sic[ao]|Classic|Flex|Business|Smart|Full|Zero|Light"
    r"|Plus|Standard)$",
    re.I,
)
# Los códigos de una o dos letras solo cuentan en mayúsculas: en minúscula
# cualquier línea sueltacon una "s" pasaría por tarifa.
FARE_CODE = re.compile(r"^(?:XS|S|M|L|XL)$")


def _to_int(raw: str) -> int:
    digits = re.sub(r"\D", "", raw or "")
    return int(digits) if digits else 0


def _level_of(text: str) -> str | None:
    """El equipaje más alto que menciona el bloque."""
    best = None
    for level, pattern in BAG_RE:
        if pattern.search(text):
            if best is None or RANK[level] > RANK[best]:
                best = level
    return best


def _name_in(chunk: str, last: bool = False) -> str | None:
    """El nombre comercial de la tarifa, si aparece: 'Go Standard', 'Classic', 'M'…

    `last=True` busca de abajo hacia arriba: cuando el nombre va antes del precio,
    el que manda es el más cercano al precio, no el primero del texto.
    """
    lines = [ln.strip() for ln in (chunk or "").splitlines()]
    for line in reversed(lines) if last else lines:
        if line and (FARE_NAME.match(line) or FARE_CODE.match(line)):
            return line
    return None


def parse_panel(text: str, side: str = "after") -> dict:
    """De un panel de tarifas a los saltos de precio por nivel de equipaje.

    Devuelve `{"base": int|None, "deltas": {nivel: int}, "names": {nivel: str}}`.
    `base` solo viene cuando el panel cotiza precios absolutos: sirve para saber
    a qué vuelo pertenece el panel. `deltas` es lo que se le suma al precio de
    la lista para tener equipaje.
    """
    spots = []
    for m in MONEY.finditer(text or ""):
        if m.group("zero") is not None:
            spots.append({"start": m.start(), "end": m.end(), "value": 0, "plus": True})
            continue
        value = _to_int(m.group("num"))
        if value <= 1000:  # "COP 0", cantidades de kilos o de millas
            continue
        spots.append(
            {"start": m.start(), "end": m.end(), "value": value, "plus": bool(m.group("plus"))}
        )

    tiers = []
    for i, spot in enumerate(spots):
        if side == "before":
            start = spots[i - 1]["end"] if i else 0
            block = text[start : spot["start"]]
        else:
            end = spots[i + 1]["start"] if i + 1 < len(spots) else len(text)
            block = text[spot["end"] : end]
        level = _level_of(block)
        if level is None:
            continue  # no es una tarifa: precio de calendario, de otro vuelo, etc.
        # El nombre encabeza la tarifa: donde el equipaje va después del precio
        # (Wingo) queda antes de él; donde va antes (Avianca), abre el bloque.
        before = text[max(0, spot["start"] - 240) : spot["start"]]
        name = _name_in(block) if side == "before" else None
        name = name or _name_in(before, last=True)
        tiers.append({"level": level, "price": spot["value"], "plus": spot["plus"], "name": name})

    if not tiers:
        return {"base": None, "deltas": {}, "names": {}}

    # Por nivel se queda la opción más barata; los extras (silla, prioridad) suben
    # el precio sin cambiar el equipaje y no interesan.
    best: dict[str, dict] = {}
    for tier in tiers:
        cur = best.get(tier["level"])
        if cur is None or tier["price"] < cur["price"]:
            best[tier["level"]] = tier

    absolutes = {lv: t["price"] for lv, t in best.items() if not t["plus"]}
    base = None
    if absolutes:
        # La tarifa más barata del panel es la base (siempre el escalón personal).
        base = min(absolutes.values())

    deltas = {}
    for level in ("carry_on", "checked"):
        tier = best.get(level)
        if tier is None:
            continue
        if tier["plus"]:
            deltas[level] = tier["price"]
        elif base is not None:
            deltas[level] = tier["price"] - base

    # Un salto negativo o absurdo significa que se leyó mal: mejor no inventar.
    deltas = {lv: v for lv, v in deltas.items() if 0 <= v <= 3_000_000}
    if "checked" in deltas and "carry_on" in deltas:
        deltas["checked"] = max(deltas["checked"], deltas["carry_on"])

    return {
        "base": base,
        "deltas": deltas,
        "names": {lv: t["name"] for lv, t in best.items() if t["name"]},
    }
