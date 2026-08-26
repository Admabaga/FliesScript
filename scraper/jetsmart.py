import re

from app.links import jetsmart as search_url  # el enlace vive en app/: lo usa la UI

from .base import dedupe, extract_times, stealth, to_int_price
from .fares import parse_panel

NAME = "JetSMART"
ENGINE = "patchright"
# En los "Packs" de JetSMART el equipaje va encima del "+ $" que cuesta.
BAG_SIDE = "before"

# La tarjeta muestra dos precios: el del "Club de descuentos" (solo para quien
# paga la membresía) y el público. Aquí interesa el público.
PUBLIC_PRICE = re.compile(r"Tarifa\s+(?:desde|seleccionada)[^$]{0,40}\$\s*([\d.,]+)", re.I)


async def read_fares(page) -> dict:
    """Abre los "Packs disponibles" del primer vuelo para leer el equipaje.

    El primero sirve porque JetSMART trae la lista ordenada por "Más barato", que
    es justo el vuelo cuyo salto de precio interesa.
    """
    await page.locator("text=Tarifa desde").first.click()
    await page.wait_for_selector("text=Equipaje de mano", timeout=30_000)
    await page.wait_for_timeout(1500)
    return parse_panel(await page.locator("body").inner_text(), BAG_SIDE)


async def scrape(origin: str, destination: str, date: str, adults: int = 1) -> dict:
    url = search_url(origin, destination, date, adults)
    ctx, page = await stealth.new_page()
    ladder = {}
    try:
        await page.goto(url, wait_until="domcontentloaded")

        # Interstitial anti-bot ("Client Challenge"): se resuelve solo en unos segundos.
        for _ in range(20):
            if "Client Challenge" not in (await page.title()):
                break
            await page.wait_for_timeout(1500)

        # JetSMART abre primero el calendario de precios; hay que pulsar "Continuar".
        await page.wait_for_selector("text=Calendario precios", timeout=45_000)
        cont = page.locator("div.cursor-pointer", has_text=re.compile(r"^\s*Continuar\s*$"))
        if await cont.count():
            await cont.first.click()

        await page.wait_for_selector("text=Vuelo Operado por", timeout=45_000)
        await page.wait_for_timeout(1500)
        cards = await page.locator("div:has-text('Vuelo Operado por')").all_inner_texts()
        try:
            ladder = await read_fares(page)
        except Exception as exc:  # noqa: BLE001  sin panel se estima el equipaje
            ladder = {"error": str(exc)[:120]}
    finally:
        await ctx.close()

    flights = []
    for raw in cards:
        text = " | ".join(line.strip() for line in raw.splitlines() if line.strip())
        # Descarta contenedores grandes que envuelven varias tarjetas.
        if text.count("Vuelo Operado por") != 1 or len(text) > 900:
            continue
        m = PUBLIC_PRICE.search(text)
        price = to_int_price(m.group(1)) if m else None
        if not price:
            prices = [
                p for p in (to_int_price(x) for x in re.findall(r"\$\s*([\d.,]+)", text)) if p
            ]
            price = min(prices) if prices else None
        if not price:
            continue
        times = extract_times(text)
        dm = re.search(r"(\d+h\s?\d*\s?min|\d+\s?min)", text)
        flights.append(
            {
                "depart_time": times[0] if times else None,
                "arrive_time": times[1] if len(times) > 1 else None,
                "duration": dm.group(1) if dm else None,
                "flight_no": None,
                "price": price,
                "url": url,
            }
        )
    return {"flights": dedupe(flights), "ladder": ladder}
