# Flight ✈️

Vigila precios de vuelos en **Wingo**, **JetSMART** y **Avianca** y avisa por
**WhatsApp** cuando alguno baja de tu filtro.

- Agregas las fechas que quieras; cada una con su propio precio máximo.
- Origen y destino se eligen de una lista con 74 ciudades (nombre + código IATA),
  para no tener que acordarse de si Cartagena es CTG o CGN.
- Las fechas viven en el servidor **y** en `localStorage` (no se pierden al recargar).
- Cada fecha muestra los vuelos de las 3 aerolíneas con **horario y precio**.
- Revisa cada 60 min y alerta solo cuando hay algo bajo tu filtro.
- Pensada para el celular: una columna por aerolínea en PC, apiladas en móvil.

## Cómo funciona

Está partida en dos, y por una razón concreta: el scraping necesita un navegador
real, y un navegador no cabe en los 512 MB del plan free de Render.

```
GitHub Actions (cada hora)          Render (free)
  abre las 3 aerolíneas    ──POST──▶  guarda, muestra
  con Chromium + xvfb                 y manda los WhatsApp
  7 GB RAM · CPU real                 sin Chromium para scrapear
```

- **`runner.py`** corre en Actions: pide las fechas a la app (`GET /api/pending`),
  consulta las aerolíneas y devuelve lo que encontró (`POST /api/results`).
- **La app en Render** solo guarda, pinta la interfaz y envía por WhatsApp Web.
  Ahí sí abre un Chromium, pero uno solo y únicamente al enviar.

No hay API usable en las aerolíneas: las tres están detrás de anti-bots
(Cloudflare en Wingo, Imperva en JetSMART, Akamai en Avianca) que **también
bloquean la simple consulta**, no solo la compra. De ahí el navegador.

| Aerolínea | URL de búsqueda | Motor |
|---|---|---|
| Wingo | `booking.wingo.com/es/search/{O}/{D}/{fecha}/1/0/0/1/COP/0/0` | Playwright |
| JetSMART | `booking.jetsmart.com/Flight/InternalSelect?...` | Patchright |
| Avianca | `booking.avianca.com/av/booking/avail?...` | Playwright |

JetSMART necesita `patchright` (fork de Playwright sin las fugas de CDP) porque
Imperva redirige a Playwright estándar a la home.

Para no despertar a los anti-bots: **perfil de navegador persistente**, consultas
**espaciadas 12s** y reintentos con backoff. Además solo vive **un Chromium a la
vez** y se cierra al terminar el escaneo, para caber en 512 MB de RAM.

## Correr en local

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install --no-deps playwright==1.49.1
.venv/bin/python -m playwright install chromium
.venv/bin/python -m patchright install chromium
.venv/bin/uvicorn app.main:app --reload --port 8010
```

Abre http://localhost:8010

> `playwright` va con `--no-deps` a propósito: pinea `pyee==12` y `patchright`
> pinea `pyee 13`. Con `pyee 13` funcionan los dos, pero pip no lo resuelve solo.
>
> Python 3.12 o 3.11. En 3.14 todavía no compilan las ruedas de `greenlet`.

## Configurar WhatsApp

Los mensajes salen **desde tu propio WhatsApp**, igual que WhatsApp Web:

1. **⚙ Alertas → Conectar**. Aparece un código QR.
2. En el celular: *WhatsApp → Ajustes → Dispositivos vinculados → Vincular
   dispositivo*, y escanea.
3. Escribe los números a avisar, uno por línea:
   ```
   +573054305869
   +573009876543
   ```
4. **Guardar** → **Probar**.

No se guarda ninguna contraseña: la sesión vive en el perfil del navegador, como
en el computador de cualquiera.

> ⚠️ **En el plan free la sesión se pierde cuando Render reinicia el servicio**
> (no hay disco persistente) y toca volver a escanear el QR. Si eso molesta:
> agrega un disco (plan Starter) o usa el respaldo de abajo.

### Respaldo: CallMeBot

Si WhatsApp Web no está vinculado, la app usa
[CallMeBot](https://www.callmebot.com/blog/free-api-whatsapp-messages/) para los
números que tengan apikey. Cada persona pide la suya: guarda el
**+34 644 51 95 23** y mándale `I allow callmebot to send me messages`. Luego se
escribe así:

```
+573054305869|123456
```

## Desplegar

### 1. Render (la interfaz)

1. Render → **New → Blueprint** → apunta a este repo. Lee `render.yaml`.
2. Render genera solo el `INGEST_TOKEN`. **Cópialo** de Environment: lo necesitas
   en el paso 2.
3. `WA_RECIPIENTS` se puede dejar vacío y configurar luego desde la app.

### 2. GitHub Actions (el motor)

En el repo → **Settings → Secrets and variables → Actions → New secret**:

| Secret | Valor |
|---|---|
| `APP_URL` | `https://tu-app.onrender.com` |
| `INGEST_TOKEN` | el mismo que generó Render |

El workflow corre solo cada hora. Para probarlo ya: pestaña **Actions → Buscar
vuelos → Run workflow**.

### 3. Botón "Actualizar" de la app (opcional)

Para que el botón dispare el workflow, crea un
[token de GitHub](https://github.com/settings/tokens) con permiso `workflow` y
pon en Render:

```
SCRAPE_URL=https://api.github.com/repos/USUARIO/REPO/actions/workflows/scrape.yml/dispatches
```

Sin esto el botón no rompe nada: simplemente avisa que el runner corre cada hora.

Notas:

- El plan free duerme a los 15 min: mantenlo despierto con UptimeRobot apuntando
  a `/health` cada 10 min.
- Sin disco no hay BD persistente. Si Render reinicia, la app repone tus fechas
  desde el `localStorage` del navegador la próxima vez que la abras (y toca
  volver a escanear el QR de WhatsApp).

## Frecuencia

Cada hora, definido en el `cron` de `.github/workflows/scrape.yml`. Bajar de 30
minutos aumenta el riesgo de bloqueo (Avianca es la más sensible) y consume más
minutos de Actions (el plan gratis da 2000/mes; una ronda gasta ~2).

`No repetir alerta (h)` evita recibir el mismo vuelo cada hora: solo vuelve a
avisar si pasó ese tiempo **o** si el precio bajó todavía más.

## Si una aerolínea deja de funcionar

Cada scraper está aislado en `app/scrapers/`. Si cambian el HTML, se ajusta el
selector de ese archivo; las otras dos siguen funcionando y la interfaz muestra
el error por aerolínea.

| Archivo | Selector clave |
|---|---|
| `wingo.py` | `w-org-flight-card` |
| `jetsmart.py` | texto `Vuelo Operado por` (tras pulsar *Continuar*) |
| `avianca.py` | `button.flight-container` |

Los destinos del desplegable están en `static/airports.js`; agregar uno es una
línea más en la región que corresponda.
