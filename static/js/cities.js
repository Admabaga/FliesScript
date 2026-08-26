// Ciudades: el desplegable y el nombre para mostrar, en un solo lugar.

import { AIRPORTS } from "./airports.js";

const NOMBRE = {};
for (const lista of Object.values(AIRPORTS)) {
  for (const [code, name] of lista) NOMBRE[code] = name;
}

export const cityName = (code) => NOMBRE[code] || code;

export function cityOptions(selected) {
  return Object.entries(AIRPORTS)
    .map(
      ([region, lista]) =>
        `<optgroup label="${region}">` +
        lista
          .map(
            ([code, name]) =>
              `<option value="${code}"${code === selected ? " selected" : ""}>${name} · ${code}</option>`
          )
          .join("") +
        "</optgroup>"
    )
    .join("");
}
