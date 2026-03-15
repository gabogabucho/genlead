"""
Post Processor — LeadGen Gabriel Urrutia

Se ejecuta automáticamente después de que CrewAI completa el procesamiento de un lead
(status='landing_lista'). Hace dos cosas:
  1. Deploya la landing a Cloudflare Pages (URL demo .pages.dev)
  2. Envía el pitch por WhatsApp con el link de la demo

Si algo falla, el lead queda en 'landing_lista' para retry manual desde el dashboard.
"""

import os
import sqlite3
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "leadgen.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _log_activity(conn, lead_id: int, tipo: str, descripcion: str, metadata: dict = None):
    conn.execute(
        "INSERT INTO activities (lead_id, tipo, descripcion, metadata) VALUES (?,?,?,?)",
        [lead_id, tipo, descripcion, json.dumps(metadata) if metadata else None],
    )


def _log_wa_conversation(conn, lead_id: int, direction: str, message: str, wa_msg_id: str = None):
    conn.execute(
        "INSERT INTO whatsapp_conversations (lead_id, direction, message, wa_msg_id) VALUES (?,?,?,?)",
        [lead_id, direction, message, wa_msg_id],
    )


def post_process_lead(lead_id: int) -> bool:
    """
    Deploya landing a CF Pages y envía WhatsApp con el link de la demo.

    Returns:
        True si ambas operaciones fueron exitosas, False si alguna falló.
    """
    from utils.cloudflare_deployer import deploy_landing
    from utils.whatsapp_sender import send_text

    conn = _get_conn()
    try:
        lead = conn.execute("SELECT * FROM leads WHERE id = ?", [lead_id]).fetchone()
        if not lead:
            logger.error(f"[PostProcessor] Lead {lead_id} no encontrado")
            return False

        if lead["status"] != "landing_lista":
            logger.info(f"[PostProcessor] Lead {lead_id} no está en 'landing_lista' (status: {lead['status']}), saltando")
            return False

        if not lead["landing_html"]:
            logger.warning(f"[PostProcessor] Lead {lead_id} no tiene landing_html, saltando deploy")
            return False

        # ── 1. Deploy a Cloudflare Pages (URL demo .pages.dev) ──────────────
        demo_domain = f"leadgen-{lead_id}.pages.dev"
        result = deploy_landing(lead_id, demo_domain, lead["landing_html"])

        if not result.get("ok"):
            error_msg = result.get("error", "Error desconocido en CF deploy")
            logger.error(f"[PostProcessor] CF deploy falló para lead {lead_id}: {error_msg}")
            _log_activity(conn, lead_id, "nota",
                          f"Error en CF deploy: {error_msg}",
                          {"error": error_msg})
            conn.commit()
            return False

        landing_url = result["url"]
        logger.info(f"[PostProcessor] Landing deployada: {landing_url}")

        # ── 2. Construir mensaje WhatsApp con la URL de la demo ──────────────
        base_text = lead["whatsapp_text"] or ""
        if not base_text:
            empresa = lead["empresa"] or "tu negocio"
            base_text = (
                f"Hola! Vi {empresa} y me pareció que tiene mucho potencial. "
                f"Te armé una demo de cómo quedaría tu página web. "
                f"Incluye botón de WhatsApp, mapa de ubicación y todo el info de tu negocio. "
                f"Por $50.000/mes podés tener tu propia página con dominio .com.ar incluido."
            )

        full_message = f"{base_text}\n\n📱 Mirá la demo que te hice: {landing_url}"

        # Añadir link de pago si existe
        if lead["mp_payment_link"]:
            full_message += f"\n\n💳 Pagar acá (MercadoPago): {lead['mp_payment_link']}"

        # ── 3. Enviar WhatsApp ───────────────────────────────────────────────
        telefono = lead["telefono"] or ""
        if not telefono:
            logger.warning(f"[PostProcessor] Lead {lead_id} sin teléfono — no se puede enviar WA")
            _log_activity(conn, lead_id, "nota",
                          "Sin teléfono: landing deployada pero WA no enviado",
                          {"landing_url": landing_url})
            conn.execute(
                "UPDATE leads SET landing_url=?, updated_at=? WHERE id=?",
                [landing_url, datetime.now().isoformat(), lead_id]
            )
            conn.commit()
            return False

        wa_result = send_text(telefono, full_message)
        now_iso = datetime.now().isoformat()

        if "error" in wa_result:
            logger.error(f"[PostProcessor] WA fallido para lead {lead_id}: {wa_result['error']}")
            _log_activity(conn, lead_id, "nota",
                          f"Landing deployada ({landing_url}) pero WA falló: {wa_result['error']}",
                          {"landing_url": landing_url, "wa_error": wa_result["error"]})
            conn.execute(
                "UPDATE leads SET landing_url=?, whatsapp_sent_status='fallido', updated_at=? WHERE id=?",
                [landing_url, now_iso, lead_id]
            )
            conn.commit()
            return False

        # ── 4. Todo OK: actualizar DB ────────────────────────────────────────
        wa_msg_id = wa_result.get("key", {}).get("id") or wa_result.get("messageId", "")
        _log_wa_conversation(conn, lead_id, "outbound", full_message, wa_msg_id)

        conn.execute("""
            UPDATE leads SET
                landing_url          = ?,
                status               = 'whatsapp_enviado',
                whatsapp_sent_at     = ?,
                whatsapp_sent_status = 'enviado',
                whatsapp_conv_status = 'activo',
                updated_at           = ?
            WHERE id = ?
        """, [landing_url, now_iso, now_iso, lead_id])

        _log_activity(conn, lead_id, "nota",
                      f"Landing deployada y WA enviado. Demo: {landing_url}",
                      {"landing_url": landing_url, "wa_msg_id": wa_msg_id})
        conn.commit()

        logger.info(f"[PostProcessor] Lead {lead_id} procesado OK → whatsapp_enviado")
        return True

    except Exception as e:
        logger.error(f"[PostProcessor] Excepción procesando lead {lead_id}: {e}", exc_info=True)
        try:
            _log_activity(conn, lead_id, "nota",
                          f"Error en post-procesamiento: {e}",
                          {"error": str(e)})
            conn.commit()
        except Exception:
            pass
        return False
    finally:
        conn.close()
