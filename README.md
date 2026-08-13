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

No hay API usable: las tres aerolíneas están detrás de anti-bots (Cloudflare en
Wingo, Imperva en JetSMART, Akamai en Avianca) que **también bloquean la simple
consulta**, no solo la compra. Por eso se usa un navegador real headless.

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

## Desplegar en Render

1. Sube el repo a GitHub.
2. Render → **New → Blueprint** → apunta a este repo. Lee `render.yaml`.
3. En **Environment**, pon `WA_RECIPIENTS` (o configúralo luego desde la app).

Notas:

- El `render.yaml` viene en **Starter** con disco en `/data` para que la BD
  sobreviva a los redeploys.
- **Si quieres usar el plan Free:** quita el bloque `disk:` y cambia `plan` a
  `free`, y mantén el servicio despierto con UptimeRobot (el free duerme a los
  15 min). Ojo con dos cosas: 512 MB de RAM van justos con Chromium, y con 0.1
  CPU las páginas cargan mucho más lento (puede que a Avianca no le alcancen los
  60s de timeout). Si ves *Out of memory* o muchos timeouts, sube a Starter.
- Sin disco no hay BD persistente, pero la app repone tus fechas desde el
  `localStorage` del navegador la próxima vez que la abras.

## Frecuencia

60 minutos por defecto. Menos de 30 aumenta el riesgo de bloqueo (Avianca es la
más sensible). Se cambia en **⚙ Alertas → Revisar cada (min)**.

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
