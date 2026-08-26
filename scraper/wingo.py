import re

from app.links import wingo as search_url  # el enlace vive en app/: lo usa la UI

from .base import dedupe, extract_times, standard, to_int_price
from .fares import parse_panel

NAME = "Wingo"
ENGINE = "playwright"
CARD = "w-org-flight-card"
# En el panel de Wingo el equipaje va debajo del precio de cada tarifa.
BAG_SIDE = "after"


async def read_fares(page, index: int = 0) -> dict:
    """Abre una tarifa para leer la escalera de equipaje (Go Basic/Standard/Plus).

    Se abre la del vuelo más barato: es el que se va a comprar, y el salto que
    cobra el equipaje no es idéntico en todas las tarifas base.
    """
    await page.locator(CARD).nth(index).locator("text=Seleccionar").first.click()
    await page.wait_for_selector("text=Equipaje de mano", timeout=30_000)
    await page.wait_for_timeout(1500)
    return parse_panel(await page.locator("body").inner_text(), BAG_SIDE)


def parse_card(raw: str, url: str) -> dict | None:
    text = " | ".join(line.strip() for line in raw.splitlines() if line.strip())
    m = re.search(r"\$\s*([\d.,]+)\s*COP", text)
    price = to_int_price(m.group(1)) if m else None
    if not price:
        return None
    times = extract_times(text)
    fm = re.search(r"\b([A-Z0-9]{2}\s?\d{2,4})\b", text)
    dm = re.search(r"\b(\d+h\s?\d*m?|\d+m)\b", text)
    return {
        "depart_time": times[0] if times else None,
        "arrive_time": times[1] if len(times) > 1 else None,
        "duration": dm.group(1) if dm else None,
        "flight_no": fm.group(1) if fm else None,
        "price": price,
        "url": url,
    }


async def scrape(origin: str, destination: str, date: str, adults: int = 1) -> dict:
    url = search_url(origin, destination, date, adults)
    ctx, page = await standard.new_page()
    ladder = {}
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_selector(CARD, timeout=45_000)
        cards = await page.locator(CARD).all_inner_texts()
        # El índice importa: el panel se abre sobre la tarjeta más barata.
        rows = [(i, f) for i, raw in enumerate(cards) if (f := parse_card(raw, url))]
        try:
            barata = min(rows, key=lambda r: r[1]["price"])[0] if rows else 0
            ladder = await read_fares(page, barata)
        except Exception as exc:  # noqa: BLE001  sin panel se estima el equipaje
            ladder = {"error": str(exc)[:120]}
    finally:
        await ctx.close()

    return {"flights": dedupe([f for _, f in rows]), "ladder": ladder}
