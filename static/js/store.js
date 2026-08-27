/**
 * Copia de las búsquedas en el navegador.
 *
 * El plan free de Render no tiene disco: si el servicio reinicia, la base queda
 * vacía. Esta copia es la que la repone al abrir la app.
 */

const KEY = "flight.watches";
const CAMPOS = ["origin", "destination", "date", "return_date", "adults", "bag_level", "max_price"];

const soloCampos = (w) => Object.fromEntries(CAMPOS.map((k) => [k, w[k]]));
const clave = (w) => CAMPOS.slice(0, 6).map((k) => w[k] ?? "").join("|");

/** Sin repetidas: si la copia trae dos iguales, reponerlas duplicaría todo. */
function unicas(watches) {
  const vistas = new Set();
  return watches.filter((w) => {
    const k = clave(w);
    if (vistas.has(k)) return false;
    vistas.add(k);
    return true;
  });
}

export const store = {
  read() {
    try {
      return unicas(JSON.parse(localStorage.getItem(KEY) || "[]"));
    } catch {
      return [];
    }
  },
  write(watches) {
    try {
      localStorage.setItem(KEY, JSON.stringify(unicas(watches.map(soloCampos))));
    } catch {
      /* modo privado o sin cuota: la copia es un extra, no rompe nada */
    }
  },
};
