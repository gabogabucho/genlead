"""
Follow-up Scheduler — LeadGen Gabriel Urrutia

Envía mensajes de seguimiento automático a los leads que no respondieron.
Corre como APScheduler en background thread dentro del proceso Flask.

Secuencia:
  Día 3: Primer follow-up (recordatorio amigable + link de la demo)
  Día 7: Segundo follow-up (última oportunidad + link de pago)
  Día 8+: Si no hubo respuesta, marca como 'sin_respuesta'
"""

import os
import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "leadgen.db")

# ─────────────────────────────────────────────────────────────────────────────
#  Templates de mensajes (sin LLM, velocidad máxima)
# ─────────────────────────────────────────────────────────────────────────────

def _msg_dia3(empresa: str, landing_url: str) -> str:
    nombre = empresa or "amigo/a"
    demo   = f"\n\n🌐 Demo: {landing_url}" if landing_url else ""
    return (
        f"Hola {nombre}! 👋 Te escribo de nuevo sobre la página web que armé para tu negocio.\n\n"
        f"La demo sigue disponible para que la veas:{demo}\n\n"
        f"Si tenés alguna pregunta o querés hacer algún cambio, avisame. "
        f"Por $50.000/mes tu negocio tiene presencia online profesional. 💪"
    )


def _msg_dia7(empresa: str, landing_url: str, mp_link: str) -> str:
    nombre = empresa or "amigo/a"
    demo   = f"\n🌐 Demo: {landing_url}" if landing_url else ""
    pago   = f"\n💳 Contratar: {mp_link}" if mp_link else ""
    return (
        f"Último mensaje, te lo prometo! 😄\n\n"
        f"La demo de {nombre} sigue disponible:{demo}{pago}\n\n"
        f"Si en algún momento te interesa, acá estoy. "
        f"Mucho éxito con tu negocio! 🙌"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Job principal
# ─────────────────────────────────────────────────────────────────────────────

def _run_followups():
    """
    Revisa los leads y envía follow-ups según los días transcurridos.
    Se ejecuta cada hora via APScheduler.
    """
    from utils.whatsapp_sender import send_text

    now = datetime.now()
    threshold_3d = (now - timedelta(days=3)).isoformat()
    threshold_7d = (now - timedelta(days=7)).isoformat()
    threshold_8d = (now - timedelta(days=8)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        # ── Follow-up día 3 ──────────────────────────────────────────────────
        leads_3d = conn.execute("""
            SELECT id, empresa, telefono, landing_url, mp_payment_link
            FROM leads
            WHERE status = 'whatsapp_enviado'
              AND whatsapp_sent_at IS NOT NULL
              AND whatsapp_sent_at <= ?
              AND whatsapp_follow_up_3d = 0
              AND whatsapp_conv_status NOT IN ('cerrado', 'descartado', 'pagado')
        """, [threshold_3d]).fetchall()

        for lead in leads_3d:
            try:
                mensaje = _msg_dia3(lead["empresa"], lead["landing_url"] or "")
                result  = send_text(lead["telefono"], mensaje)
                wa_id   = result.get("key", {}).get("id") or ""
                now_iso = now.isoformat()

                conn.execute(
                    "INSERT INTO whatsapp_conversations (lead_id, direction, message, wa_msg_id) VALUES (?,?,?,?)",
                    [lead["id"], "outbound", mensaje, wa_id]
                )
                conn.execute(
                    "UPDATE leads SET whatsapp_follow_up_3d=1, updated_at=? WHERE id=?",
                    [now_iso, lead["id"]]
                )
                conn.execute(
                    "INSERT INTO activities (lead_id, tipo, descripcion) VALUES (?,?,?)",
                    [lead["id"], "seguimiento", "Follow-up automático día 3 enviado por WA"]
                )
                conn.commit()
                logger.info(f"[Scheduler] Follow-up día 3 enviado a lead {lead['id']} ({lead['empresa']})")

            except Exception as e:
                logger.error(f"[Scheduler] Error follow-up día 3 lead {lead['id']}: {e}")

        # ── Follow-up día 7 ──────────────────────────────────────────────────
        leads_7d = conn.execute("""
            SELECT id, empresa, telefono, landing_url, mp_payment_link
            FROM leads
            WHERE status = 'whatsapp_enviado'
              AND whatsapp_sent_at IS NOT NULL
              AND whatsapp_sent_at <= ?
              AND whatsapp_follow_up_7d = 0
              AND whatsapp_conv_status NOT IN ('cerrado', 'descartado', 'pagado')
        """, [threshold_7d]).fetchall()

        for lead in leads_7d:
            try:
                mensaje = _msg_dia7(
                    lead["empresa"],
                    lead["landing_url"] or "",
                    lead["mp_payment_link"] or "",
                )
                result  = send_text(lead["telefono"], mensaje)
                wa_id   = result.get("key", {}).get("id") or ""
                now_iso = now.isoformat()

                conn.execute(
                    "INSERT INTO whatsapp_conversations (lead_id, direction, message, wa_msg_id) VALUES (?,?,?,?)",
                    [lead["id"], "outbound", mensaje, wa_id]
                )
                conn.execute(
                    "UPDATE leads SET whatsapp_follow_up_7d=1, updated_at=? WHERE id=?",
                    [now_iso, lead["id"]]
                )
                conn.execute(
                    "INSERT INTO activities (lead_id, tipo, descripcion) VALUES (?,?,?)",
                    [lead["id"], "seguimiento", "Follow-up automático día 7 enviado por WA"]
                )
                conn.commit()
                logger.info(f"[Scheduler] Follow-up día 7 enviado a lead {lead['id']} ({lead['empresa']})")

            except Exception as e:
                logger.error(f"[Scheduler] Error follow-up día 7 lead {lead['id']}: {e}")

        # ── Marcar sin_respuesta (día 8+, sin actividad) ──────────────────────
        conn.execute("""
            UPDATE leads
            SET whatsapp_conv_status = 'sin_respuesta', updated_at = ?
            WHERE status = 'whatsapp_enviado'
              AND whatsapp_sent_at <= ?
              AND whatsapp_follow_up_7d = 1
              AND whatsapp_conv_status = 'activo'
              AND (whatsapp_last_msg_at IS NULL OR whatsapp_last_msg_at <= ?)
        """, [now.isoformat(), threshold_8d, threshold_7d])
        conn.commit()

    except Exception as e:
        logger.error(f"[Scheduler] Error en _run_followups: {e}", exc_info=True)
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Setup APScheduler
# ─────────────────────────────────────────────────────────────────────────────

_scheduler = None


def setup_scheduler():
    """
    Inicia el scheduler de follow-ups. Llama a esto una vez al arrancar Flask.
    Usa APScheduler con BackgroundScheduler (thread daemon).
    """
    global _scheduler
    if _scheduler is not None:
        return  # Ya iniciado

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning(
            "[Scheduler] APScheduler no instalado. "
            "Instalá con: pip install apscheduler  — Los follow-ups no van a correr automáticamente."
        )
        return

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _run_followups,
        trigger="interval",
        hours=1,
        id="followup_job",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info("[Scheduler] Follow-up scheduler iniciado (intervalo: 1 hora)")
