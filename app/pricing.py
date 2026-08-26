"""De vuelos sueltos a lo que de verdad se paga.

Una sola fuente de verdad para la pantalla y para las alertas: el precio que se
muestra, el que se compara con el filtro y el que sale por WhatsApp se calculan
aquí. Si esto viviera duplicado en el frontend, tarde o temprano la app diría
un número y el WhatsApp otro.

Reglas del cálculo, todas verificadas contra las tres páginas:

  - el precio de la lista es **por pasajero y por trayecto** (sale igual pidiendo
    1 o 2 adultos), así que el total es precio × adultos × trayectos;
  - ida y vuelta se consulta como dos búsquedas de solo ida, que es como cotizan
    estas tres, y así el precio de cada tramo queda a la vista;
  - el filtro "avísame si baja de" se compara contra el **total** de la compra:
    todos los pasajeros, los dos tramos y el equipaje pedido.
"""

from . import baggage, links


def flight_option(flight: dict, bag_level: str) -> dict | None:
    """El precio de ese vuelo con el equipaje pedido, o None si no lo vende."""
    fares = flight.get("fares") or [
        {"level": "personal", "price": flight["price"], "source": "estimado", "name": None}
    ]
    return baggage.option_for(fares, bag_level or baggage.ANY)


def buy_url(watch: dict, airline: str, direction: str) -> str | None:
    """El enlace de compra ya con los pasajeros puestos.

    Se arma al mostrarlo, no al guardarlo: si se cambian los adultos, el enlace
    queda bien de inmediato y no hay que rehacer el filtro en la aerolínea.
    """
    adults = max(1, int(watch.get("adults") or 1))
    if direction == "ret":
        if not watch.get("return_date"):
            return None
        return links.search_url(
            airline, watch["destination"], watch["origin"], watch["return_date"], adults
        )
    return links.search_url(airline, watch["origin"], watch["destination"], watch["date"], adults)


def annotate(flights: list[dict], bag_level: str, watch: dict | None = None) -> list[dict]:
    """Añade a cada vuelo la opción que cumple el filtro de equipaje."""
    out = []
    for f in flights:
        direction = f.get("direction") or "out"
        url = buy_url(watch, f["airline"], direction) if watch else None
        out.append({**f, "direction": direction, "url": url or f.get("url"),
                    "option": flight_option(f, bag_level)})
    return out


def _leg(flight: dict) -> dict:
    return {
        "airline": flight["airline"],
        "direction": flight.get("direction") or "out",
        "depart_time": flight.get("depart_time"),
        "arrive_time": flight.get("arrive_time"),
        "duration": flight.get("duration"),
        "flight_no": flight.get("flight_no"),
        "url": flight.get("url"),
        "option": flight["option"],
    }


# El dato más flojo de la combinación manda: si un tramo es estimado, el total lo es.
_ORDER = {"scraped": 0, "derivado": 1, "estimado": 2}


def _source_of(*legs: dict) -> str:
    worst = "scraped"
    for leg in legs:
        if leg and _ORDER.get(leg["option"]["source"], 2) > _ORDER.get(worst, 0):
            worst = leg["option"]["source"]
    return worst


def _combo(watch: dict, out: dict, ret: dict | None) -> dict:
    adults = max(1, int(watch.get("adults") or 1))
    per_person = out["option"]["price"] + (ret["option"]["price"] if ret else 0)
    total = per_person * adults
    airlines = [out["airline"]] + ([ret["airline"]] if ret else [])
    return {
        "airline": " + ".join(dict.fromkeys(airlines)),
        "airlines": airlines,
        "mixed": bool(ret) and ret["airline"] != out["airline"],
        "out": out,
        "ret": ret,
        "per_person": per_person,
        "total": total,
        "adults": adults,
        "bag_level": watch.get("bag_level") or baggage.ANY,
        "source": _source_of(out, ret),
        "hit": total <= int(watch["max_price"]),
    }


def combos(watch: dict, flights: list[dict]) -> list[dict]:
    """Las compras posibles, ordenadas por total.

    Solo ida: una por vuelo. Ida y vuelta: cada vuelo de ida con la vuelta más
    barata de su misma aerolínea (una sola compra, un solo link) y, si mezclar
    aerolíneas sale mejor, se añade esa combinación aparte.
    """
    bag = watch.get("bag_level") or baggage.ANY
    usable = [f for f in annotate(flights, bag, watch) if f["option"]]
    outs = [_leg(f) for f in usable if (f.get("direction") or "out") == "out"]
    rets = [_leg(f) for f in usable if (f.get("direction") or "out") == "ret"]

    if not watch.get("return_date"):
        return sorted((_combo(watch, o, None) for o in outs), key=lambda c: c["total"])

    if not rets:
        return []

    cheapest_ret = {}
    for r in rets:
        cur = cheapest_ret.get(r["airline"])
        if cur is None or r["option"]["price"] < cur["option"]["price"]:
            cheapest_ret[r["airline"]] = r

    out_list = []
    for o in outs:
        r = cheapest_ret.get(o["airline"])
        if r:
            out_list.append(_combo(watch, o, r))

    # ¿Sale mejor comprar la ida en una aerolínea y la vuelta en otra?
    best_out = min(outs, key=lambda l: l["option"]["price"], default=None)
    best_ret = min(rets, key=lambda l: l["option"]["price"], default=None)
    if best_out and best_ret and best_out["airline"] != best_ret["airline"]:
        mixed = _combo(watch, best_out, best_ret)
        if not out_list or mixed["total"] < min(c["total"] for c in out_list):
            out_list.append(mixed)

    return sorted(out_list, key=lambda c: c["total"])


def combo_key(watch_id: int, combo: dict) -> str:
    """Identifica una compra concreta para no repetir la misma alerta."""
    out, ret = combo["out"], combo["ret"]
    partes = [
        str(watch_id),
        out["airline"],
        out["depart_time"] or "?",
        ret["airline"] if ret else "-",
        (ret["depart_time"] or "?") if ret else "-",
        combo["bag_level"],
    ]
    return "|".join(partes)


def summary(watch: dict, flights: list[dict]) -> dict:
    """Lo que la pantalla necesita: vuelos con precio, mejores compras y total."""
    bag = watch.get("bag_level") or baggage.ANY
    todos = combos(watch, flights)
    por_aerolinea = {}
    for c in todos:
        if not c["mixed"] and c["airline"] not in por_aerolinea:
            por_aerolinea[c["airline"]] = c
    return {
        "flights": annotate(flights, bag, watch),
        "combos": todos[:12],
        "best": todos[0] if todos else None,
        "best_by_airline": por_aerolinea,
    }
