// Único punto que habla con el servidor. Si mañana cambia una ruta, se cambia
// aquí y en ningún otro archivo.

async function request(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!r.ok) throw new Error((await r.text()).slice(0, 300));
  return r.json();
}

export const api = {
  watches: () => request("/api/watches"),
  addWatch: (body) => request("/api/watches", { method: "POST", body }),
  editWatch: (id, body) => request(`/api/watches/${id}`, { method: "PATCH", body }),
  removeWatch: (id) => request(`/api/watches/${id}`, { method: "DELETE" }),
  scan: () => request("/api/scan", { method: "POST" }),

  settings: () => request("/api/settings"),
  saveSettings: (body) => request("/api/settings", { method: "POST", body }),
  testAlert: () => request("/api/test-alert", { method: "POST" }),

  whatsapp: () => request("/api/whatsapp"),
  whatsappConnect: () => request("/api/whatsapp/connect", { method: "POST" }),
  whatsappLogout: () => request("/api/whatsapp/logout", { method: "POST" }),
};
