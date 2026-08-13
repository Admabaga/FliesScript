import os

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/flights.db")
# Akamai (Avianca) detecta el modo headless y devuelve 403. En Docker se corre
# con ventana sobre una pantalla virtual (xvfb), por eso el default es "false".
HEADLESS = os.getenv("HEADLESS", "false").lower() != "false"
NAV_TIMEOUT_MS = int(os.getenv("NAV_TIMEOUT_MS", "60000"))
PORT = int(os.getenv("PORT", "8000"))

# Valores por defecto de la configuracion editable desde la UI.
# Todo esto se puede sobreescribir con variables de entorno en Render.
SETTING_DEFAULTS = {
    "scan_interval_min": os.getenv("SCAN_INTERVAL_MIN", "60"),
    "alert_cooldown_h": os.getenv("ALERT_COOLDOWN_H", "8"),
    # Una linea por persona: "+573054305869|123456" (telefono|apikey de CallMeBot).
    "wa_recipients": os.getenv("WA_RECIPIENTS", ""),
}

SECRET_KEYS: set[str] = set()
