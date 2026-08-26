/**
 * Copia de las búsquedas en el navegador.
 *
 * El plan free de Render no tiene disco: si el servicio reinicia, la base queda
 * vacía. Esta copia es la que la repone al abrir la app.
 */

const KEY = "flight.watches";
const CAMPOS = ["origin", "destination", "date", "return_date", "adults", "bag_level", "max_price"];

const soloCampos = (w) => Object.fromEntries(CAMPOS.map((k) => [k, w[k]]));

export const store = {
  read() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || "[]");
    } catch {
      return [];
    }
  },
  write(watches) {
    try {
      localStorage.setItem(KEY, JSON.stringify(watches.map(soloCampos)));
    } catch {
      /* modo privado o sin cuota: la copia es un extra, no rompe nada */
    }
  },
};
