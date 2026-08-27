/**
 * La tarjeta de una búsqueda: mejor compra, vuelos por aerolínea y qué equipaje
 * trae cada precio.
 *
 * Solo pinta: no llama a la API ni guarda nada. Los totales, las combinaciones y
 * el precio por nivel de equipaje ya vienen calculados del backend
 * (`app/pricing.py`), para que la pantalla y el WhatsApp nunca digan cifras
 * distintas.
 */

import { cityName } from "./cities.js";
import { esc, fecha, money, plural } from "./format.js";
import { IC, icon } from "./icons.js";
import { ANY, BAG, RANK, fuente } from "./vocab.js";

const AEROLINEAS = ["Wingo", "JetSMART", "Avianca"];
const MAX_VUELOS_POR_TRAMO = 6;

/**
 * Semáforo de precio: cuánto peor es una opción que la más barata.
 *
 * Es la respuesta a "¿esto está barato o qué?" sin tener que restar de cabeza:
 * oro lo más barato, verde lo que está ahí mismo, ámbar lo que ya cuesta, y
 * rojo apagado lo que se fue de precio.
 */
function tier(valor, mejor) {
  if (!mejor || !valor) return "t-far";
  const exceso = (valor - mejor) / mejor;
  if (exceso <= 0.005) return "t-best";
  if (exceso <= 0.08) return "t-close";
  if (exceso <= 0.25) return "t-mid";
  return "t-far";
}

const porcentaje = (valor, mejor) => Math.round(((valor - mejor) / mejor) * 100);

/** El precio más bajo de cada tramo, mirando las tres aerolíneas juntas. */
function minimoPorTramo(w) {
  const min = {};
  for (const f of w.flights) {
    if (!f.option) continue;
    const actual = min[f.direction];
    if (actual === undefined || f.option.price < actual) min[f.direction] = f.option.price;
  }
  return min;
}

/**
 * Qué desgloses de tarifas están abiertos. Vive aquí porque es estado de la
 * vista: la pantalla se refresca sola cada 30s y no debe cerrarlos.
 */
export const abiertos = {
  claves: new Set(),
  has: (k) => abiertos.claves.has(k),
  toggle(k) {
    abiertos.claves.has(k) ? abiertos.claves.delete(k) : abiertos.claves.add(k);
  },
};

const claveVuelo = (w, f) => `${w.id}|${f.airline}|${f.direction}|${f.depart_time}`;

// --------------------------------------------------------------- equipaje

/** El equipaje, dicho con palabras: es el dato, no una etiqueta decorativa. */
function textoEquipaje(o, conNombre = true) {
  const nombre = conNombre && o.fare_name ? ` · ${esc(o.fare_name)}` : "";
  return (
    `<span class="lvl ${o.level}" title="${esc(BAG.detail(o.level))} · ${fuente(o.source).txt}">` +
    `${icon(o.level, "ic-sm")}${esc(BAG.short(o.level))}</span>` +
    `<span class="muted">${nombre}</span>`
  );
}

function tablaTarifas(w, f) {
  const filas = [...f.fares].sort((a, b) => a.price - b.price);
  const base = filas[0]?.price ?? 0;
  const elegido = f.option?.level;
  // Avianca, por ejemplo, no vende "solo equipaje de mano": su tarifa con mano
  // ya trae bodega. Se dice, para que el precio más alto se entienda. Solo
  // aplica si se pidió un equipaje concreto: con "el más barato" no hay salto.
  const pedido = RANK[w.bag_level];
  const obligado = pedido !== undefined && RANK[elegido] > pedido;

  return `<div class="fbox">
    <table class="ftable">
      <caption>Qué incluye cada precio · por persona y por trayecto</caption>
      <tbody>
      ${filas
        .map((t) => {
          const extra = t.price - base;
          const fu = fuente(t.source);
          return `<tr class="${t.level === elegido ? "pick" : ""}"
            title="${esc(BAG.detail(t.level))} · ${fu.txt}">
            <td class="lv">${esc(BAG.label(t.level) || t.level)}${
              t.name ? ` <span class="nmi muted">${esc(t.name)}</span>` : ""
            }</td>
            <td class="p">${fu.mark}${money(t.price)}</td>
            <td class="dx muted">${extra ? "+" + money(extra) : "incluido"}</td>
          </tr>`;
        })
        .join("")}
      </tbody>
    </table>
    <p class="fnote muted small">${
      obligado
        ? "Esta aerolínea no vende ese equipaje suelto: la tarifa más barata que lo incluye es esta. "
        : ""
    }${esc(BAG.detail(elegido))}</p>
  </div>`;
}

// --------------------------------------------------------------- vuelos

function filaVuelo(w, f, minTramo) {
  const o = f.option;
  if (!o) return "";
  const nivel = tier(o.price, minTramo);
  const esElMasBarato = nivel === "t-best";
  const clave = claveVuelo(w, f);
  const horas = `${f.depart_time || "--:--"}${f.arrive_time ? " → " + f.arrive_time : ""}`;
  const meta = [f.duration, f.flight_no].filter(Boolean).join(" · ");
  // Se marca el vuelo que forma la mejor compra, para no compararlo a ojo.
  const enLaMejor = [w.best?.out, w.best?.ret]
    .filter(Boolean)
    .some(
      (l) =>
        l.airline === f.airline &&
        l.direction === f.direction &&
        (l.depart_time || "") === (f.depart_time || "")
    );

  return `<details class="fl ${nivel}${enLaMejor ? " inbest" : ""}"${
    abiertos.has(clave) ? " open" : ""
  } data-key="${esc(clave)}">
    <summary>
      <span class="fmain">
        <span class="time">${esc(horas)}</span>
        ${esElMasBarato ? `<span class="cheapest">${IC.best} el más barato</span>` : ""}
        <span class="price">${fuente(o.source).mark}${money(o.price)}<i> p/p</i></span>
      </span>
      <span class="fsub">
        ${textoEquipaje(o)}${meta ? `<span class="muted">· ${esc(meta)}</span>` : ""}
        <span class="more">tarifas ${icon("chevron", "ic-sm")}</span>
      </span>
    </summary>
    ${tablaTarifas(w, f)}
  </details>`;
}

/**
 * El estado trae los fallos por tramo ("… · vuelta: no respondió a tiempo"):
 * cada tramo muestra solo lo suyo.
 */
function mensajeTramo(st, dir) {
  if (!st) return "buscando…";
  const etiqueta = dir === "out" ? "ida" : "vuelta";
  const m = (st.message || "").match(new RegExp(`${etiqueta}:\\s*([^·]+)`, "i"));
  if (m) return m[1].trim();
  if (st.status === "ok") return dir === "out" ? "sin vuelos" : "sin vuelos de vuelta";
  return st.message || st.status;
}

function bloqueAerolinea(w, airline, minTramo) {
  const st = w.status.find((s) => s.airline === airline);
  const suyos = w.flights.filter((f) => f.airline === airline);
  const tramos = w.return_date ? ["out", "ret"] : ["out"];

  const cuerpo = tramos
    .map((dir) => {
      const lista = suyos.filter((f) => f.direction === dir).slice(0, MAX_VUELOS_POR_TRAMO);
      const titulo =
        dir === "out"
          ? `${icon("takeoff", "ic-sm")} Ida · ${fecha(w.date)}`
          : `${icon("landing", "ic-sm")} Vuelta · ${fecha(w.return_date)}`;
      const filas = lista.length
        ? lista.map((f) => filaVuelo(w, f, minTramo[dir])).join("")
        : `<div class="muted small">${esc(mensajeTramo(st, dir))}</div>`;
      return `<div class="dir"><h4>${titulo}</h4>${filas}</div>`;
    })
    .join("");

  const enlace = suyos[0]?.url
    ? `<a href="${esc(suyos[0].url)}" target="_blank" rel="noopener">Abrir ${airline} ${IC.ext}</a>`
    : "";
  const aviso =
    st?.status === "ok" && /estimado/.test(st.message || "")
      ? `<div class="warn-txt small">${icon("warn", "ic-sm")} No abrió el panel de tarifas: el
         costo del equipaje es estimado.</div>`
      : "";

  return `<div class="al" data-a="${airline}">
    <h3><span>${airline}</span>${st?.status === "error" ? icon("warn", "ic-sm") : ""}</h3>
    ${cuerpo}${aviso}${enlace}
  </div>`;
}

// --------------------------------------------------------------- mejor compra

function lineaTramo(etiqueta, leg, dia, conAerolinea) {
  const o = leg.option;
  const horas = `${leg.depart_time || "--:--"}${leg.arrive_time ? " → " + leg.arrive_time : ""}`;
  return `<div class="leg">
    <span class="tag">${icon(etiqueta === "Ida" ? "takeoff" : "landing", "ic-sm")}${etiqueta}</span>
    <span class="ltime">${esc(horas)}</span>
    <span class="lday muted">${fecha(dia)}${conAerolinea ? ` · ${esc(leg.airline)}` : ""}</span>
    <span class="lbag">${textoEquipaje(o)}</span>
    <span class="lprice">${fuente(o.source).mark}${money(o.price)}<i> p/p</i></span>
  </div>`;
}

/** "Wingo ida · Avianca vuelta" o "Todo en Wingo". */
function tituloCombo(c) {
  if (!c.ret) return esc(c.out.airline);
  return c.mixed
    ? `${esc(c.out.airline)} ida · ${esc(c.ret.airline)} vuelta`
    : `Todo en ${esc(c.out.airline)}`;
}

/**
 * Un botón por aerolínea: si la compra es híbrida son dos compras separadas, y
 * cada enlace abre su buscador con la fecha y los pasajeros ya puestos.
 */
function enlacesCompra(c, { compacto = false } = {}) {
  return [c.out, c.ret]
    .filter(Boolean)
    .filter((l, i, todos) => todos.findIndex((x) => x.airline === l.airline) === i)
    .filter((l) => l.url)
    .map((l) => {
      const texto = c.mixed
        ? `${esc(l.airline)}${compacto ? "" : l === c.out ? " (ida)" : " (vuelta)"}`
        : compacto
          ? "Comprar"
          : "Ir a comprar";
      // El botón de la mejor compra va en oro: es la acción que importa.
      const clase = compacto ? "btn mini" : "btn primary";
      return `<a class="${clase}" href="${esc(l.url)}" target="_blank" rel="noopener"
        >${texto} ${icon("ext", "ic-sm")}</a>`;
    })
    .join("");
}

function panelMejorCompra(w) {
  const c = w.best;
  if (!c) {
    return w.return_date && w.flights.length
      ? `<div class="best none muted small">Todavía falta un tramo de vuelta para poder armar
         la compra.</div>`
      : "";
  }

  const equipajePagado =
    (c.out.option.extra || 0) + (c.ret ? c.ret.option.extra || 0 : 0);

  return `<div class="best ${c.hit ? "hit" : ""}">
    <div class="bhead">
      <span class="btitle">${c.hit ? IC.check : IC.best} Mejor compra${
        c.hit ? " · bajo tu filtro" : ""
      }</span>
      <span class="grow"></span>
      <span class="btotal">${fuente(c.source).mark}${money(c.total)}</span>
    </div>
    <div class="bsub">
      <b>${tituloCombo(c)}</b>${
        c.mixed ? " <span class='muted'>· son dos compras, una en cada aerolínea</span>" : ""
      }
      <span class="muted">· ${plural(c.adults, "persona")} · ${
        w.return_date ? "ida y vuelta" : "solo ida"
      }</span>
    </div>
    <div class="legs">
      ${/* La aerolínea solo se repite por tramo si son distintas. */ ""}
      ${lineaTramo("Ida", c.out, w.date, c.mixed)}
      ${c.ret ? lineaTramo("Vta", c.ret, w.return_date, c.mixed) : ""}
    </div>
    <div class="bbreak">
      ${money(c.per_person)} por persona${
        c.ret
          ? ` <span class="muted">(ida ${money(c.out.option.price)} + vuelta ${money(
              c.ret.option.price
            )})</span>`
          : ""
      }${
        // Con un solo pasajero, "× 1 = el mismo número" es ruido.
        c.adults > 1 ? ` × ${c.adults} = <b>${money(c.total)}</b>` : ""
      }
      <span class="muted">· ${
        equipajePagado
          ? `${money(equipajePagado)} de eso es el equipaje`
          : "sin equipaje pago"
      }</span>
    </div>
    <div class="brow">${enlacesCompra(c)}</div>
  </div>`;
}

/**
 * Las otras compras que valen la pena: la mezclada y la de una sola aerolínea
 * conviven, para poder elegir entre ahorrar o comprar de una sola vez.
 */
function bloqueAlternativas(w) {
  const otras = w.alternatives || [];
  if (!otras.length) return "";
  const mejor = w.best ? w.best.total : null;
  return `<div class="alts">
    <div class="atitle">Otras combinaciones</div>
    ${otras
      .map((c) => {
        const dif = mejor ? c.total - mejor : 0;
        const pct = mejor ? porcentaje(c.total, mejor) : 0;
        const nivel = tier(c.total, mejor);
        return `<div class="alt ${nivel}">
        <span class="aname">${icon(c.mixed ? "wallet" : "any", "ic-sm")}${tituloCombo(c)}</span>
        <span class="atimes muted">${esc(c.out.depart_time || "--:--")}${
          c.ret ? " · vuelta " + esc(c.ret.depart_time || "--:--") : ""
        }</span>
        <span class="grow"></span>
        <span class="atotal">${fuente(c.source).mark}${money(c.total)}</span>
        <span class="adif" title="${dif > 0 ? "más caro que la mejor compra" : "mismo precio"}">${
          dif > 0 ? `+${money(dif)} · ${pct}%` : "igual"
        }</span>
        <span class="alinks">${enlacesCompra(c, { compacto: true })}</span>
      </div>`;
      })
      .join("")}
  </div>`;
}

// --------------------------------------------------------------- tarjeta

export function renderWatch(w) {
  const minTramo = minimoPorTramo(w);
  const fechas = w.return_date
    ? `${fecha(w.date)} → ${fecha(w.return_date)}`
    : `${fecha(w.date)} · solo ida`;
  const hayEstimados = w.flights.some((f) => f.option && f.option.source !== "scraped");
  const equipaje = w.bag_level === ANY ? BAG.frase(ANY) : BAG.frase(w.bag_level);

  return `<section class="watch ${w.best?.hit ? "hit" : ""}" data-id="${w.id}">
    <div class="wh">
      <div class="whtop">
        <span class="route">${esc(cityName(w.origin))} → ${esc(cityName(w.destination))}</span>
        <span class="codes muted">${w.origin}-${w.destination}</span>
        <span class="grow"></span>
        <div class="acts">
          <button class="btn mini ghost" data-act="edit">${icon("edit", "ic-sm")}Cambiar</button>
          <button class="btn mini ghost" data-act="scan">${icon("refresh", "ic-sm")}Refrescar</button>
          <button class="btn mini ghost" data-act="del">${icon("trash", "ic-sm")}Eliminar</button>
        </div>
      </div>
      <div class="whsub">
        ${icon("calendar", "ic-sm")}<span class="date">${fechas}</span>
        <span class="dot-sep"></span>${icon("user", "ic-sm")}${plural(w.adults, "adulto")}
        <span class="dot-sep"></span>${icon(w.bag_level, "ic-sm")}<span
          title="${esc(BAG.detail(w.bag_level))}">${esc(equipaje)}</span>
        <span class="dot-sep"></span>aviso si el total baja de ${money(w.max_price)}
      </div>
    </div>
    ${panelMejorCompra(w)}
    ${bloqueAlternativas(w)}
    <div class="airlines">${AEROLINEAS.map((a) => bloqueAerolinea(w, a, minTramo)).join("")}</div>
    <div class="foot muted small">
      Precios por pasajero y por trayecto${
        hayEstimados ? " · <b>≈</b> costo de equipaje no leído en ese vuelo exacto" : ""
      }
    </div>
  </section>`;
}
