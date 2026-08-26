"""Vinculación de WhatsApp: estado, QR y cierre de sesión."""

from fastapi import APIRouter

from .. import whatsapp as sidecar

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


@router.get("")
async def status():
    """Se consulta al sidecar cada vez: el QR de allá se renueva solo."""
    return await sidecar.refresh_state()


@router.post("/connect")
async def connect():
    """El sidecar ya tiene el QR listo; la UI lo va leyendo con GET."""
    return await sidecar.start_pairing()


@router.post("/logout")
async def logout():
    """Cierra la sesión para vincular otro teléfono."""
    return await sidecar.logout()
