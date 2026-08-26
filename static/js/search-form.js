/**
 * El formulario de búsqueda: ruta, tipo de viaje, adultos, equipaje y filtro.
 *
 * Es una sola clase porque el mismo formulario sirve para crear una búsqueda y
 * para cambiarla desde el diálogo: quien lo use solo le pasa valores iniciales y
 * escucha el envío.
 */

import { cityOptions } from "./cities.js";
import { esc, hoyISO, masDias, money, onlyDigits, plural, thousands } from "./format.js";
import { IC } from "./icons.js";
import { ANY, BAG } from "./vocab.js";

const MAX_ADULTOS = 9;

export class SearchForm {
  /**
   * @param {HTMLFormElement} form  el <form> que envía los datos
   * @param {object} opciones
   * @param {(valores: object) => Promise<void>} opciones.onSubmit
   * @param {string} [opciones.submitLabel]  si viene, el componente pinta su botón
   * @param {HTMLElement} [opciones.container]  dónde pintar los campos (por
   *   defecto el propio form; el diálogo de edición usa un div interno para no
   *   borrar su título ni sus botones)
   */
  constructor(form, { onSubmit, submitLabel = null, container = null } = {}) {
    this.form = form;
    this.container = container || form;
    this.onSubmit = onSubmit;
    this.submitLabel = submitLabel;
    this.form.addEventListener("click", (e) => this.#onClick(e));
    this.form.addEventListener("input", (e) => this.#onInput(e));
    this.form.addEventListener("change", () => this.paint());
    if (this.form.tagName === "FORM") {
      this.form.addEventListener("submit", (e) => this.#onSubmit(e));
    }
  }

  /** Pinta los campos con unos valores (los de una búsqueda existente, o vacío). */
  render(valores = {}) {
    const v = { date: masDias(hoyISO(), 7), adults: 1, bag_level: ANY, ...valores };
    this.container.innerHTML = this.#camposHTML(v) + this.#pieHTML();
    this.paint();
  }

  /** Lo que el usuario tiene puesto, listo para mandar a la API. */
  values() {
    const f = Object.fromEntries(new FormData(this.form));
    const idaYVuelta = this.tripType === "rt";
    return {
      origin: (f.origin || "").toUpperCase(),
      destination: (f.destination || "").toUpperCase(),
      date: f.date || "",
      return_date: idaYVuelta ? f.return_date || "" : "",
      adults: Math.min(MAX_ADULTOS, Math.max(1, Number(f.adults) || 1)),
      bag_level: f.bag_level || ANY,
      max_price: onlyDigits(f.max_price),
    };
  }

  get tripType() {
    return this.form.querySelector('[data-trip="rt"]')?.classList.contains("on") ? "rt" : "ow";
  }

  message(texto) {
    const box = this.form.querySelector(".fmsg");
    if (box) box.textContent = texto;
  }

  /** Devuelve el primer problema que impide guardar, o null. */
  validate() {
    const v = this.values();
    if (!v.date) return "Falta la fecha de ida.";
    if (this.tripType === "rt" && !v.return_date) return "Falta la fecha de vuelta.";
    if (v.origin === v.destination) return "El origen y el destino son el mismo.";
    if (!v.max_price) return "Falta el precio del filtro.";
    return null;
  }

  /** Sincroniza lo que depende de otros campos: vuelta, adultos y la explicación. */
  paint() {
    const v = this.values();
    const idaYVuelta = this.tripType === "rt";

    const pax = this.form.querySelector(".paxlbl");
    if (pax) pax.textContent = plural(v.adults, "adulto");

    const ret = this.form.querySelector(".ret");
    if (ret) {
      ret.hidden = !idaYVuelta;
      const input = ret.querySelector("input");
      input.required = idaYVuelta;
      if (v.date) input.min = v.date; // la vuelta nunca antes de la ida
    }

    const salida = this.form.querySelector('input[name="date"]');
    if (salida) salida.min = hoyISO();

    this.form.querySelectorAll(".bagopt").forEach((el) => {
      el.classList.toggle("on", el.querySelector("input").checked);
    });

    const hint = this.form.querySelector(".hint");
    if (hint) hint.innerHTML = this.#hintHTML(v, idaYVuelta);
  }

  // ------------------------------------------------------------- privado

  #onClick(e) {
    const trip = e.target.closest("[data-trip]");
    if (trip) {
      this.form.querySelectorAll("[data-trip]").forEach((b) => b.classList.toggle("on", b === trip));
      this.#ajustarVuelta(trip.dataset.trip);
      this.paint();
    }
    const paso = e.target.closest("[data-adults]");
    if (paso) {
      const input = this.form.querySelector('input[name="adults"]');
      const n = (Number(input.value) || 1) + Number(paso.dataset.adults);
      input.value = Math.min(MAX_ADULTOS, Math.max(1, n));
      this.paint();
    }
  }

  #onInput(e) {
    if (e.target.classList.contains("money")) {
      e.target.value = thousands(onlyDigits(e.target.value));
    }
    this.paint();
  }

  async #onSubmit(e) {
    e.preventDefault();
    const problema = this.validate();
    if (problema) return this.message(problema);
    await this.onSubmit(this.values());
  }

  /** Al pasar a ida y vuelta, propone una fecha: ahorra dos toques en el móvil. */
  #ajustarVuelta(tipo) {
    const ret = this.form.querySelector('input[name="return_date"]');
    const ida = this.form.querySelector('input[name="date"]').value;
    if (tipo === "rt") {
      if (!ret.value && ida) ret.value = masDias(ida, 3);
    } else {
      ret.value = "";
    }
  }

  #hintHTML(v, idaYVuelta) {
    const tramos = idaYVuelta ? 2 : 1;
    const unidad = v.max_price ? Math.floor(v.max_price / (v.adults * tramos)) : 0;
    const equivalencia =
      unidad && v.adults * tramos > 1
        ? ` Equivale a ${money(unidad)} por persona y por trayecto.`
        : "";
    return `Te aviso cuando el <b>total</b> baje de ahí: ${plural(v.adults, "adulto")} · ${
      idaYVuelta ? "ida y vuelta" : "solo ida"
    } · ${BAG.frase(v.bag_level)}.${equivalencia}`;
  }

  #camposHTML(v) {
    const rt = !!v.return_date;
    return `
    <div class="frow">
      <label>Origen<select name="origin" required>${cityOptions(v.origin || "MDE")}</select></label>
      <label>Destino<select name="destination" required>${cityOptions(v.destination || "BOG")}</select></label>
    </div>

    <div class="seg" role="group" aria-label="Tipo de viaje">
      <button type="button" class="chip${rt ? "" : " on"}" data-trip="ow">Solo ida</button>
      <button type="button" class="chip${rt ? " on" : ""}" data-trip="rt">Ida y vuelta</button>
    </div>

    <div class="frow">
      <label>Fecha de ida<input name="date" type="date" required value="${v.date || ""}"></label>
      <label class="ret"${rt ? "" : " hidden"}>Fecha de vuelta
        <input name="return_date" type="date" value="${v.return_date || ""}">
      </label>
    </div>

    <label class="full">¿Cuántos van?
      <div class="stepper">
        <button type="button" class="btn mini" data-adults="-1" aria-label="Menos adultos">−</button>
        <input name="adults" type="number" min="1" max="${MAX_ADULTOS}" inputmode="numeric" value="${v.adults}">
        <button type="button" class="btn mini" data-adults="1" aria-label="Más adultos">+</button>
        <span class="muted small paxlbl"></span>
      </div>
    </label>

    <fieldset class="bags">
      <legend>¿Con qué equipaje?</legend>
      ${BAG.filters
        .map(
          (f) => `<label class="bagopt">
          <input type="radio" name="bag_level" value="${f.value}"${
            v.bag_level === f.value ? " checked" : ""
          }>
          <span class="bagicon">${IC[f.value] || ""}</span>
          <span class="baglab">${esc(f.label)}</span>
          <span class="bagdet">${esc(f.detail)}</span>
        </label>`
        )
        .join("")}
    </fieldset>

    <label class="full">Avísame si el total baja de
      <input name="max_price" type="text" inputmode="numeric" class="money"
             value="${thousands(v.max_price || 200000)}" required>
    </label>
    <p class="hint"></p>`;
  }

  #pieHTML() {
    return this.submitLabel
      ? `<button class="btn primary wide" type="submit">${esc(this.submitLabel)}</button>
         <p class="fmsg muted small"></p>`
      : `<p class="fmsg muted small"></p>`;
  }
}
