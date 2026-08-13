import os
import re

from ..config import DB_PATH, HEADLESS, NAV_TIMEOUT_MS

PROFILE_ROOT = os.path.join(os.path.dirname(DB_PATH) or ".", "profiles")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

BLOCKED_ASSETS = re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4)(\?|$)")


class Browser:
    """Chromium con perfil persistente; una pestaña nueva por scrape.

    El perfil se reusa a proposito: conserva las cookies del anti-bot entre
    escaneos, asi cada consulta parece un visitante recurrente y no uno nuevo.

    Dos motores porque cada aerolinea tiene un anti-bot distinto:
      - engine="playwright": Chromium 131 + UA propia. Sirve para Wingo y Avianca
        (Akamai de Avianca rechaza fingerprints de Chromium mas nuevos).
      - engine="patchright": fork sin fugas de CDP. Necesario para JetSMART,
        cuyo Imperva redirige a la home a Playwright estandar.
    """

    def __init__(self, engine: str = "playwright"):
        self.engine = engine
        self._pw = None
        self._ctx = None

    async def start(self):
        if self._ctx:
            return
        if self.engine == "patchright":
            from patchright.async_api import async_playwright
        else:
            from playwright.async_api import async_playwright

        args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            # Sin esto, en macOS el perfil persistente pide la clave del llavero.
            "--use-mock-keychain",
            "--password-store=basic",
        ]
        kwargs = dict(
            headless=HEADLESS,
            locale="es-CO",
            timezone_id="America/Bogota",
            viewport={"width": 1366, "height": 900},
        )
        if self.engine == "playwright":
            args.append("--disable-blink-features=AutomationControlled")
            kwargs["user_agent"] = UA  # patchright pierde stealth si se fuerza la UA

        profile = os.path.join(PROFILE_ROOT, self.engine)
        os.makedirs(profile, exist_ok=True)
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            profile, args=args, **kwargs
        )
        self._ctx.set_default_timeout(NAV_TIMEOUT_MS)

    async def stop(self):
        if self._ctx:
            await self._ctx.close()
            self._ctx = None
        if self._pw:
            await self._pw.stop()
            self._pw = None

    async def new_page(self, block_assets: bool = True):
        await self.start()
        page = await self._ctx.new_page()
        if block_assets:
            # Ahorra RAM, pero Fetch.enable delata al navegador en algunos anti-bot.
            await page.route(BLOCKED_ASSETS, lambda route: route.abort())
        # Se devuelve la propia pagina como "cerrable": cierra la pestaña, no el perfil.
        return page, page


standard = Browser("playwright")
stealth = Browser("patchright")
ENGINES = {"playwright": standard, "patchright": stealth}


async def keep_only(engine: str):
    """Deja vivo un solo Chromium: dos a la vez no caben en 512 MB.

    Cerrar el navegador no pierde nada: las cookies del anti-bot viven en el
    perfil en disco, no en memoria.
    """
    for name, browser in ENGINES.items():
        if name != engine:
            await browser.stop()


async def stop_all():
    for browser in ENGINES.values():
        await browser.stop()


async def wait_for_cards(page, selector: str, timeout_ms: int = 60_000, settle_ms: int = 2000):
    """Espera por conteo, no por wait_for_selector.

    Algunas SPAs (Avianca) dejan la navegacion abierta indefinidamente y
    wait_for_selector se bloquea esperandola en vez de mirar el DOM.
    """
    waited = 0
    step = 1500
    while waited < timeout_ms:
        try:
            if await page.locator(selector).count():
                await page.wait_for_timeout(settle_ms)
                return True
        except Exception:  # noqa: BLE001  contexto destruido por una navegacion interna
            pass
        await page.wait_for_timeout(step)
        waited += step
    raise TimeoutError(f"no aparecieron resultados ({selector}) en {timeout_ms // 1000}s")


def to_int_price(text: str) -> int | None:
    """'$ 86,090 COP' / 'COP 131.900' / '$76.892' -> 86090 / 131900 / 76892"""
    digits = re.sub(r"\D", "", text or "")
    if not digits:
        return None
    value = int(digits)
    return value if value > 1000 else None


TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\s*(a\.?\s?m\.?|p\.?\s?m\.?)?", re.I)


def normalize_time(hhmm: str, meridiem: str | None) -> str:
    """'5:31' + 'a.m.' -> '05:31' (24h). Sin meridiano se asume ya 24h."""
    hh, mm = hhmm.split(":")
    hh = int(hh)
    if meridiem:
        m = meridiem.lower().replace(".", "").replace(" ", "")
        if m == "pm" and hh != 12:
            hh += 12
        if m == "am" and hh == 12:
            hh = 0
    return f"{hh:02d}:{mm}"


def extract_times(text: str, limit: int = 2) -> list[str]:
    out = []
    for m in TIME_RE.finditer(text):
        out.append(normalize_time(m.group(1), m.group(2)))
        if len(out) >= limit:
            break
    return out


def dedupe(flights: list[dict]) -> list[dict]:
    seen, out = set(), []
    for f in flights:
        key = (f.get("depart_time"), f.get("arrive_time"), f.get("price"))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return sorted(out, key=lambda f: (f["price"], f.get("depart_time") or ""))
