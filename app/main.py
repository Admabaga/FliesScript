import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, engine, notify, whatsapp
from .config import SECRET_KEYS
from .scrapers import NAMES
from .scrapers.base import stop_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

STATIC = Path(__file__).resolve().parent.parent / "static"
scheduler = AsyncIOScheduler(timezone="America/Bogota")


def _reschedule():
    minutes = max(15, int(db.get_settings().get("scan_interval_min") or 60))
    scheduler.add_job(
        engine.scan_all,
        "interval",
        minutes=minutes,
        id="scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    log.info("Escaneo programado cada %s min", minutes)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    scheduler.start()
    _reschedule()
    async def first_scan():
        # Se espera a que Render valide el health check: si Chromium arranca antes,
        # se come la RAM del plan free y el servicio muere sin abrir el puerto.
        await asyncio.sleep(45)
        await engine.scan_all()

    asyncio.create_task(first_scan())
    yield
    scheduler.shutdown(wait=False)
    await stop_all()
    await whatsapp.stop()


app = FastAPI(title="Flight", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True, **engine.STATE}


@app.get("/api/watches")
async def get_watches():
    out = []
    for w in db.list_watches():
        out.append({**w, "flights": db.get_flights(w["id"]), "status": db.get_statuses(w["id"])})
    return {
        "watches": out,
        "airlines": NAMES,
        "last_scan": engine.STATE["last_scan"],
        "running": engine.STATE["running"],
    }


@app.post("/api/watches")
async def post_watch(payload: dict = Body(...)):
    for field in ("origin", "destination", "date", "max_price"):
        if not payload.get(field):
            raise HTTPException(400, f"falta {field}")
    watch_id = db.add_watch(
        payload["origin"], payload["destination"], payload["date"], payload["max_price"]
    )
    asyncio.create_task(engine.scan_all(only_watch_id=watch_id))
    return {"id": watch_id}


@app.patch("/api/watches/{watch_id}")
async def patch_watch(watch_id: int, payload: dict = Body(...)):
    db.update_watch(watch_id, **payload)
    return {"ok": True}


@app.delete("/api/watches/{watch_id}")
async def del_watch(watch_id: int):
    db.delete_watch(watch_id)
    return {"ok": True}


@app.post("/api/scan")
async def post_scan(payload: dict = Body(default={})):
    asyncio.create_task(engine.scan_all(only_watch_id=payload.get("watch_id")))
    return {"started": True}


@app.get("/api/settings")
async def get_settings():
    s = db.get_settings()
    return {k: ("••••••" if k in SECRET_KEYS and v else v) for k, v in s.items()}


@app.post("/api/settings")
async def post_settings(payload: dict = Body(...)):
    clean = {k: v for k, v in payload.items() if not (k in SECRET_KEYS and v in ("", "••••••"))}
    db.save_settings(clean)
    _reschedule()
    return {"ok": True}


@app.post("/api/test-alert")
async def test_alert():
    return {
        "results": await notify.send_message(
            "✈️ Flight — mensaje de prueba. Si lees esto, las alertas funcionan."
        )
    }


@app.get("/api/whatsapp")
async def whatsapp_status():
    return whatsapp.STATE


@app.post("/api/whatsapp/connect")
async def whatsapp_connect():
    """Abre WhatsApp Web y devuelve el QR para escanear desde el celular."""
    return await whatsapp.refresh_state()


@app.post("/api/whatsapp/pair")
async def whatsapp_pair():
    """Espera a que se escanee el QR (o lo refresca si vence)."""
    return await whatsapp.wait_for_pairing()


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")
