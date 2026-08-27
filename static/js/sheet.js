/**
 * El buscador en pantalla chica.
 *
 * En pantalla grande vive fijo en la columna izquierda y esto no hace nada. Por
 * debajo de 1000px se convierte en una hoja que sube desde abajo, y se abre con
 * el botón flotante: así la pantalla es de las búsquedas, no del formulario.
 *
 * El botón se recoge a un círculo cuando se baja y vuelve con su texto al subir
 * — nunca tapa un precio, pero siempre está a un toque.
 */

const CHICA = window.matchMedia("(max-width: 1000px)");
const DESPLAZAMIENTO_MINIMO = 12;

export class SearchSheet {
  constructor({ onOpen } = {}) {
    this.onOpen = onOpen || (() => {});
    this.pane = document.querySelector("#pane");
    this.fab = document.querySelector("#fab");
    this.scrim = document.querySelector("#scrim");
    this.ultimoScroll = window.scrollY;

    this.fab.addEventListener("click", () => this.toggle());
    this.scrim.addEventListener("click", () => this.close());
    document.querySelector("#paneClose").addEventListener("click", () => this.close());
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.abierta) this.close();
    });
    window.addEventListener("scroll", () => this.#alDesplazar(), { passive: true });
    CHICA.addEventListener("change", () => this.close());
  }

  get abierta() {
    return this.pane.classList.contains("open");
  }

  toggle() {
    this.abierta ? this.close() : this.open();
  }

  open() {
    if (!CHICA.matches) return;
    this.pane.classList.add("open");
    this.scrim.hidden = false;
    this.fab.hidden = true;
    this.fab.setAttribute("aria-expanded", "true");
    document.body.classList.add("sheet-open");
    this.onOpen();
    // el primer campo, para poder escribir de una
    this.pane.querySelector("select, input")?.focus({ preventScroll: true });
  }

  close() {
    this.pane.classList.remove("open");
    this.scrim.hidden = true;
    this.fab.hidden = false;
    this.fab.classList.remove("compacto");
    this.fab.setAttribute("aria-expanded", "false");
    document.body.classList.remove("sheet-open");
  }

  #alDesplazar() {
    if (this.abierta) return;
    const y = window.scrollY;
    if (Math.abs(y - this.ultimoScroll) < DESPLAZAMIENTO_MINIMO) return;
    // bajando: se recoge; subiendo o arriba del todo: vuelve completo
    this.fab.classList.toggle("compacto", y > this.ultimoScroll && y > 90);
    this.ultimoScroll = y;
  }
}
