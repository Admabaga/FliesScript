"""Ensamblado de la app web: ciclo de vida, rutas y estáticos.

El reparto del código, para no tener que leerlo todo para cambiar una cosa:

    config.py         variables de entorno
    db.py             persistencia (SQLite)
    baggage.py        reglas de equipaje: tarifa -> qué incluye
    pricing.py        cálculo de las compras y sus totales
    links.py          enlaces de compra de cada aerolínea
    engine.py         ingesta de resultados y decisión de alertar
    notify.py         redacción y envío del mensaje
    whatsapp.py       sidecar de WhatsApp
    validation.py     validación de la entrada
    runner_client.py  lo que se le pide a GitHub Actions
    routes/           HTTP, una por tema
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, engine, runner_client, whatsapp
from .routes import ROUTERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    asyncio.create_task(runner_client.rehydrate())
    # El cron de GitHub no cumple los 10 min prometidos: la app se vigila sola.
    asyncio.create_task(runner_client.watchdog())
    yield
    await whatsapp.stop()


app = FastAPI(title="Flight", lifespan=lifespan)

for router in ROUTERS:
    app.include_router(router)


# HEAD además de GET: los monitores tipo UptimeRobot usan HEAD por defecto, y
# FastAPI no lo añade solo (respondía 405 y marcaba el servicio como caído).
#
# Ese ping cada 10 min es, de paso, el latido del vigilante: si los precios están
# viejos, aprovecha para pedir una búsqueda. Se dispara en segundo plano para no
# demorar la respuesta (el monitor mide el tiempo).
@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    asyncio.create_task(runner_client.ensure_fresh())
    return {"ok": True, **engine.STATE, "auto": runner_client.estado_vigilante()}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")
