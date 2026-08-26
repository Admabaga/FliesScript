"""Ajustes editables desde la UI y el envío de prueba."""

from fastapi import APIRouter, Body

from .. import db, notify

router = APIRouter(prefix="/api", tags=["settings"])

MENSAJE_PRUEBA = "✈️ Flight — mensaje de prueba. Si lees esto, las alertas funcionan."


@router.get("/settings")
async def get_settings():
    return db.get_settings()


@router.post("/settings")
async def post_settings(payload: dict = Body(...)):
    db.save_settings(payload)
    return {"ok": True}


@router.post("/test-alert")
async def test_alert():
    return {"results": await notify.send_message(MENSAJE_PRUEBA)}
