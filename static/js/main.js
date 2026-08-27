/**
 * Arranque y orquestación: trae los datos, decide qué se repinta y conecta los
 * botones con los componentes. Aquí no hay HTML ni cálculos.
 */

import { AlertsDialog } from "./alerts-dialog.js";
import { api } from "./api.js";
import { pintarIconos } from "./icons.js";
import { SearchForm } from "./search-form.js";
import { store } from "./store.js";
import { setVocab } from "./vocab.js";
import { abiertos, renderWatch } from "./watch-card.js";

const $ = (s) => document.querySelector(s);
const REFRESCO_MS = 30_000;

pintarIconos(); // rellena los <span data-icon> del HTML estático

const nuevaBusqueda = new SearchForm($("#watchForm"), {
  submitLabel: "Buscar y vigilar",
  onSubmit: async (valores) => {
    nuevaBusqueda.message("guardando…");
    try {
      await api.addWatch(valores);
      nuevaBusqueda.message("Listo: ya la estoy vigilando.");
      await cargar({ forzar: true });
    } catch (err) {
      nuevaBusqueda.message(err.message);
    }
  },
});

const edicion = new SearchForm($("#editForm"), {
  container: $("#editFields"),
  onSubmit: async (valores) => {
    try {
      await api.editWatch(edicion.watchId, valores);
      $("#editDlg").close();
      await cargar({ forzar: true });
    } catch (err) {
      edicion.message(err.message);
    }
  },
});

new AlertsDialog({ onSaved: () => cargar({ forzar: true }) });

// --------------------------------------------------------------- carga

let ultimoJson = "";
let formularioListo = false;

/**
 * Si el servidor perdió los datos (redeploy sin disco), los repone desde el
 * navegador antes de pintar.
 */
async function reponerDesdeLocal(delServidor) {
  const copia = store.read();
  if (!copia.length || delServidor.length) return false;
  for (const w of copia) await api.addWatch(w);
  return true;
}

async function cargar({ forzar = false } = {}) {
  const data = await api.watches();
  setVocab(data);
  $("#loading").hidden = true;

  // El formulario se pinta una sola vez: necesita el vocabulario del backend, y
  // repintarlo borraría lo que se esté escribiendo.
  if (!formularioListo) {
    nuevaBusqueda.render();
    formularioListo = true;
  }

  if (await reponerDesdeLocal(data.watches)) return cargar({ forzar: true });
  store.write(data.watches);

  // Repintar solo cuando algo cambió: si no, el refresco cierra los desgloses.
  const json = JSON.stringify(data.watches);
  if (forzar || json !== ultimoJson) {
    ultimoJson = json;
    $("#watches").innerHTML = data.watches.map(renderWatch).join("");
    $("#empty").hidden = data.watches.length > 0;
  }
  $("#lastScan").textContent = textoRevision(data);
}

/**
 * La línea de estado. Dice hace cuánto son los precios y, si la búsqueda
 * automática está fallando, por qué: es lo primero que se quiere saber cuando
 * los precios se ven viejos.
 */
function textoRevision({ running, last_scan, auto }) {
  if (running) return "buscando vuelos…";

  let base = "sin revisiones aún";
  if (auto && auto.edad_min !== null && auto.edad_min !== undefined) {
    const m = auto.edad_min;
    base =
      m < 1
        ? "precios de hace un momento"
        : m < 60
          ? `precios de hace ${m} min`
          : `precios de hace ${Math.floor(m / 60)} h ${m % 60} min`;
  } else if (last_scan) {
    base = "última revisión: " + last_scan.replace("T", " ");
  }

  if (auto && !auto.activo) return base + " · búsqueda automática apagada";
  // El detalle solo importa cuando algo va mal: si los precios están frescos, sobra.
  if (auto && auto.detalle && auto.edad_min > 25) return base + " · " + auto.detalle;
  return base;
}

// --------------------------------------------------------------- eventos

$("#watches").addEventListener("click", async (e) => {
  // Los desgloses se recuerdan para que el refresco automático no los cierre.
  const resumen = e.target.closest("summary");
  if (resumen) return abiertos.toggle(resumen.closest("details").dataset.key);

  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const id = Number(btn.closest(".watch").dataset.id);

  if (btn.dataset.act === "del") {
    if (!confirm("¿Eliminar esta búsqueda?")) return;
    await api.removeWatch(id);
    await cargar({ forzar: true });
  }
  if (btn.dataset.act === "scan") {
    const r = await api.scan();
    $("#lastScan").textContent = r.detalle || "buscando vuelos…";
  }
  if (btn.dataset.act === "edit") await abrirEdicion(id);
});

async function abrirEdicion(id) {
  const { watches } = await api.watches();
  const w = watches.find((x) => x.id === id);
  if (!w) return;
  edicion.watchId = id;
  edicion.render(w);
  edicion.message("");
  $("#editDlg").showModal();
}

$("#editForm").addEventListener("click", (e) => {
  if (e.target.closest("[data-close]")) $("#editDlg").close();
});

$("#btnScan").addEventListener("click", async () => {
  $("#lastScan").textContent = "pidiendo búsqueda…";
  const r = await api.scan();
  $("#lastScan").textContent = r.detalle || (r.started ? "buscando vuelos…" : "no se pudo pedir");
});

$("#loading").hidden = false;
cargar().catch(() => {
  $("#loading").hidden = true;
  $("#lastScan").textContent = "no se pudo conectar con el servidor";
});
setInterval(() => cargar().catch(() => {}), REFRESCO_MS);
