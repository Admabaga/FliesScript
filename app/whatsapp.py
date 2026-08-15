"""Cliente del sidecar de WhatsApp (Baileys, en whatsapp-bot/).

Antes esto abría WhatsApp Web con un navegador y fotografiaba el QR: el código
vence cada ~20s y la foto llegaba muerta al celular. Baileys habla el protocolo
directo por WebSocket, así que el QR sale del propio WhatsApp y no hay Chrome.
"""

import logging

import httpx

log = logging.getLogger("whatsapp")

BOT = "http://127.0.0.1:3001"
STATE = {"status": "desconectado", "qr": None}


async def refresh_state(wait_s: int = 0) -> dict:
    """Lee el estado del sidecar. El QR se renueva solo allá."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{BOT}/status")
        STATE.update(r.json())
    except Exception as exc:  # noqa: BLE001
        log.warning("sidecar no responde: %s", exc)
        STATE.update(status="desconectado", qr=None, detalle="el servicio de WhatsApp no responde")
    return dict(STATE)


async def start_pairing() -> dict:
    """El sidecar ya genera el QR solo al arrancar; aquí solo se consulta."""
    return await refresh_state()


async def logout() -> dict:
    """Borra la sesión para que salga un QR nuevo."""
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            await c.post(f"{BOT}/logout")
    except Exception as exc:  # noqa: BLE001
        log.warning("no se pudo cerrar la sesión: %s", exc)
    return await refresh_state()


async def send(phone: str, text: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post(f"{BOT}/send", json={"to": phone, "message": text})
        if r.status_code == 200:
            return f"{phone}: ok"
        if r.status_code == 503:
            return f"{phone}: WhatsApp sin vincular (escanea el QR)"
        return f"{phone}: {r.json().get('error', r.status_code)}"
    except Exception as exc:  # noqa: BLE001
        return f"{phone}: error {str(exc)[:60]}"


async def send_all(phones: list[str], text: str) -> list[str]:
    return [await send(p, text) for p in phones]


async def stop():
    """El sidecar es un proceso aparte; no hay nada que cerrar desde aquí."""
    return None
