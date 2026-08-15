# Sin Chromium: el scraping vive en GitHub Actions y WhatsApp usa Baileys
# (WebSocket puro). La imagen queda pequeña y cabe de sobra en el plan free.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/tmp/flight/flights.db \
    WA_AUTH_DIR=/tmp/flight/whatsapp

# Node 20: el `nodejs` de Debian es el 18 y Baileys exige >=20 (el sidecar moría
# al arrancar). git hace falta porque una dependencia se instala desde un repo.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gnupg git ca-certificates \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY whatsapp-bot/package.json whatsapp-bot/package-lock.json whatsapp-bot/
# Baileys depende de libsignal-node por "git+ssh", y en el contenedor no hay
# llaves SSH: se reescribe a HTTPS para que npm pueda clonarlo.
RUN git config --global url."https://github.com/".insteadOf "ssh://git@github.com/" \
 && git config --global url."https://github.com/".insteadOf "git@github.com:" \
 && cd whatsapp-bot && npm install --omit=dev --no-audit --no-fund

COPY whatsapp-bot ./whatsapp-bot
COPY app ./app
COPY static ./static
COPY start.sh .
RUN chmod +x start.sh && mkdir -p /tmp/flight

EXPOSE 8000
CMD ["./start.sh"]
