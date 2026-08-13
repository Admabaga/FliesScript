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

from app.scrapers import AIRLINES
from app.scrapers.base import keep_only, stop_all

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


async def scrape_one(module, watch: dict) -> dict:
    for attempt in range(RETRIES):
        try:
            await keep_only(module.ENGINE)
            flights = await module.scrape(watch["origin"], watch["destination"], watch["date"])
            log.info("%s %s->%s %s: %s vuelos", module.NAME, watch["origin"],
                     watch["destination"], watch["date"], len(flights))
            return {"status": "ok" if flights else "vacio", "flights": flights}
        except Exception as exc:  # noqa: BLE001
            log.warning("%s intento %s/%s: %s", module.NAME, attempt + 1, RETRIES, str(exc)[:120])
            if attempt < RETRIES - 1:
                await asyncio.sleep(20)
            else:
                return {"status": "error", "message": friendly_error(exc), "flights": []}


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
