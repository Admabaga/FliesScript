FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app
ENV PYTHONUNBUFFERED=1 DB_PATH=/tmp/flight/flights.db

# xvfb = pantalla virtual. Avianca (Akamai) rechaza el modo headless, así que el
# navegador corre "con ventana" contra una pantalla que no existe.
RUN apt-get update && apt-get install -y --no-install-recommends xvfb \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir --no-deps playwright==1.49.1

# En Render solo hace falta el Chromium de Playwright (ya viene en la imagen) para
# WhatsApp Web. El scraping —y patchright— corren en GitHub Actions.

COPY app ./app
COPY static ./static
COPY start.sh .
RUN chmod +x start.sh && mkdir -p /tmp/flight

EXPOSE 8000
CMD ["./start.sh"]
