"""Motor de scraping. Corre en GitHub Actions, no en Render.

Pide las fechas a la app, consulta las 3 aerolíneas y devuelve lo que encontró.
Aquí sí hay CPU y RAM de verdad, así que no hay que hacer malabares.

    APP_URL=https://flight-xxxx.onrender.com INGEST_TOKEN=... python runner.py
"""

import asyncio
import logging
import os
import sys

import httpx

from scraper import AIRLINES
from scraper.base import keep_only, stop_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("runner")

APP_URL = os.environ["APP_URL"].rstrip("/")
TOKEN = os.environ["INGEST_TOKEN"]
HEADERS = {"X-Token": TOKEN}
RETRIES = 2
PACE_S = 5  # aquí sobra potencia; la pausa es solo para no parecer un bot


def friendly_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "no aparecieron resultados" in text or "timeout" in text:
        return "no respondió a tiempo; se reintenta en la próxima revisión"
    if "net::" in text or "connection" in text:
        return "sin conexión con la aerolínea"
    return "no se pudo leer la página; se reintenta luego"


async def scrape_leg(module, origin: str, destination: str, date: str, adults: int) -> dict:
    """Un trayecto en una aerolínea, con reintento."""
    for attempt in range(RETRIES):
        try:
            await keep_only(module.ENGINE)
            res = await module.scrape(origin, destination, date, adults)
            flights, ladder = res["flights"], res.get("ladder") or {}
            log.info("%s %s->%s %s: %s vuelos, equipaje %s", module.NAME, origin, destination,
                     date, len(flights),
                     "leído" if ladder.get("deltas") else f"sin panel ({ladder.get('error', '-')})")
            return {"status": "ok" if flights else "vacio", "flights": flights, "ladder": ladder}
        except Exception as exc:  # noqa: BLE001
            log.warning("%s intento %s/%s: %s", module.NAME, attempt + 1, RETRIES, str(exc)[:120])
            if attempt < RETRIES - 1:
                await asyncio.sleep(20)
            else:
                return {"status": "error", "message": friendly_error(exc), "flights": []}


async def scrape_one(module, watch: dict) -> dict:
    """Ida y, si la fecha lo pide, vuelta. Se consultan como dos búsquedas de solo
    ida: es como cotizan las tres y así el precio de cada tramo queda a la vista."""
    adults = max(1, int(watch.get("adults") or 1))
    legs = [("out", watch["origin"], watch["destination"], watch["date"])]
    if watch.get("return_date"):
        legs.append(("ret", watch["destination"], watch["origin"], watch["return_date"]))

    flights, ladders, fallos = [], {}, []
    for i, (direction, origin, destination, date) in enumerate(legs):
        if i:
            await asyncio.sleep(PACE_S)
        res = await scrape_leg(module, origin, destination, date, adults)
        nombre = "ida" if direction == "out" else "vuelta"
        if res["status"] == "error":
            fallos.append(f"{nombre}: {res.get('message', 'no se pudo leer')}")
            continue
        if res["status"] == "vacio":
            fallos.append(f"{nombre}: sin vuelos")
            continue
        flights += [{**f, "direction": direction} for f in res["flights"]]
        ladders[direction] = res["ladder"]

    if not flights:
        estado = "error" if any("sin vuelos" not in f for f in fallos) else "vacio"
        return {"status": estado, "message": " · ".join(fallos), "flights": []}
    return {"status": "ok", "flights": flights, "ladders": ladders,
            "message": " · ".join(fallos)}


async def main() -> int:
    async with httpx.AsyncClient(timeout=60, headers=HEADERS) as client:
        r = await client.get(f"{APP_URL}/api/pending")
        r.raise_for_status()
        watches = r.json()["watches"]

    if not watches:
        log.info("No hay fechas que vigilar.")
        return 0
    log.info("%s fechas por consultar", len(watches))

    fallos = 0
    for i, watch in enumerate(watches):
        if i:
            await asyncio.sleep(PACE_S)
        airlines = {}
        for j, module in enumerate(AIRLINES):
            if j:
                await asyncio.sleep(PACE_S)
            airlines[module.NAME] = await scrape_one(module, watch)
            if airlines[module.NAME]["status"] == "error":
                fallos += 1
        async with httpx.AsyncClient(timeout=120, headers=HEADERS) as client:
            resp = await client.post(
                f"{APP_URL}/api/results", json={"watch_id": watch["id"], "airlines": airlines}
            )
            log.info("enviado a la app: %s %s", resp.status_code, resp.text[:200])

    await stop_all()
    # Que falle una aerolínea no debe marcar el workflow en rojo; que fallen todas, sí.
    return 1 if fallos >= len(watches) * len(AIRLINES) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
