const $ = (s) => document.querySelector(s);
const LS_KEY = "flight.watches";
const AIRLINES = ["Wingo", "JetSMART", "Avianca"];

// Miles con punto en todo lo que se muestra y en lo que se escribe.
const money = (n) => "$" + Number(n).toLocaleString("es-CO", { maximumFractionDigits: 0 });
const onlyDigits = (s) => Number(String(s).replace(/\D/g, "")) || 0;

const local = {
  read: () => JSON.parse(localStorage.getItem(LS_KEY) || "[]"),
  write: (w) => localStorage.setItem(LS_KEY, JSON.stringify(w)),
};

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// Si el servidor perdió los datos (redeploy sin disco), los repone desde el navegador.
async function restoreFromLocal(serverWatches) {
  const cached = local.read();
  if (!cached.length || serverWatches.length) return false;
  for (const w of cached) await api("/api/watches", { method: "POST", body: w });
  return true;
}

function renderAirline(w, airline, flights) {
  const st = w.status.find((s) => s.airline === airline);
  const list = flights.slice(0, 8);
  const rows = list.length
    ? list
        .map(
          (f) => `<div class="fl ${f.price <= w.max_price ? "under" : ""}">
            <span class="time">${f.depart_time || "--:--"}${f.arrive_time ? " → " + f.arrive_time : ""}</span>
            <span class="meta">${f.duration || ""} ${f.flight_no || ""}</span>
            <span class="price">${money(f.price)}</span>
          </div>`
        )
        .join("")
    : `<div class="muted small">${st ? st.message || st.status : "buscando…"}</div>`;
  const link = list[0]?.url
    ? `<a href="${list[0].url}" target="_blank" rel="noopener">Abrir ${airline} ↗</a>`
    : "";
  return `<div class="al" data-a="${airline}">
    <h3><span>${airline}</span>${st?.status === "error" ? " ⚠️" : ""}</h3>${rows}${link}
  </div>`;
}

function renderWatch(w) {
  const byAirline = {};
  for (const f of w.flights) (byAirline[f.airline] ||= []).push(f);
  const cheapest = w.flights.length ? Math.min(...w.flights.map((f) => f.price)) : null;
  const hit = cheapest !== null && cheapest <= w.max_price;

  return `<section class="watch ${hit ? "hit" : ""}" data-id="${w.id}">
    <div class="wh">
      <span class="route">${CITY[w.origin] || w.origin} → ${CITY[w.destination] || w.destination}</span>
      <span class="codes muted">${w.origin}-${w.destination}</span>
      <span class="date">${w.date}</span>
      <span class="grow"></span>
      <span class="badge">&lt; ${money(w.max_price)}</span>
      ${cheapest !== null ? `<span class="badge ${hit ? "good" : ""}">mejor ${money(cheapest)}</span>` : ""}
      <div class="acts">
        <button class="btn mini" data-act="edit">Cambiar precio</button>
        <button class="btn mini" data-act="scan">Refrescar</button>
        <button class="btn mini" data-act="del">Eliminar</button>
      </div>
    </div>
    <div class="airlines">${AIRLINES.map((a) => renderAirline(w, a, byAirline[a] || [])).join("")}</div>
  </section>`;
}

async function load() {
  const data = await api("/api/watches");
  if (await restoreFromLocal(data.watches)) return load();
  local.write(
    data.watches.map(({ origin, destination, date, max_price }) => ({
      origin,
      destination,
      date,
      max_price,
    }))
  );
  $("#watches").innerHTML = data.watches.map(renderWatch).join("");
  $("#empty").style.display = data.watches.length ? "none" : "block";
  $("#lastScan").textContent = data.running
    ? "buscando vuelos…"
    : data.last_scan
      ? "última revisión: " + data.last_scan.replace("T", " ")
      : "sin revisiones aún";
}

// Llena los desplegables de ciudades para no tener que saberse los códigos.
const CITY = {};
function fillAirports(select, selected) {
  select.innerHTML = Object.entries(AIRPORTS)
    .map(
      ([region, list]) =>
        `<optgroup label="${region}">` +
        list
          .map(([code, name]) => {
            CITY[code] = name;
            return `<option value="${code}"${code === selected ? " selected" : ""}>${name} · ${code}</option>`;
          })
          .join("") +
        "</optgroup>"
    )
    .join("");
}
fillAirports($('select[name="origin"]'), "MDE");
fillAirports($('select[name="destination"]'), "BOG");

// Formatea el precio mientras se escribe: 200000 -> 200.000
$(".money").addEventListener("input", (e) => {
  const v = onlyDigits(e.target.value);
  e.target.value = v ? v.toLocaleString("es-CO") : "";
});

$("#watchForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  await api("/api/watches", {
    method: "POST",
    body: {
      origin: f.origin.toUpperCase(),
      destination: f.destination.toUpperCase(),
      date: f.date,
      max_price: onlyDigits(f.max_price),
    },
  });
  load();
});

$("#watches").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const id = btn.closest(".watch").dataset.id;
  const act = btn.dataset.act;
  if (act === "del" && confirm("¿Eliminar esta fecha?")) {
    await api(`/api/watches/${id}`, { method: "DELETE" });
  }
  if (act === "scan") await api("/api/scan", { method: "POST" });
  if (act === "edit") {
    const v = prompt("Avísame si baja de (COP):");
    if (v) await api(`/api/watches/${id}`, { method: "PATCH", body: { max_price: onlyDigits(v) } });
  }
  load();
});

$("#btnScan").addEventListener("click", async () => {
  await api("/api/scan", { method: "POST" });
  $("#lastScan").textContent = "buscando vuelos…";
});

// ---- WhatsApp: vinculación por QR ----
function paintWa(s) {
  const dot = $("#waDot"), txt = $("#waTxt"), btn = $("#btnWa");
  dot.className = "dot" + (s.status === "conectado" ? " on" : s.status === "esperando_qr" ? " wait" : "");
  txt.textContent =
    s.detalle ||
    (s.status === "conectado"
      ? "WhatsApp vinculado"
      : s.status === "esperando_qr"
        ? "Escanea el código con tu celular"
        : "WhatsApp sin vincular");
  btn.textContent = s.status === "conectado" ? "Revincular" : "Conectar";
  btn.disabled = false;
  const box = $("#waQr");
  if (s.qr) {
    $("#waImg").src = s.qr;
    box.hidden = false;
  } else {
    box.hidden = true;
  }
}

async function connectWa() {
  const btn = $("#btnWa");
  btn.disabled = true;
  btn.textContent = "Abriendo…";
  const first = await api("/api/whatsapp/connect", { method: "POST" });
  paintWa(first);
  if (first.status === "ocupado") return;
  // se queda esperando el escaneo, refrescando el QR si vence
  for (let i = 0; i < 4; i++) {
    const s = await api("/api/whatsapp/pair", { method: "POST" });
    paintWa(s);
    if (s.status === "conectado") return;
  }
}
$("#btnWa").addEventListener("click", connectWa);

$("#btnCfg").addEventListener("click", async () => {
  const s = await api("/api/settings");
  for (const [k, v] of Object.entries(s)) {
    const el = $(`#cfgForm [name="${k}"]`);
    if (el) el.value = v;
  }
  $("#cfgMsg").textContent = "";
  $("#cfg").showModal();
  paintWa(await api("/api/whatsapp"));
});
$("#btnSaveCfg").addEventListener("click", async () => {
  await api("/api/settings", { method: "POST", body: Object.fromEntries(new FormData($("#cfgForm"))) });
  $("#cfgMsg").textContent = "Guardado.";
});
$("#btnTest").addEventListener("click", async () => {
  $("#cfgMsg").textContent = "enviando…";
  const r = await api("/api/test-alert", { method: "POST" });
  $("#cfgMsg").textContent = r.results.join(" · ");
});

$('input[name="date"]').valueAsDate = new Date(Date.now() + 7 * 864e5);
load();
setInterval(load, 30000);
