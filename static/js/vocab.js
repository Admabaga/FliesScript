/**
 * Vocabulario del equipaje y calidad del precio.
 *
 * Las etiquetas las manda el backend (`/api/watches`) para que la pantalla, el
 * filtro y el WhatsApp digan exactamente lo mismo. Aquí solo se guardan y se
 * ofrecen a quien las pinte.
 */

export const ANY = "any";
export const RANK = { personal: 0, carry_on: 1, checked: 2 };

const estado = { filters: [], label: {}, short: {}, icon: {}, detail: {} };

export function setVocab({ bag_filters, bag_labels } = {}) {
  if (bag_filters) estado.filters = bag_filters;
  Object.assign(estado, bag_labels || {});
}

export const BAG = {
  get filters() {
    return estado.filters;
  },
  label: (lv) => estado.label[lv] || "",
  short: (lv) => estado.short[lv] || estado.label[lv] || "",
  detail: (lv) => estado.detail[lv] || "",
  /** Cómo se lee el filtro en una frase: "con equipaje de mano". */
  frase: (lv) =>
    lv === ANY ? "el más barato, sin exigir equipaje" : (estado.label[lv] || "").toLowerCase(),
};

// De dónde salió el precio del equipaje. Se marca para no vender una cuenta
// propia como dato de la aerolínea.
const FUENTE = {
  scraped: { mark: "", txt: "leído en la aerolínea" },
  derivado: { mark: "≈", txt: "el mismo costo de equipaje que cobra hoy en esa ruta" },
  estimado: { mark: "≈", txt: "estimado: no se pudo abrir el panel de tarifas" },
};

export const fuente = (s) => FUENTE[s] || FUENTE.estimado;
