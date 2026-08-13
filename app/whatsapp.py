"""Envío por WhatsApp Web: se vincula una vez escaneando un QR desde el celular.

La sesión queda guardada en el perfil del navegador (en disco), igual que cuando
se abre web.whatsapp.com en el computador. No se guarda ninguna contraseña.
"""

import asyncio
import base64
import logging
import re
from urllib.parse import quote

from .scrapers.base import Browser

log = logging.getLogger("whatsapp")

wa = Browser("playwright", profile="whatsapp")
_lock = asyncio.Lock()

URL = "https://web.whatsapp.com"

# WhatsApp Web cambia sus selectores seguido: se prueban varios.
LOGGED_IN = ["#pane-side", "[data-testid='chat-list']", "[aria-label='Lista de chats']"]
QR_CANVAS = ["canvas[aria-label*='Scan']", "canvas[aria-label*='scan']", "div[data-ref] canvas", "canvas"]
SEND_BTN = [
    "button[aria-label='Enviar']",
    "button[aria-label='Send']",
    "span[data-icon='send']",
    "[data-testid='send']",
]

STATE = {"status": "desconectado", "qr": None}


async def _first(page, selectors, timeout_ms=1500):
    for sel in selectors:
        try:
            if await page.locator(sel).count():
                el = page.locator(sel).first
                if await el.is_visible(timeout=timeout_ms):
                    return el
        except Exception:  # noqa: BLE001
            continue
    return None


async def _open_page():
    page, _ = await wa.new_page(block_assets=False)
    await page.goto(URL, wait_until="domcontentloaded")
    return page


async def refresh_state(wait_s: int = 25) -> dict:
    """Abre WhatsApp Web y dice si ya está vinculado o hace falta escanear."""
    async with _lock:
        page = await _open_page()
        try:
            for _ in range(wait_s):
                await page.wait_for_timeout(1000)
                if await _first(page, LOGGED_IN):
                    STATE.update(status="conectado", qr=None)
                    return dict(STATE)
                canvas = await _first(page, QR_CANVAS)
                if canvas:
                    png = await canvas.screenshot()
                    STATE.update(
                        status="esperando_qr",
                        qr="data:image/png;base64," + base64.b64encode(png).decode(),
                    )
                    return dict(STATE)
            STATE.update(status="desconectado", qr=None)
            return dict(STATE)
        finally:
            await page.close()


async def wait_for_pairing(timeout_s: int = 150) -> dict:
    """Mantiene el QR vivo mientras la persona lo escanea, y lo refresca si vence."""
    async with _lock:
        page = await _open_page()
        try:
            waited = 0
            while waited < timeout_s:
                await page.wait_for_timeout(2000)
                waited += 2
                if await _first(page, LOGGED_IN):
                    STATE.update(status="conectado", qr=None)
                    await page.wait_for_timeout(4000)  # deja que guarde la sesión
                    return dict(STATE)
                canvas = await _first(page, QR_CANVAS)
                if canvas:
                    png = await canvas.screenshot()
                    STATE.update(
                        status="esperando_qr",
                        qr="data:image/png;base64," + base64.b64encode(png).decode(),
                    )
            return dict(STATE)
        finally:
            await page.close()


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


async def send(phone: str, text: str) -> str:
    num = _digits(phone)
    if not num:
        return f"{phone}: número inválido"
    async with _lock:
        page, _ = await wa.new_page(block_assets=False)
        try:
            await page.goto(
                f"{URL}/send?phone={num}&text={quote(text)}&type=phone_number&app_absent=0",
                wait_until="domcontentloaded",
            )
            for _ in range(40):
                await page.wait_for_timeout(1500)
                if await _first(page, QR_CANVAS):
                    STATE.update(status="desconectado", qr=None)
                    return f"+{num}: WhatsApp no está vinculado"
                btn = await _first(page, SEND_BTN)
                if btn:
                    await btn.click()
                    await page.wait_for_timeout(3000)
                    return f"+{num}: ok"
                body = await page.evaluate("document.body.innerText.slice(0,300)")
                if "inválido" in body or "invalid" in body.lower():
                    return f"+{num}: el número no está en WhatsApp"
            return f"+{num}: no se pudo enviar (WhatsApp Web no respondió)"
        except Exception as exc:  # noqa: BLE001
            log.warning("envío a %s falló: %s", num, exc)
            return f"+{num}: error {str(exc)[:60]}"
        finally:
            await page.close()


async def send_all(phones: list[str], text: str) -> list[str]:
    results = []
    for phone in phones:
        results.append(await send(phone, text))
        await asyncio.sleep(2)
    return results


async def stop():
    await wa.stop()
