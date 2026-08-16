import re

from .base import dedupe, extract_times, standard, to_int_price, wait_for_cards

NAME = "Avianca"
ENGINE = "playwright"
CARD = "button.flight-container"


def search_url(origin: str, destination: str, date: str) -> str:
    return (
        "https://booking.avianca.com/av/booking/avail"
        f"?departureDate={date}&tripType=one-way&platform=WEBB2C"
        f"&from={origin}&to={destination}"
        "&nbAdults=1&nbYoungs=0&nbChildren=0&nbInfants=0"
        "&language=ES&pointOfSale=CO&accessMethod=default&backend=PRD"
    )


async def scrape(origin: str, destination: str, date: str) -> list[dict]:
    url = search_url(origin, destination, date)
    # Akamai bloquea si se interceptan requests (Fetch.enable), asi que no filtramos.
    ctx, page = await standard.new_page(block_assets=False)
    try:
        # Warm-up: pasar primero por la home deja las cookies de Akamai y evita el 403.
        await page.goto("https://www.avianca.com/es/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await page.goto(url, wait_until="domcontentloaded")
        await wait_for_cards(page, CARD)
        cards = await page.locator(CARD).all_inner_texts()
    finally:
        await ctx.close()

    flights = []
    for raw in cards:
        text = " | ".join(line.strip() for line in raw.splitlines() if line.strip())
        prices = [
            p for p in (to_int_price(x) for x in re.findall(r"COP\s*([\d.,]+)", text)) if p
        ]
        if not prices:
            continue
        times = extract_times(text)
        dm = re.search(r"(\d+h\s?\d*m?|\d+m)\b", text)
        flights.append(
            {
                "depart_time": times[0] if times else None,
                "arrive_time": times[1] if len(times) > 1 else None,
                "duration": dm.group(1) if dm else None,
                "flight_no": None,
                "price": min(prices),
                "url": url,
            }
        )
    return dedupe(flights)
