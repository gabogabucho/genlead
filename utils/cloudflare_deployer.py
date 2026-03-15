"""
Cloudflare Pages Deployer — LeadGen Gabriel Urrutia
Despliega un HTML estático en Cloudflare Pages y configura el dominio custom.
"""

import os
import json
import logging
import sqlite3
import io
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

CF_API_TOKEN  = os.environ.get("CF_API_TOKEN", "")
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "")
CF_PROJECT_PREFIX = os.environ.get("CF_PAGES_PROJECT_PREFIX", "leadgen-")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "leadgen.db")

CF_BASE = "https://api.cloudflare.com/client/v4"


def _cf_request(method: str, path: str, body=None, multipart_data=None) -> dict:
    """Realiza un request a la API de Cloudflare. Retorna el JSON parseado."""
    url = f"{CF_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
    }

    if multipart_data is not None:
        boundary = "----CFBoundary7MA4YWxkTrZu0gW"
        parts = []
        for name, (filename, content, content_type) in multipart_data.items():
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            )
        body_parts = b""
        for i, (name, (filename, content, content_type)) in enumerate(multipart_data.items()):
            part_header = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            body_parts += part_header + (content if isinstance(content, bytes) else content.encode()) + b"\r\n"
        body_parts += f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        data = body_parts
    elif body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    else:
        data = None

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        logger.error(f"CF API error {e.code} {method} {path}: {error_body}")
        try:
            return json.loads(error_body)
        except Exception:
            return {"success": False, "errors": [{"message": error_body}]}


def _get_or_create_project(project_name: str) -> bool:
    """Verifica si el proyecto existe en CF Pages; si no, lo crea."""
    result = _cf_request("GET", f"/accounts/{CF_ACCOUNT_ID}/pages/projects/{project_name}")
    if result.get("success"):
        return True

    # Crear el proyecto
    result = _cf_request("POST", f"/accounts/{CF_ACCOUNT_ID}/pages/projects", body={
        "name": project_name,
        "production_branch": "main",
    })
    if not result.get("success"):
        errors = result.get("errors", [])
        logger.error(f"No se pudo crear el proyecto CF Pages '{project_name}': {errors}")
        return False
    return True


def _upload_deployment(project_name: str, html_content: str) -> str | None:
    """
    Sube el HTML como deployment directo a CF Pages.
    Retorna la URL de deployment o None si falla.
    """
    multipart_data = {
        "index.html": ("index.html", html_content, "text/html"),
        "_worker.js": ("_worker.js", "// empty", "application/javascript"),
    }
    result = _cf_request(
        "POST",
        f"/accounts/{CF_ACCOUNT_ID}/pages/projects/{project_name}/deployments",
        multipart_data=multipart_data,
    )
    if not result.get("success"):
        errors = result.get("errors", [])
        logger.error(f"Error subiendo deployment a CF Pages '{project_name}': {errors}")
        return None

    deployment = result.get("result", {})
    url = deployment.get("url") or f"https://{project_name}.pages.dev"
    return url


def _configure_custom_domain(project_name: str, dominio: str) -> bool:
    """Configura el dominio custom en el proyecto de CF Pages."""
    result = _cf_request(
        "POST",
        f"/accounts/{CF_ACCOUNT_ID}/pages/projects/{project_name}/domains",
        body={"name": dominio},
    )
    if not result.get("success"):
        errors = result.get("errors", [])
        logger.warning(f"No se pudo configurar dominio custom '{dominio}' en CF Pages: {errors}")
        return False
    return True


def deploy_landing(lead_id: int, dominio: str, html_content: str) -> dict:
    """
    Despliega un HTML en Cloudflare Pages y configura el dominio custom.
    Retorna {"ok": bool, "url": str, "deployment_id": str, "error": str}
    """
    if not CF_API_TOKEN or not CF_ACCOUNT_ID:
        msg = "CF_API_TOKEN o CF_ACCOUNT_ID no configurados en .env"
        logger.error(msg)
        return {"ok": False, "error": msg}

    project_name = f"{CF_PROJECT_PREFIX}{lead_id}"

    # 1. Crear o verificar proyecto
    if not _get_or_create_project(project_name):
        return {"ok": False, "error": f"No se pudo crear el proyecto CF Pages '{project_name}'"}

    # 2. Subir deployment
    url = _upload_deployment(project_name, html_content)
    if not url:
        return {"ok": False, "error": "Error subiendo deployment a CF Pages"}

    # 3. Configurar dominio custom (solo si no es .pages.dev)
    if dominio and not dominio.endswith(".pages.dev"):
        _configure_custom_domain(project_name, dominio)

    # 4. Actualizar lead en DB
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "UPDATE leads SET landing_url=?, dominio_status='configurado' WHERE id=?",
            [url, lead_id]
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error actualizando lead {lead_id} en DB tras deploy CF: {e}")

    logger.info(f"Landing desplegada para lead {lead_id}: {url}")
    return {"ok": True, "url": url, "deployment_id": project_name}
