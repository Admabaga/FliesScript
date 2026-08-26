/**
 * El diálogo de ⚙ Alertas: a quién avisar, la vinculación de WhatsApp por QR y
 * el respaldo del precio del equipaje.
 */

import { api } from "./api.js";
import { onlyDigits, thousands } from "./format.js";

const $ = (s) => document.querySelector(s);
const ESPERA_QR_MS = 2000;
const INTENTOS_QR = 120; // ~4 min: el código se rota cada ~20s

export class AlertsDialog {
  constructor({ onSaved } = {}) {
    this.onSaved = onSaved || (() => {});
    this.dlg = $("#cfg");
    this.form = $("#cfgForm");

    $("#btnCfg").addEventListener("click", () => this.open());
    $("#btnWa").addEventListener("click", () => this.#vincular());
    $("#btnSaveCfg").addEventListener("click", () => this.#guardar());
    $("#btnTest").addEventListener("click", () => this.#probar());
    this.form.addEventListener("input", (e) => {
      if (e.target.classList.contains("money")) {
        e.target.value = thousands(onlyDigits(e.target.value));
      }
    });
  }

  async open() {
    const ajustes = await api.settings();
    for (const [k, v] of Object.entries(ajustes)) {
      const el = this.form.querySelector(`[name="${k}"]`);
      if (!el) continue;
      el.value = v && el.classList.contains("money") ? thousands(onlyDigits(v)) : v || "";
    }
    this.#mensaje("");
    this.dlg.showModal();
    this.#pintarWa(await api.whatsapp());
  }

  #mensaje(txt) {
    $("#cfgMsg").textContent = txt;
  }

  async #guardar() {
    const f = Object.fromEntries(new FormData(this.form));
    await api.saveSettings({
      ...f,
      bag_carryon_cop: String(onlyDigits(f.bag_carryon_cop) || ""),
      bag_checked_cop: String(onlyDigits(f.bag_checked_cop) || ""),
    });
    this.#mensaje("Guardado.");
    this.onSaved();
  }

  async #probar() {
    this.#mensaje("enviando…");
    const r = await api.testAlert();
    this.#mensaje(r.results.join(" · "));
  }

  #pintarWa(s) {
    const dot = $("#waDot");
    const btn = $("#btnWa");
    dot.className =
      "dot" + (s.status === "conectado" ? " on" : s.status === "esperando_qr" ? " wait" : "");
    $("#waTxt").textContent = s.detalle || AlertsDialog.#textoEstado(s.status);
    btn.textContent = s.status === "conectado" ? "Revincular" : "Conectar";
    btn.dataset.conectado = s.status === "conectado" ? "1" : "";
    btn.disabled = false;

    const caja = $("#waQr");
    if (s.qr) {
      $("#waImg").src = s.qr;
      caja.hidden = false;
    } else {
      caja.hidden = true;
    }
  }

  static #textoEstado(status) {
    return (
      {
        conectado: "WhatsApp vinculado ✅",
        esperando_qr: "Escanea el código (se renueva solo)",
        abriendo: "Abriendo WhatsApp Web…",
      }[status] || "WhatsApp sin vincular"
    );
  }

  async #vincular() {
    const btn = $("#btnWa");
    const yaEstaba = btn.dataset.conectado;
    btn.disabled = true;
    btn.textContent = "Abriendo…";
    this.#pintarWa(yaEstaba ? await api.whatsappLogout() : await api.whatsappConnect());

    // WhatsApp rota el código cada ~20s: hay que repintarlo o vence antes de
    // que alcance a escanearlo.
    for (let i = 0; i < INTENTOS_QR; i++) {
      await new Promise((r) => setTimeout(r, ESPERA_QR_MS));
      const s = await api.whatsapp();
      this.#pintarWa(s);
      if (s.status === "conectado" || s.status === "desconectado") return;
    }
  }
}
