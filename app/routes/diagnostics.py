"""Por qué no arranca la búsqueda automática.

GitHub responde **404 a todo lo que el token no puede ver**, así que un 404 al
disparar el workflow no distingue entre "el token no sirve" y "la URL apunta a
otro repo". Esta ruta lo separa haciendo tres consultas de solo lectura:

    GET /user                          -> ¿de qué cuenta es el token?
    GET /repos/{owner}/{repo}          -> ¿existe y lo ve?
    GET .../actions/workflows          -> ¿está el archivo del workflow?

No devuelve el token ni ningún secreto: solo la cuenta, el repo y el veredicto.
"""

import re

import httpx
from fastapi import APIRouter

from ..config import GH_TOKEN, SCRAPE_URL

router = APIRouter(prefix="/api/diag", tags=["diag"])

# https://api.github.com/repos/OWNER/REPO/actions/workflows/ARCHIVO/dispatches
URL_RE = re.compile(
    r"repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/actions/workflows/(?P<wf>[^/]+)/dispatches"
)


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if GH_TOKEN:
        h["Authorization"] = f"Bearer {GH_TOKEN}"
    return h


@router.get("/github")
async def github():
    out: dict = {
        "scrape_url_configurada": bool(SCRAPE_URL),
        "token_configurado": bool(GH_TOKEN),
        "token_tipo": (GH_TOKEN or "")[:8] + "…" if GH_TOKEN else None,
    }
    if not SCRAPE_URL:
        out["veredicto"] = "Falta SCRAPE_URL en Render."
        return out

    m = URL_RE.search(SCRAPE_URL)
    if not m:
        out["veredicto"] = (
            "SCRAPE_URL no tiene la forma correcta. Debe ser: https://api.github.com/repos/"
            "OWNER/REPO/actions/workflows/scrape.yml/dispatches"
        )
        return out

    owner, repo, wf = m["owner"], m["repo"], m["wf"]
    out["apunta_a"] = {"owner": owner, "repo": repo, "workflow": wf}

    async with httpx.AsyncClient(timeout=20, headers=_headers()) as c:
        try:
            r = await c.get("https://api.github.com/user")
            out["token_de_la_cuenta"] = r.json().get("login") if r.status_code == 200 else None
            out["token_valido"] = r.status_code == 200
            out["scopes"] = r.headers.get("x-oauth-scopes")

            r = await c.get(f"https://api.github.com/repos/{owner}/{repo}")
            out["repo_visible"] = r.status_code == 200

            r = await c.get(f"https://api.github.com/repos/{owner}/{repo}/actions/workflows")
            if r.status_code == 200:
                archivos = [w["path"].split("/")[-1] for w in r.json().get("workflows", [])]
                out["workflows_del_repo"] = archivos
                out["workflow_existe"] = wf in archivos
            else:
                out["workflows_del_repo"] = f"HTTP {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            out["error_de_red"] = str(exc)[:150]
            return out

    # El veredicto, en orden de lo que suele fallar.
    if not out.get("token_valido"):
        out["veredicto"] = (
            "El token no es válido (o no se guardó en Render / falta redesplegar). "
            "Ojo: si lo regeneraste, hay que pegar el valor nuevo."
        )
    elif not out.get("repo_visible"):
        out["veredicto"] = (
            f"El token de {out.get('token_de_la_cuenta')} no ve {owner}/{repo}: revisa que el "
            "nombre del repo en SCRAPE_URL sea exacto (mayúsculas incluidas)."
        )
    elif not out.get("workflow_existe"):
        out["veredicto"] = (
            f"El repo existe, pero no tiene un workflow llamado '{wf}'. En SCRAPE_URL debe ir el "
            f"nombre del archivo tal cual: {out.get('workflows_del_repo')}"
        )
    elif "workflow" not in (out.get("scopes") or ""):
        out["veredicto"] = (
            "Todo apunta bien, pero el token no trae el permiso 'workflow' "
            f"(scopes: {out.get('scopes')})."
        )
    else:
        out["veredicto"] = "Todo en orden: la búsqueda automática puede disparar el workflow."
    return out
