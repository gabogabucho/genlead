import os
import sqlite3
from datetime import datetime

from config.settings import RUBROS, CIUDADES_ARG

# Dominios que NO son sitios web propios (redes sociales, páginas de terceros)
_TERCEROS = (
    "instagram.com", "facebook.com", "linktr.ee", "linktree.com",
    "wa.me", "whatsapp.com", "twitter.com", "x.com", "tiktok.com",
    "youtube.com", "maps.google.com", "goo.gl", "g.co",
    "yelp.com", "tripadvisor.com", "mercadolibre.com", "mercadoshops.com",
    "wix.com/", "my.strikingly.com", "weebly.com", "jimdo.com",
)

def _tiene_web_propia(url: str) -> bool:
    """Retorna True si la URL es un sitio web propio (no una red social ni página de terceros)."""
    if not url:
        return False
    url_lower = url.lower()
    return not any(t in url_lower for t in _TERCEROS)
from scrapers.google_places_scraper import (
    geocode_ciudad,
    buscar_lugares,
    obtener_detalle,
    normalizar_lead,
    deduplicar,
)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "leadgen.db")


def _get_db(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _append_log(conn: sqlite3.Connection, run_id: int, msg: str) -> None:
    cur = conn.execute("SELECT log FROM pipeline_runs WHERE id = ?", [run_id]).fetchone()
    prev = (cur["log"] or "") if cur else ""
    stamp = datetime.now().strftime("%H:%M:%S")
    new_log = (prev + "\n" if prev else "") + f"[{stamp}] {msg}"
    conn.execute("UPDATE pipeline_runs SET log = ? WHERE id = ?", [new_log, run_id])


def _update_run(conn: sqlite3.Connection, run_id: int, **fields) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE pipeline_runs SET {set_clause} WHERE id = ?",
        list(fields.values()) + [run_id],
    )


def _lead_exists(conn: sqlite3.Connection, empresa: str, ciudad: str, url: str) -> bool:
    if url:
        row = conn.execute("SELECT id FROM leads WHERE url = ? LIMIT 1", [url]).fetchone()
        if row:
            return True
    row = conn.execute(
        "SELECT id FROM leads WHERE lower(empresa) = lower(?) AND lower(ciudad) = lower(?) LIMIT 1",
        [empresa, ciudad],
    ).fetchone()
    return bool(row)


def run_pipeline(rubro_slug: str, ciudades: list[str] | None, limit: int, run_id: int | None = None,
                 db_path: str | None = None, tipo_web: str = "sin_web") -> dict:
    if rubro_slug not in RUBROS:
        raise ValueError(f"Rubro '{rubro_slug}' no existe en settings.")

    rubro_cfg = RUBROS[rubro_slug]
    ciudades = ciudades or CIUDADES_ARG
    ciudades = [c.strip() for c in ciudades if c.strip()]

    conn = _get_db(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO rubros (slug, nombre) VALUES (?, ?)",
            [rubro_slug, rubro_cfg["nombre"]],
        )
        if run_id:
            _append_log(conn, run_id, f"Pipeline iniciado para {rubro_slug} en {len(ciudades)} ciudad(es)")
            conn.commit()

        leads_raw = []
        place_ids_vistos = set()

        for ciudad in ciudades:
            coords = geocode_ciudad(ciudad)
            if not coords:
                if run_id:
                    _append_log(conn, run_id, f"No se pudo geocodificar: {ciudad}")
                continue
            for query in rubro_cfg["queries"]:
                resultados = buscar_lugares(query, coords)
                for r in resultados:
                    place_id = r.get("place_id")
                    if not place_id or place_id in place_ids_vistos:
                        continue
                    place_ids_vistos.add(place_id)
                    detalle = obtener_detalle(place_id)
                    lead = normalizar_lead(detalle, ciudad, rubro_cfg["nombre"])
                    leads_raw.append(lead)

        leads_unicos = deduplicar(leads_raw)

        # Filtrar por tipo de web
        if tipo_web == "sin_web":
            leads_unicos = [l for l in leads_unicos if not _tiene_web_propia(l.get("WEBSITE", ""))]
        elif tipo_web == "con_web":
            leads_unicos = [l for l in leads_unicos if _tiene_web_propia(l.get("WEBSITE", ""))]

        leads_unicos = leads_unicos[: max(0, int(limit or 0))] if limit else leads_unicos

        if run_id:
            _update_run(conn, run_id, leads_encontrados=len(leads_unicos))
            _append_log(conn, run_id, f"Leads encontrados: {len(leads_unicos)}")
            conn.commit()

        inserted = 0
        for lead in leads_unicos:
            empresa = lead.get("COMPANY", "").strip()
            ciudad = lead.get("CIUDAD", "").strip()
            url = lead.get("WEBSITE", "").strip()
            telefono = lead.get("PHONE", "").strip()
            maps_url = lead.get("GOOGLE_MAPS_URL", "").strip()
            notas = lead.get("NOTAS", "").strip()

            if not empresa:
                continue
            if _lead_exists(conn, empresa, ciudad, url):
                continue

            conn.execute(
                """
                INSERT INTO leads (
                    rubro_slug, empresa, ciudad, url, email, telefono, google_maps_url,
                    status, notas, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    rubro_slug,
                    empresa,
                    ciudad,
                    url,
                    lead.get("EMAIL", ""),
                    telefono,
                    maps_url,
                    "nuevo",
                    notas,
                    datetime.now().isoformat(),
                ],
            )
            inserted += 1

        if run_id:
            _update_run(conn, run_id, status="completed", completed_at=datetime.now().isoformat())
            _append_log(conn, run_id, f"Leads insertados: {inserted}")
            conn.commit()

        return {"leads_encontrados": len(leads_unicos), "leads_insertados": inserted}
    finally:
        conn.commit()
        conn.close()
