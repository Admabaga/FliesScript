# Sin Chromium: el scraping vive en GitHub Actions y WhatsApp usa Baileys
# (WebSocket puro). La imagen queda pequeña y cabe de sobra en el plan free.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/tmp/flight/flights.db \
    WA_AUTH_DIR=/tmp/flight/whatsapp

RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY whatsapp-bot/package.json whatsapp-bot/
RUN cd whatsapp-bot && npm install --omit=dev

COPY whatsapp-bot ./whatsapp-bot
COPY app ./app
COPY static ./static
COPY start.sh .
RUN chmod +x start.sh && mkdir -p /tmp/flight

EXPOSE 8000
CMD ["./start.sh"]
