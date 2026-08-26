# Flight ✈️

Vigila precios de vuelos en **Wingo**, **JetSMART** y **Avianca** y avisa por
**WhatsApp** cuando alguno baja de tu filtro.

- Agregas las búsquedas que quieras: **ida o ida y vuelta**, **cuántos adultos**,
  **qué equipaje necesitas** y el precio máximo, cada una con lo suyo.
- Origen y destino se eligen de una lista con 74 ciudades (nombre + código IATA),
  para no tener que acordarse de si Cartagena es CTG o CGN.
- Las búsquedas viven en el servidor **y** en `localStorage` (no se pierden al recargar).
- Cada búsqueda muestra los vuelos de las 3 aerolíneas con **horario, precio y
  qué equipaje trae ese precio** (ver *Equipaje* más abajo).
- El filtro se compara contra el **total de la compra**: todos los pasajeros, los
  dos tramos y el equipaje pedido.
- El enlace de compra sale **con los pasajeros ya puestos**, para no rehacer el
  formulario en la aerolínea.
- Revisa cada 10 min y **solo avisa cuando hay novedad** (ver más abajo).
- Pensada para el celular: una columna por aerolínea en PC, apiladas en móvil.

## Cómo funciona

Está partida en dos, y por una razón concreta: el scraping necesita un navegador
real, y un navegador no cabe en los 512 MB del plan free de Render.

```
GitHub Actions (cada 10 min)        Render (free)
  scraper/ + runner.py     ──POST──▶  app/ : guarda, muestra
  Chromium + xvfb                     y manda los WhatsApp
  7 GB RAM · CPU real                 sin navegador
```

La frontera es literal: `scraper/` y `runner.py` solo corren en Actions; `app/`
solo corre en Render. Nada de `scraper/` entra en la imagen de Docker.

- **`runner.py`** corre en Actions: pide las fechas a la app (`GET /api/pending`),
  consulta las aerolíneas y devuelve lo que encontró (`POST /api/results`).
- **La app en Render** solo guarda, pinta la interfaz y envía por WhatsApp.
  No abre ningún navegador: su imagen ni siquiera trae Chromium.

No hay API usable en las aerolíneas: las tres están detrás de anti-bots
(Cloudflare en Wingo, Imperva en JetSMART, Akamai en Avianca) que **también
bloquean la simple consulta**, no solo la compra. De ahí el navegador.

| Aerolínea | URL de búsqueda | Motor |
|---|---|---|
| Wingo | `booking.wingo.com/es/search/{O}/{D}/{fecha}/{adultos}/0/0/1/COP/0/0` | Playwright |
| JetSMART | `booking.jetsmart.com/Flight/InternalSelect?...&ADT={adultos}` | Patchright |
| Avianca | `booking.avianca.com/av/booking/avail?...&nbAdults={adultos}` | Playwright |

Las URLs viven en `app/links.py` (no en `scraper/`) porque **el enlace lo pinta
la app** y la imagen de Docker solo copia `app/`. El runner sí tiene todo el
repo, así que los scrapers las importan de ahí. Se arman al mostrarlas: cambiar
los adultos actualiza el enlace sin esperar la siguiente revisión.

**Ida y vuelta se consulta como dos búsquedas de solo ida** (la de ida y la de
regreso con origen/destino al revés). Es como cotizan estas tres, deja el precio
de cada tramo a la vista y permite combinar la ida en una aerolínea con la vuelta
en otra si sale mejor.

JetSMART necesita `patchright` (fork de Playwright sin las fugas de CDP) porque
Imperva redirige a Playwright estándar a la home.

Para no despertar a los anti-bots: **perfil de navegador persistente**, consultas
espaciadas y reintentos con backoff.

## Cómo está organizado el código

Cada archivo tiene un trabajo y solo uno; así se cambia una cosa sin leerlo todo.

```
app/                        la app web (lo único que entra en la imagen de Docker)
  main.py                   ensamblado: ciclo de vida, rutas, estáticos
  config.py                 variables de entorno
  db.py                     persistencia (SQLite) y migraciones
  baggage.py                reglas de equipaje: tarifa -> qué incluye
  pricing.py                compras posibles y sus totales
  links.py                  enlaces de compra de cada aerolínea
  engine.py                 ingesta de resultados y decisión de alertar
  notify.py                 redacción y envío del mensaje
  whatsapp.py               sidecar de WhatsApp
  validation.py             validación de la entrada
  runner_client.py          lo que se le pide a GitHub Actions
  routes/                   HTTP: watches · ingest · settings · whatsapp

scraper/                    solo corre en GitHub Actions
  base.py                   navegador, esperas, utilidades comunes
  fares.py                  lee el panel de tarifas (equipaje por precio)
  wingo.py · jetsmart.py · avianca.py

static/js/                  módulos ES, sin framework
  main.js                   arranque y orquestación
  api.js                    único punto que habla con el servidor
  search-form.js            el formulario (crear y cambiar usan la misma clase)
  watch-card.js             pinta la tarjeta de una búsqueda
  alerts-dialog.js          ⚙ Alertas y la vinculación por QR
  vocab.js · format.js · icons.js · cities.js · store.js · airports.js
```

Dos reglas que sostienen el resto:

- **Los cálculos viven una sola vez, en el backend** (`pricing.py`). El total, la
  combinación elegida y el precio por nivel de equipaje llegan calculados al
  frontend, así la pantalla y el WhatsApp no pueden decir cifras distintas.
- **El scraper extrae, la app interpreta.** `scraper/fares.py` solo lee números y
  palabras de la página; qué significan (y si el dato es leído, derivado o
  estimado) lo decide `app/baggage.py`.

## Equipaje: qué incluye ese precio

La lista de resultados de las tres aerolíneas muestra **un solo precio**, el más
barato ("Desde…", "Tarifa desde"), y en las tres ese precio es **solo un bolso
pequeño bajo el asiento**. La escalera completa vive un clic más adentro, en el
panel de tarifas. El scraper lo abre **una vez por aerolínea y trayecto**, sobre
el vuelo más barato, y lee el equipaje del propio texto de la aerolínea
(`scraper/fares.py`):

| Aerolínea | Escalones leídos | Cómo cotiza el panel |
|---|---|---|
| Wingo | Go Basic → Go Standard (mano 12 kg) → Go Plus (bodega 23 kg) | precios absolutos, equipaje **debajo** del precio |
| JetSMART | pack base → mano → bodega | sobreprecios (`+ $…`), equipaje **encima** del precio |
| Avianca | Basic → Classic (mano **y** bodega juntas) | precios absolutos, equipaje **encima** del precio |

De ahí sale una tarifa por nivel para cada vuelo, y la app marca de dónde viene
cada número:

| Marca | Significa |
|---|---|
| sin marca | precio leído tal cual en la aerolínea |
| `≈` derivado | el salto que cobra hoy esa aerolínea en esa ruta, aplicado a los demás vuelos del día |
| `≈` estimado | no se pudo abrir el panel: tabla de referencia de `app/baggage.py`, editable en ⚙ Alertas |

**Avianca no vende "solo equipaje de mano"**: su escalón con mano ya trae bodega.
Cuando pides mano, la app muestra el precio de ese escalón y lo dice, en vez de
inventar una opción intermedia que no existe.

El filtro de equipaje elige, para cada vuelo, **la tarifa más barata que lo
cumple**; si la aerolínea no lo vende, ese vuelo no aparece como opción.

## Cuándo te escribe (y cuándo no)

Las alertas se disparan **por novedad, no por reloj**, y se comparan contra el
**total de la compra** (pasajeros × tramos, con el equipaje pedido):

| Situación | ¿Te escribe? |
|---|---|
| Compra nueva bajo tu filtro | ✅ sí, al instante |
| La misma compra, mismo total | ❌ no, ya lo sabías |
| Bajó de precio (≥ $1.000) | ✅ sí, con el total anterior |
| Bajó menos de $1.000 | ❌ no, es ruido |
| Subió, pero sigue bajo el filtro | ❌ no, ya lo conocías más barato |

El mensaje trae el total, cada tramo con su hora y su tarifa, **qué equipaje
incluye ese precio**, el valor por persona × la cantidad de personas, y cuánto de
ese valor es el equipaje.

Como se revisa cada 10 minutos, cualquier cambio real te llega en ≤10 min. Se
recuerda el último precio avisado por vuelo (tabla `alerts`), así que no hay
repeticiones. Si el envío falla (WhatsApp sin vincular), la novedad **queda
pendiente** y sale en el siguiente intento.

## Correr en local

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt          # solo la app web
.venv/bin/uvicorn app.main:app --reload --port 8010

# el sidecar de WhatsApp, en otra terminal
cd whatsapp-bot && npm install && node index.js
```

Para trabajar en el scraper hace falta lo del runner:

```bash
.venv/bin/pip install -r requirements-scraper.txt
.venv/bin/pip install --no-deps playwright==1.49.1
.venv/bin/python -m playwright install chromium
.venv/bin/python -m patchright install chromium
APP_URL=http://localhost:8010 INGEST_TOKEN=... .venv/bin/python runner.py
```

Abre http://localhost:8010

> `playwright` va con `--no-deps` a propósito: pinea `pyee==12` y `patchright`
> pinea `pyee 13`. Con `pyee 13` funcionan los dos, pero pip no lo resuelve solo.
>
> Python 3.12 o 3.11. En 3.14 todavía no compilan las ruedas de `greenlet`.

## Configurar WhatsApp

Los mensajes salen **desde tu propio WhatsApp**. El envío lo hace un sidecar en
Node con [Baileys](https://github.com/WhiskeySockets/Baileys) (`whatsapp-bot/`),
que habla el protocolo por WebSocket: sin Chrome y con el QR generado por el
propio WhatsApp.

> Antes esto abría WhatsApp Web con Playwright y fotografiaba el QR. No servía:
> el código se rota cada ~20s y la foto llegaba vencida al celular
> ("No se pudo vincular el dispositivo").

1. **⚙ Alertas → Conectar**. Aparece el código QR (se renueva solo).
2. En el celular: *WhatsApp → Ajustes → Dispositivos vinculados → Vincular
   dispositivo*, y escanea.
3. Escribe los números a avisar, uno por línea:
   ```
   +573054305869
   +573009876543
   ```
4. **Guardar** → **Probar**.

No se guarda ninguna contraseña: la sesión vive en `WA_AUTH_DIR`, igual que un
dispositivo vinculado más.

> El sidecar necesita **Node 20 o superior** (Baileys lo exige). El `nodejs` que
> trae Debian es el 18, por eso el Dockerfile lo instala desde NodeSource.

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

### 3. Botón "Actualizar" de la app

Crea un [token clásico de GitHub](https://github.com/settings/tokens/new) con los
permisos **`repo` + `workflow`**, y **desde la cuenta dueña del repo** (si es de
un colaborador, GitHub responde 403 *"Must have admin rights"*). Ponlo en
Render → Environment:

```
SCRAPE_URL=https://api.github.com/repos/USUARIO/REPO/actions/workflows/scrape.yml/dispatches
GH_TOKEN=<el token>
```

Con esto el botón dispara el workflow al instante (los precios llegan en ~3 min)
y, además, la app se auto-recupera: si Render reinicia y la base queda vacía,
pide una búsqueda sola al minuto de arrancar.

Sin esto el botón no rompe nada: solo avisa que el runner corre cada 10 min.

Notas:

- **Toda variable de entorno debe estar declarada en `render.yaml`**, aunque su
  valor se escriba a mano (`sync: false`). Las que no aparecen ahí, Render las
  borra al redesplegar el Blueprint.
- El plan free duerme a los 15 min: mantenlo despierto con UptimeRobot apuntando
  a `https://TU-APP.onrender.com/health` cada 10 min. `/health` acepta **GET y
  HEAD** a propósito: los monitores usan HEAD y FastAPI no lo añade solo.
- Sin disco no hay BD persistente. Si Render reinicia, la app repone tus fechas
  desde el `localStorage` del navegador la próxima vez que la abras (y toca
  volver a escanear el QR de WhatsApp).

## Frecuencia

Cada 10 minutos, en el `cron` de `.github/workflows/scrape.yml`. Es gratis
porque **en repos públicos los minutos de Actions son ilimitados** (en repos
privados serían ~17.000 min/mes contra un tope de 2.000).

Dos cosas que conviene saber:

- GitHub no garantiza la hora exacta de los `cron`: cuando su cola está cargada
  puede retrasarse 5-20 min. El botón **Actualizar** sí es inmediato.
- Consultar tan seguido sube el riesgo de que un anti-bot bloquee. Si empiezas a
  ver errores seguidos en una aerolínea, sube el intervalo a 20-30 min.

## Si una aerolínea deja de funcionar

Cada scraper está aislado en `scraper/`. Si cambian el HTML, se ajusta el
selector de ese archivo; las otras dos siguen funcionando y la interfaz muestra
el error por aerolínea.

| Archivo | Selector de la lista | Para abrir el panel de tarifas |
|---|---|---|
| `scraper/wingo.py` | `w-org-flight-card` | *Seleccionar* en la tarjeta más barata |
| `scraper/jetsmart.py` | texto `Vuelo Operado por` (tras pulsar *Continuar*) | texto *Tarifa desde* |
| `scraper/avianca.py` | `button.flight-container` | clic en la tarjeta (hay que cerrar antes el aviso de cookies, o el clic no llega) |

Si el panel no abre, el vuelo sigue apareciendo: solo el costo del equipaje pasa
a ser estimado y la interfaz lo avisa. `scraper/fares.py` es genérico (lee
precios absolutos o `+ $`, y equipaje encima o debajo del precio), así que un
cambio de maquetación normalmente se arregla ahí o en el `BAG_SIDE` del scraper.

Los destinos del desplegable están en `static/airports.js`; agregar uno es una
línea más en la región que corresponda.
