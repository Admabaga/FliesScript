/**
 * Flight — sidecar de WhatsApp (Baileys)
 *
 * Habla el protocolo de WhatsApp por WebSocket: sin Chrome, sin capturas de
 * pantalla y sin QR vencidos. La sesión se guarda en disco y se restaura sola.
 *
 * Solo escucha en 127.0.0.1: únicamente la app de Python (en el mismo
 * contenedor) puede hablarle.
 */

import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";
import express from "express";
import pino from "pino";
import QRCode from "qrcode";
import { rm } from "fs/promises";

const PORT = parseInt(process.env.WA_PORT ?? "3001", 10);
const AUTH_DIR = process.env.WA_AUTH_DIR ?? "./auth_info_baileys";

let sock = null;
/** Lo que la app de Python consulta: estado y QR listo para pintar. */
const state = { status: "desconectado", qr: null };

async function startBot() {
  const { state: auth, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth,
    logger: pino({ level: "silent" }),
    browser: ["Flight", "Chrome", "1.0.0"],
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      // Baileys entrega el texto del QR; aquí se vuelve imagen para la web.
      state.status = "esperando_qr";
      state.qr = await QRCode.toDataURL(qr, { margin: 1, width: 320 });
      console.log("[wa] QR nuevo listo para escanear");
    }

    if (connection === "open") {
      state.status = "conectado";
      state.qr = null;
      console.log("[wa] WhatsApp vinculado");
    }

    if (connection === "close") {
      const code =
        lastDisconnect?.error instanceof Boom
          ? lastDisconnect.error.output.statusCode
          : 0;
      state.status = "desconectado";
      state.qr = null;

      if (code === DisconnectReason.loggedOut) {
        console.warn("[wa] Sesión cerrada desde el celular; se pedirá un QR nuevo");
        await rm(AUTH_DIR, { recursive: true, force: true }).catch(() => {});
        setTimeout(startBot, 2000);
      } else {
        console.warn(`[wa] Desconectado (código ${code}); reconectando…`);
        startBot();
      }
    }
  });
}

const app = express();
app.use(express.json({ limit: "1mb" }));

app.get("/status", (_req, res) => res.json(state));

app.post("/send", async (req, res) => {
  const { to, message } = req.body ?? {};
  if (!to || !message) return res.status(400).json({ error: "faltan to y message" });
  if (state.status !== "conectado") {
    return res.status(503).json({ error: "WhatsApp sin vincular" });
  }
  try {
    const num = String(to).replace(/\D/g, "");
    await sock.sendMessage(`${num}@s.whatsapp.net`, { text: message });
    res.json({ ok: true });
  } catch (err) {
    console.error("[wa] error enviando:", err.message);
    res.status(500).json({ error: err.message });
  }
});

/** Fuerza un QR nuevo: borra la sesión y reconecta. */
app.post("/logout", async (_req, res) => {
  try {
    await sock?.logout().catch(() => {});
  } catch {}
  await rm(AUTH_DIR, { recursive: true, force: true }).catch(() => {});
  state.status = "desconectado";
  state.qr = null;
  setTimeout(startBot, 1000);
  res.json({ ok: true });
});

app.listen(PORT, "127.0.0.1", () => console.log(`[wa] sidecar en :${PORT}`));
startBot();
