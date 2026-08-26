import re

from app.links import avianca as search_url  # el enlace vive en app/: lo usa la UI

from .base import dedupe, extract_times, standard, to_int_price, wait_for_cards
from .fares import parse_panel

NAME = "Avianca"
ENGINE = "playwright"
CARD = "button.flight-container"
# Avianca lista el equipaje de cada tarifa (Basic/Classic/Flex) sobre su precio.
BAG_SIDE = "before"


async def read_fares(page, index: int = 0) -> dict:
    """Despliega las tarifas de un vuelo (Basic / Classic / Flex).

    Se abre el vuelo más barato porque el salto de precio del equipaje no es
    igual en todas las tarifas base, y el barato es el que se va a comprar.

    El aviso de cookies tapa las tarjetas: sin cerrarlo el clic nunca llega.
    """
    for label in ("Aceptar", "Aceptar todo", "Aceptar todas", "Entendido"):
        btn = page.get_by_role("button", name=label)
        try:
            if await btn.count():
                await btn.first.click(timeout=3000)
                break
        except Exception:  # noqa: BLE001  si no se deja pulsar, se intenta el clic igual
            pass

    card = page.locator(CARD).nth(index)
    await card.scroll_into_view_if_needed()
    try:
        await card.click(timeout=8000)
    except Exception:  # noqa: BLE001
        await card.click(force=True, timeout=8000)
    await page.wait_for_selector("text=equipaje de mano", timeout=30_000)
    await page.wait_for_timeout(1500)
    return parse_panel(await page.locator("body").inner_text(), BAG_SIDE)


def parse_card(raw: str, url: str) -> dict | None:
    text = " | ".join(line.strip() for line in raw.splitlines() if line.strip())
    prices = [p for p in (to_int_price(x) for x in re.findall(r"COP\s*([\d.,]+)", text)) if p]
    if not prices:
        return None
    times = extract_times(text)
    dm = re.search(r"(\d+h\s?\d*m?|\d+m)\b", text)
    return {
        "depart_time": times[0] if times else None,
        "arrive_time": times[1] if len(times) > 1 else None,
        "duration": dm.group(1) if dm else None,
        "flight_no": None,
        "price": min(prices),
        "url": url,
    }


async def scrape(origin: str, destination: str, date: str, adults: int = 1) -> dict:
    url = search_url(origin, destination, date, adults)
    # Akamai bloquea si se interceptan requests (Fetch.enable), asi que no filtramos.
    ctx, page = await standard.new_page(block_assets=False)
    ladder = {}
    try:
        # Warm-up: pasar primero por la home deja las cookies de Akamai y evita el 403.
        await page.goto("https://www.avianca.com/es/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await page.goto(url, wait_until="domcontentloaded")
        await wait_for_cards(page, CARD)
        cards = await page.locator(CARD).all_inner_texts()
        rows = [(i, f) for i, raw in enumerate(cards) if (f := parse_card(raw, url))]
        try:
            barata = min(rows, key=lambda r: r[1]["price"])[0] if rows else 0
            ladder = await read_fares(page, barata)
        except Exception as exc:  # noqa: BLE001  sin panel se estima el equipaje
            ladder = {"error": str(exc)[:120]}
    finally:
        await ctx.close()

    return {"flights": dedupe([f for _, f in rows]), "ladder": ladder}
