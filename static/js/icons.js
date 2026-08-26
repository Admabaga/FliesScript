// Iconos de línea propios: en la interfaz no se usan emojis (los del backend
// son para el texto del WhatsApp, donde sí funcionan).

const svg = (d) =>
  `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;

export const IC = {
  // bolso pequeño bajo el asiento
  personal: svg(`<path d="M7 9h10a2 2 0 0 1 2 2v6a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3v-6a2 2 0 0 1 2-2Z"/>
    <path d="M9.5 9V7.5a2.5 2.5 0 0 1 5 0V9"/>`),
  // maleta de cabina con ruedas
  carry_on: svg(`<rect x="6.5" y="7.5" width="11" height="11" rx="2"/>
    <path d="M10 7.5V5h4v2.5"/><path d="M9.5 18.5v2M14.5 18.5v2"/>`),
  // maleta grande de bodega
  checked: svg(`<rect x="3.5" y="7" width="17" height="12" rx="2"/>
    <path d="M9 7V4.5h6V7"/><path d="M8.5 10.5v5M15.5 10.5v5"/>`),
  // etiqueta de precio: el más barato, sin exigir equipaje
  any: svg(`<path d="M20.3 12.4 11.9 4H4.5v7.4l8.4 8.4a1.4 1.4 0 0 0 2 0l5.4-5.4a1.4 1.4 0 0 0 0-2Z"/>
    <circle cx="8" cy="8" r="1.1"/>`),
  user: svg(`<circle cx="12" cy="8" r="3.2"/><path d="M5.5 20c0-3.2 2.9-5.3 6.5-5.3s6.5 2.1 6.5 5.3"/>`),
  ext: svg(`<path d="M14 4.5h5.5V10"/><path d="M19.5 4.5 12 12"/>
    <path d="M18 14v4.5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4.5"/>`),
  warn: svg(`<path d="M12 4.5 21 19.5H3L12 4.5Z"/><path d="M12 10v4"/><path d="M12 16.8v.2"/>`),
};
