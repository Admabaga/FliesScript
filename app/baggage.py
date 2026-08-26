"""Qué incluye cada precio: tarifa -> equipaje.

Las tres aerolíneas venden el mismo vuelo a varios precios según el equipaje, y
la lista de resultados solo muestra el más barato ("Desde…", "Tarifa desde"),
que en las tres es **solo un bolso pequeño**. La escalera completa vive un clic
más adentro, en el panel de tarifas, y de ahí la saca el scraper
(`scraper/fares.py`) leyendo el propio texto de la aerolínea:

    Wingo      Go Basic 114.102 · Go Standard +45.000 (mano) · Go Plus +100.000 (bodega)
    JetSMART   pack base · +93.177 (mano) · +93.296 (bodega)
    Avianca    Basic 131.900 · Classic +89.250 (mano y bodega juntas)

Con eso, cada vuelo tiene precio por nivel de equipaje. Tres calidades de dato,
y la UI las distingue para no vender una cuenta propia como precio confirmado:

  - `scraped`   leído tal cual en el panel, para el vuelo que se abrió.
  - `derivado`  el mismo salto aplicado a los demás vuelos del día (la aerolínea
                cobra el mismo upsell en toda la ruta de la fecha).
  - `estimado`  no se pudo abrir el panel: tabla `ADDON` de referencia,
                sobrescribible desde Ajustes.

Ojo con Avianca: no vende "solo equipaje de mano". Su escalón con mano ya trae
bodega, así que pedir mano cuesta lo mismo que pedir bodega. No se rellena el
hueco con una estimación: sería ofrecer un precio que no existe.
"""

# Orden creciente: cada nivel incluye lo del anterior.
LEVELS = ["personal", "carry_on", "checked"]
RANK = {level: i for i, level in enumerate(LEVELS)}

# "any" = no me importa el equipaje, muéstrame el más barato.
ANY = "any"

LABEL = {
    "personal": "Sin equipaje de mano",
    "carry_on": "Con equipaje de mano",
    "checked": "Con maleta en bodega",
}
SHORT = {"personal": "solo bolso", "carry_on": "mano 10 kg", "checked": "bodega 23 kg"}
ICON = {"personal": "🎒", "carry_on": "🧳", "checked": "🛄"}
DETAIL = {
    "personal": "Solo un bolso o morral pequeño bajo el asiento. No entra maleta de cabina.",
    "carry_on": "Bolso pequeño + maleta de cabina (10-12 kg) en el compartimiento.",
    "checked": "Bolso pequeño + maleta de cabina + maleta documentada en bodega (23 kg).",
}

# Lo que la UI ofrece como filtro, en orden.
FILTERS = [
    {"value": ANY, "label": "El más barato (cualquier equipaje)", "icon": "💸",
     "detail": "Muestra el precio más bajo, casi siempre sin equipaje de mano."},
    *[
        {"value": lv, "label": LABEL[lv], "icon": ICON[lv], "short": SHORT[lv],
         "detail": DETAIL[lv]}
        for lv in LEVELS
    ],
]

# Precio de referencia del equipaje suelto, por pasajero y por trayecto (COP).
# Solo se usa cuando no se pudo leer el panel de tarifas.
ADDON = {
    "Wingo": {"carry_on": 45_000, "checked": 100_000},
    "JetSMART": {"carry_on": 93_000, "checked": 93_000},
    "Avianca": {"carry_on": 89_000, "checked": 89_000},
}
ADDON_FALLBACK = {"carry_on": 80_000, "checked": 110_000}


def addons(airline: str, overrides: dict | None = None) -> dict:
    """Precio del equipaje suelto. `overrides` viene de Ajustes (0 = usar la tabla)."""
    base = dict(ADDON.get(airline) or ADDON_FALLBACK)
    for level, value in (overrides or {}).items():
        if level in base and value:
            base[level] = int(value)
    return base


def build_fares(
    airline: str,
    price: int,
    ladder: dict | None = None,
    overrides: dict | None = None,
) -> list[dict]:
    """Del precio de la lista + la escalera del panel a una tarifa por nivel.

    `ladder` es lo que devolvió `scraper.fares.parse_panel`. Si trae saltos, se
    respetan tal cual; si no, se estima con la tabla de referencia.
    """
    price = int(price)
    ladder = ladder or {}
    deltas = {k: v for k, v in (ladder.get("deltas") or {}).items() if k in RANK}
    names = ladder.get("names") or {}
    # El panel se abrió sobre un vuelo concreto: para ese, los precios son textuales.
    leido = deltas and ladder.get("base") == price

    fares = [
        {
            "name": names.get("personal"),
            "level": "personal",
            "price": price,
            "source": "scraped",  # este sí sale de la lista de la aerolínea
        }
    ]

    if deltas:
        for level in ("carry_on", "checked"):
            if level in deltas:
                fares.append(
                    {
                        "name": names.get(level),
                        "level": level,
                        "price": price + int(deltas[level]),
                        "source": "scraped" if leido else "derivado",
                    }
                )
        return fares

    extra = addons(airline, overrides)
    for level in ("carry_on", "checked"):
        if extra.get(level):
            fares.append(
                {
                    "name": None,
                    "level": level,
                    "price": price + int(extra[level]),
                    "source": "estimado",
                }
            )
    return fares


def option_for(fares: list[dict], required: str) -> dict | None:
    """La tarifa más barata que cumple el equipaje pedido.

    Devuelve `None` si esa aerolínea no vende ese equipaje en ese vuelo: mejor
    no mostrar nada que inventar un precio.
    """
    if not fares:
        return None
    rows = sorted(fares, key=lambda f: int(f["price"]))
    if required == ANY or required not in RANK:
        best = rows[0]
    else:
        ok = [f for f in rows if RANK.get(f["level"], -1) >= RANK[required]]
        if not ok:
            return None
        best = ok[0]
    return {
        "price": int(best["price"]),
        "level": best["level"],
        "fare_name": best.get("name"),
        "source": best.get("source") or "estimado",
        # Cuánto de ese precio es el equipaje, contra la tarifa más barata del vuelo.
        "extra": int(best["price"]) - int(rows[0]["price"]),
        "label": LABEL.get(best["level"], ""),
        "short": SHORT.get(best["level"], ""),
        "icon": ICON.get(best["level"], ""),
    }
