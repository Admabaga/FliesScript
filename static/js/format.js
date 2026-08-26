// Formato: una sola forma de escribir plata, fechas y texto en toda la app.

export const money = (n) =>
  "$" + Number(n).toLocaleString("es-CO", { maximumFractionDigits: 0 });

export const onlyDigits = (s) => Number(String(s).replace(/\D/g, "")) || 0;

/** Miles con punto mientras se escribe: 200000 -> 200.000 */
export const thousands = (n) => (n ? Number(n).toLocaleString("es-CO") : "");

/** Escapa lo que se interpola en HTML: los nombres vienen de la aerolínea. */
export const esc = (s) =>
  String(s ?? "").replace(/[<>&"]/g, (c) => `&#${c.charCodeAt(0)};`);

const DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"];
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/**
 * '2026-09-25' -> 'vie 25 sep'.
 * Se parte a mano porque `new Date('2026-09-25')` se lee como UTC y en Colombia
 * muestra el día anterior.
 */
export function fecha(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return `${DIAS[(dt.getDay() + 6) % 7]} ${d} ${MESES[m - 1]}`;
}

export const hoyISO = () => new Date().toISOString().slice(0, 10);

/** La misma fecha, N días después, en ISO. */
export function masDias(iso, dias) {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + dias);
  return d.toISOString().slice(0, 10);
}

export const plural = (n, singular, pl = null) =>
  `${n} ${n === 1 ? singular : pl || singular + "s"}`;
