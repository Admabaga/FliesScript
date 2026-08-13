import os

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/flights.db")
NAV_TIMEOUT_MS = int(os.getenv("NAV_TIMEOUT_MS", "60000"))
PORT = int(os.getenv("PORT", "8000"))

# Akamai (Avianca) detecta el modo headless y devuelve 403. Tanto en Docker como
# en GitHub Actions se corre con ventana sobre una pantalla virtual (xvfb).
HEADLESS = os.getenv("HEADLESS", "false").lower() != "false"

# Clave compartida con el runner de GitHub Actions.
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "")

# Para pedirle a GitHub que corra el scraping ya (botón "Actualizar"). Opcional:
# https://api.github.com/repos/USUARIO/REPO/actions/workflows/scrape.yml/dispatches
SCRAPE_URL = os.getenv("SCRAPE_URL", "")

# Valores por defecto de la configuracion editable desde la UI.
SETTING_DEFAULTS = {
    "scan_interval_min": os.getenv("SCAN_INTERVAL_MIN", "60"),
    "alert_cooldown_h": os.getenv("ALERT_COOLDOWN_H", "8"),
    # Un numero por linea: "+573054305869" (o "+573054305869|apikey" para CallMeBot).
    "wa_recipients": os.getenv("WA_RECIPIENTS", ""),
}
