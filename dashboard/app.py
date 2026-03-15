"""
LeadGen Dashboard — Gabriel Urrutia
Backend Flask · deployable en Railway
"""

import os
import json
import sqlite3
import threading
import sys
from datetime import datetime
from flask import Flask, g, render_template, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"), override=True)

from utils.pipeline_runner import run_pipeline
from utils.agent_runner import run_agent_for_lead

app = Flask(__name__)
DATABASE  = os.environ.get("DATABASE_PATH", "leadgen.db")
API_SECRET = os.environ.get("API_SECRET", "dev-secret-change-me")
MP_SECRET  = os.environ.get("MP_WEBHOOK_SECRET", "")   # para validar webhooks de MP


# ──────────────────────────────────────────────
#  DB helpers
# ──────────────────────────────────────────────

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys = ON")
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, encoding="utf-8") as f:
            db.executescript(f.read())

        # Migrations: agregar columnas nuevas sin romper datos existentes
        cols = {r["name"] for r in db.execute("PRAGMA table_info(leads)").fetchall()}
        migrations = [
            ("whatsapp_text",           "TEXT"),
            ("whatsapp_sent_at",        "TEXT"),
            ("whatsapp_sent_status",    "TEXT DEFAULT 'pendiente'"),
            ("whatsapp_follow_up_3d",   "INTEGER DEFAULT 0"),
            ("whatsapp_follow_up_7d",   "INTEGER DEFAULT 0"),
            ("whatsapp_last_msg_at",    "TEXT"),
            ("whatsapp_conv_status",    "TEXT DEFAULT 'sin_contacto'"),
        ]
        for col_name, col_def in migrations:
            if col_name not in cols:
                db.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_def}")

        db.commit()


def require_secret(req):
    secret = req.headers.get("X-API-Secret", "")
    if secret != API_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    return None


def log_activity(db, lead_id, tipo, descripcion, metadata=None):
    """Registra una actividad en el timeline del lead."""
    db.execute(
        "INSERT INTO activities (lead_id, tipo, descripcion, metadata) VALUES (?,?,?,?)",
        [lead_id, tipo, descripcion, json.dumps(metadata) if metadata else None],
    )


# ──────────────────────────────────────────────
#  FRONTEND
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ──────────────────────────────────────────────
#  API: STATS
# ──────────────────────────────────────────────

@app.route("/api/stats")
def stats():
    db = get_db()

    totales = dict(db.execute("""
        SELECT
            COUNT(*)                                                              AS total,
            COALESCE(SUM(CASE WHEN status='cerrado'          THEN 1 END), 0)     AS cerrados,
            COALESCE(SUM(CASE WHEN status='enviado'          THEN 1 END), 0)     AS enviados,
            COALESCE(SUM(CASE WHEN status='pagado'           THEN 1 END), 0)     AS pagados,
            COALESCE(SUM(CASE WHEN landing_url IS NOT NULL
                         AND  landing_url != ''              THEN 1 END), 0)     AS landings,
            COALESCE(SUM(CASE WHEN google_ads_detectado=1    THEN 1 END), 0)     AS con_ads,
            COALESCE(SUM(CASE WHEN tipo_servicio='pro'       THEN 1 END), 0)     AS tipo_pro,
            COALESCE(SUM(CASE WHEN tipo_servicio='simple'    THEN 1 END), 0)     AS tipo_simple,
            COALESCE(SUM(deal_value), 0)                                         AS revenue_total,
            COALESCE(SUM(CASE WHEN follow_up_date IS NOT NULL
                         AND  follow_up_date <= date('now')
                         AND  follow_up_done = 0             THEN 1 END), 0)     AS follow_ups_vencidos
        FROM leads
    """).fetchone())

    por_status = [dict(r) for r in db.execute("""
        SELECT status, COUNT(*) AS count FROM leads GROUP BY status
    """).fetchall()]

    por_rubro = [dict(r) for r in db.execute("""
        SELECT
            r.slug, r.nombre,
            COUNT(l.id)                                                AS total,
            COALESCE(SUM(CASE WHEN l.status='cerrado'  THEN 1 END),0) AS cerrados,
            COALESCE(SUM(CASE WHEN l.status='enviado'  THEN 1 END),0) AS enviados,
            COALESCE(SUM(CASE WHEN l.status='pagado'   THEN 1 END),0) AS pagados,
            COALESCE(SUM(CASE WHEN l.landing_url IS NOT NULL
                         AND  l.landing_url != ''      THEN 1 END),0) AS landings,
            COALESCE(SUM(l.deal_value), 0)                            AS revenue
        FROM rubros r
        LEFT JOIN leads l ON l.rubro_slug = r.slug
        GROUP BY r.slug
        ORDER BY total DESC
    """).fetchall()]

    # Follow-ups vencidos (para badge de alerta)
    follow_ups = [dict(r) for r in db.execute("""
        SELECT id, empresa, ciudad, follow_up_date
        FROM leads
        WHERE follow_up_date IS NOT NULL
          AND follow_up_date <= date('now')
          AND follow_up_done = 0
        ORDER BY follow_up_date ASC
        LIMIT 10
    """).fetchall()]

    return jsonify({
        "totales":     totales,
        "por_status":  por_status,
        "por_rubro":   por_rubro,
        "follow_ups":  follow_ups,
    })


# ──────────────────────────────────────────────
#  API: RUBROS
# ──────────────────────────────────────────────

@app.route("/api/rubros")
def get_rubros():
    db = get_db()
    return jsonify([dict(r) for r in db.execute(
        "SELECT * FROM rubros ORDER BY nombre"
    ).fetchall()])


@app.route("/api/rubros", methods=["POST"])
def create_rubro():
    err = require_secret(request)
    if err: return err
    data = request.json
    db = get_db()
    db.execute("INSERT OR IGNORE INTO rubros (slug, nombre) VALUES (?, ?)",
               [data["slug"], data["nombre"]])
    db.commit()
    return jsonify({"ok": True}), 201


# ──────────────────────────────────────────────
#  API: LEADS
# ──────────────────────────────────────────────

@app.route("/api/leads")
def get_leads():
    db     = get_db()
    rubro  = request.args.get("rubro", "")
    status = request.args.get("status", "")
    tipo   = request.args.get("tipo", "")
    q      = request.args.get("q", "")
    follow = request.args.get("follow_up_vencido", "")
    page   = int(request.args.get("page", 1))
    per    = 50

    query  = "SELECT * FROM leads WHERE 1=1"
    params = []

    if rubro:  query += " AND rubro_slug = ?";      params.append(rubro)
    if status: query += " AND status = ?";           params.append(status)
    if tipo:   query += " AND tipo_servicio = ?";    params.append(tipo)
    if q:
        query += " AND (empresa LIKE ? OR ciudad LIKE ? OR email LIKE ?)"
        params += [f"%{q}%"] * 3
    if follow:
        query += " AND follow_up_date <= date('now') AND follow_up_done = 0"

    total = db.execute(query.replace("SELECT *", "SELECT COUNT(*)"), params).fetchone()[0]
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params += [per, (page - 1) * per]

    leads = [dict(r) for r in db.execute(query, params).fetchall()]
    return jsonify({"leads": leads, "total": total, "page": page, "per": per})


@app.route("/api/leads/<int:lead_id>")
def get_lead(lead_id):
    db   = get_db()
    lead = db.execute("SELECT * FROM leads WHERE id = ?", [lead_id]).fetchone()
    if not lead: return jsonify({"error": "Not found"}), 404
    return jsonify(dict(lead))


@app.route("/api/leads", methods=["POST"])
def create_lead():
    err = require_secret(request)
    if err: return err
    data = request.json
    db   = get_db()

    db.execute("INSERT OR IGNORE INTO rubros (slug, nombre) VALUES (?, ?)",
               [data["rubro_slug"], data.get("rubro_nombre", data["rubro_slug"])])

    cur = db.execute("""
        INSERT INTO leads (
            rubro_slug, empresa, ciudad, url, email, telefono, google_maps_url,
            google_ads_detectado, meta_ads_detectado, google_analytics, gtm,
            ssl, mobile_viewport, tiene_whatsapp, tiene_formulario,
            tiene_telefono_visible, tiempo_respuesta,
            score_calidad, dolores, titulo_pagina, meta_description,
            tipo_servicio, dominio_sugerido, deal_value, status, notas
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, [
        data["rubro_slug"], data["empresa"],
        data.get("ciudad",""), data.get("url",""),
        data.get("email",""), data.get("telefono",""), data.get("google_maps_url",""),
        1 if data.get("google_ads_detectado") else 0,
        1 if data.get("meta_ads_detectado")   else 0,
        1 if data.get("google_analytics")     else 0,
        1 if data.get("gtm")                  else 0,
        1 if data.get("ssl")                  else 0,
        1 if data.get("mobile_viewport")      else 0,
        1 if data.get("tiene_whatsapp")       else 0,
        1 if data.get("tiene_formulario")     else 0,
        1 if data.get("tiene_telefono_visible") else 0,
        data.get("tiempo_respuesta", 0),
        data.get("score_calidad", 0),
        data.get("dolores",""), data.get("titulo_pagina",""), data.get("meta_description",""),
        data.get("tipo_servicio","ninguno"),
        data.get("dominio_sugerido",""),
        data.get("deal_value", 0),
        data.get("status","nuevo"), data.get("notas",""),
    ])
    lead_id = cur.lastrowid
    log_activity(db, lead_id, "nota", "Lead creado por pipeline")
    db.commit()
    return jsonify({"id": lead_id}), 201


@app.route("/api/leads/<int:lead_id>", methods=["PATCH"])
def update_lead(lead_id):
    data = request.json
    db   = get_db()

    allowed = [
        "status", "email", "telefono", "notas", "tipo_servicio", "tipo_confirmado",
        "deal_value", "follow_up_date", "follow_up_done",
        "landing_url", "landing_url_live", "landing_html", "landing_tipo", "landing_deploy_id",
        "email_asunto", "email_html", "email_brevo_id", "whatsapp_text",
        "mp_preference_id", "mp_payment_link", "mp_payment_status",
        "dominio_sugerido", "dominio_comprado", "dominio_status", "dominio_cf_zone_id",
        "dominio_fecha_vencimiento",
    ]
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "No valid fields"}), 400

    # Auto-log de cambios importantes
    old = db.execute("SELECT status, tipo_servicio FROM leads WHERE id=?", [lead_id]).fetchone()
    if old:
        if "status" in updates and updates["status"] != old["status"]:
            log_activity(db, lead_id, "nota",
                         f"Estado cambiado: {old['status']} → {updates['status']}")
        if "tipo_servicio" in updates and updates["tipo_servicio"] != old["tipo_servicio"]:
            log_activity(db, lead_id, "nota",
                         f"Tipo de servicio: {updates['tipo_servicio']}")

    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    db.execute(f"UPDATE leads SET {set_clause} WHERE id = ?",
               list(updates.values()) + [lead_id])
    db.commit()
    return jsonify({"ok": True})


# ──────────────────────────────────────────────
#  API: RUN AGENT
# ----------------------------------------------------------------------

@app.route("/api/leads/<int:lead_id>/run_agent", methods=["POST"])
def run_agent(lead_id):
    db = get_db()
    lead = db.execute("SELECT id, status, empresa FROM leads WHERE id=?", [lead_id]).fetchone()
    if not lead:
        return jsonify({"error": "Not found"}), 404

    if lead["status"] in ("en_proceso", "cerrado", "descartado"):
        return jsonify({"error": "Lead no elegible"}), 400

    old_status = lead["status"]
    db.execute(
        "UPDATE leads SET status=?, updated_at=? WHERE id=?",
        ["en_proceso", datetime.now().isoformat(), lead_id],
    )
    log_activity(db, lead_id, "nota", "Agente iniciado desde dashboard")
    db.commit()

    def _runner(prev_status: str):
        try:
            run_agent_for_lead(lead_id)
        except Exception as e:
            conn = sqlite3.connect(DATABASE)
            conn.row_factory = sqlite3.Row
            conn.execute(
                "UPDATE leads SET status=?, updated_at=? WHERE id=?",
                [prev_status, datetime.now().isoformat(), lead_id],
            )
            conn.execute(
                "INSERT INTO activities (lead_id, tipo, descripcion) VALUES (?,?,?)",
                [lead_id, "nota", f"Error ejecutando agente: {e}"],
            )
            conn.commit()
            conn.close()

    threading.Thread(target=_runner, args=(old_status,), daemon=True).start()
    return jsonify({"ok": True})

#  API: ACTIVITIES (CRM Timeline)
# ──────────────────────────────────────────────

@app.route("/api/leads/<int:lead_id>/activities")
def get_activities(lead_id):
    db  = get_db()
    acts = [dict(r) for r in db.execute(
        "SELECT * FROM activities WHERE lead_id=? ORDER BY created_at DESC",
        [lead_id]
    ).fetchall()]
    return jsonify(acts)


@app.route("/api/leads/<int:lead_id>/activities", methods=["POST"])
def add_activity(lead_id):
    data = request.json
    db   = get_db()
    db.execute(
        "INSERT INTO activities (lead_id, tipo, descripcion, metadata) VALUES (?,?,?,?)",
        [lead_id, data.get("tipo","nota"), data.get("descripcion",""),
         json.dumps(data.get("metadata")) if data.get("metadata") else None],
    )
    db.commit()
    return jsonify({"ok": True}), 201


# ──────────────────────────────────────────────
#  API: MERCADOPAGO WEBHOOK
# ──────────────────────────────────────────────

@app.route("/api/mp/webhook", methods=["POST"])
def mp_webhook():
    """
    Recibe notificaciones de MercadoPago cuando se confirma un pago.
    MP envía: { "type": "payment", "data": { "id": "123456" } }
    """
    import urllib.request as _urllib_request
    data    = request.json or {}
    tipo    = data.get("type", "")
    payment_id = data.get("data", {}).get("id", "")

    if tipo != "payment" or not payment_id:
        return jsonify({"ok": True})   # Ignorar otros tipos de notificación

    # Consultar la API de MP para obtener external_reference (= lead_id)
    mp_token = os.environ.get("MP_ACCESS_TOKEN", "")
    lead_id = None
    try:
        req = _urllib_request.Request(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {mp_token}"}
        )
        with _urllib_request.urlopen(req, timeout=10) as resp:
            payment_data = json.loads(resp.read().decode())
        external_reference = payment_data.get("external_reference", "")
        if external_reference:
            lead_id = int(external_reference)
    except Exception as e:
        app.logger.error(f"MP Webhook: error consultando API de MP para pago {payment_id}: {e}")
        return jsonify({"ok": True})

    if not lead_id:
        app.logger.warning(f"MP Webhook: pago {payment_id} sin external_reference")
        return jsonify({"ok": True})

    db = get_db()
    lead = db.execute("SELECT * FROM leads WHERE id=?", [lead_id]).fetchone()

    if not lead:
        app.logger.warning(f"MP Webhook: lead {lead_id} no encontrado para pago {payment_id}")
        return jsonify({"ok": True})

    # Actualizar estado del lead
    db.execute("""
        UPDATE leads SET
            mp_payment_id     = ?,
            mp_payment_status = 'aprobado',
            mp_fecha_pago     = ?,
            status            = 'pagado',
            updated_at        = ?
        WHERE id = ?
    """, [str(payment_id), datetime.now().isoformat(), datetime.now().isoformat(), lead_id])

    log_activity(db, lead_id, "pago_recibido",
                 f"Pago confirmado por MercadoPago (ID: {payment_id})",
                 {"payment_id": payment_id})
    db.commit()

    app.logger.info(f"Pago confirmado para lead {lead_id} ({lead['empresa']})")

    # Notificar a Gabriel por email para que compre el dominio en NIC.ar
    try:
        from utils.email_sender import send_email
        gabriel_email = os.environ.get("GABRIEL_EMAIL", os.environ.get("VENDEDOR_EMAIL", ""))
        if gabriel_email:
            empresa       = lead["empresa"] or f"Lead {lead_id}"
            ciudad        = lead["ciudad"] or ""
            dominio_sug   = lead["dominio_sugerido"] or "—"
            landing_url   = lead["landing_url"] or ""
            email_html = f"""
<h2>💳 Pago recibido: {empresa}</h2>
<p><strong>Ciudad:</strong> {ciudad}<br>
<strong>Dominio sugerido:</strong> {dominio_sug}<br>
<strong>Pago ID:</strong> {payment_id}</p>
{"<p><strong>Demo actual:</strong> <a href='" + landing_url + "'>" + landing_url + "</a></p>" if landing_url else ""}
<hr>
<p><strong>Próximo paso:</strong> Comprar el dominio en NIC.ar y confirmarlo en el dashboard.</p>
<p><a href="https://nic.ar" style="background:#1e293b;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;">
   Ir a NIC.ar →
</a></p>
<p style="color:#64748b;font-size:12px;margin-top:20px;">
  LeadGen · Bot automático
</p>"""
            send_email(
                to_email=gabriel_email,
                to_name="Gabriel Urrutia",
                subject=f"💳 PAGO RECIBIDO: {empresa} ({ciudad})",
                html_content=email_html,
            )
    except Exception as e:
        app.logger.error(f"Error enviando notificación de pago por email: {e}")

    return jsonify({"ok": True})


# ──────────────────────────────────────────────
#  API: WHATSAPP WEBHOOK (Evolution API → Flask)
# ──────────────────────────────────────────────

@app.route("/api/whatsapp/webhook", methods=["POST"])
def whatsapp_webhook():
    """
    Recibe mensajes entrantes de Evolution API.
    Payload: {"event": "messages.upsert", "data": {"key": {"remoteJid": "549...", "fromMe": false}, "message": {"conversation": "Hola"}}}
    """
    from utils.whatsapp_sender import send_text, _normalize_phone_ar
    from utils.whatsapp_bot import procesar_mensaje

    # Validar Client-Token de Evolution API
    api_key = os.environ.get("EVOLUTION_API_KEY", "")
    incoming_key = request.headers.get("apikey", "") or request.headers.get("Authorization", "")
    if api_key and incoming_key != api_key:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    payload = request.json or {}

    # Evolution API envía el evento en distintos niveles según la versión
    data = payload.get("data", {})
    key  = data.get("key", {})

    # Ignorar mensajes enviados por nosotros
    if key.get("fromMe"):
        return jsonify({"ok": True})

    # Extraer número y texto
    remote_jid = key.get("remoteJid", "")        # ej: "5491145678901@s.whatsapp.net"
    phone_raw  = remote_jid.split("@")[0]         # "5491145678901"
    phone_norm = _normalize_phone_ar(phone_raw)

    msg_obj   = data.get("message", {})
    text_body = (
        msg_obj.get("conversation")
        or msg_obj.get("extendedTextMessage", {}).get("text")
        or ""
    )

    if not text_body or not phone_norm:
        return jsonify({"ok": True})

    wa_msg_id = key.get("id", "")

    db = get_db()

    # Buscar lead por teléfono (normalizado)
    lead = db.execute(
        "SELECT * FROM leads WHERE replace(replace(replace(replace(replace(telefono,' ',''),'-',''),'(',''),')',''),'+','') LIKE ?",
        [f"%{phone_norm[-10:]}%"]   # comparar los últimos 10 dígitos
    ).fetchone()

    if not lead:
        app.logger.info(f"WA Webhook: mensaje de {phone_norm} sin lead asociado, ignorando")
        return jsonify({"ok": True})

    lead_id = lead["id"]
    now_iso = datetime.now().isoformat()

    # Loguear mensaje entrante
    db.execute(
        "INSERT INTO whatsapp_conversations (lead_id, direction, message, wa_msg_id) VALUES (?,?,?,?)",
        [lead_id, "inbound", text_body, wa_msg_id],
    )
    db.execute(
        "UPDATE leads SET whatsapp_last_msg_at=?, whatsapp_conv_status='activo', updated_at=? WHERE id=?",
        [now_iso, now_iso, lead_id],
    )
    db.commit()

    # Obtener historial reciente para contexto del bot
    historial = [dict(r) for r in db.execute(
        "SELECT direction, message FROM whatsapp_conversations WHERE lead_id=? ORDER BY created_at DESC LIMIT 10",
        [lead_id]
    ).fetchall()]
    historial.reverse()

    # Generar respuesta del bot
    respuesta = procesar_mensaje(dict(lead), text_body, historial)
    if not respuesta:
        return jsonify({"ok": True})

    # Enviar respuesta
    wa_result = send_text(phone_norm, respuesta)
    sent_msg_id = wa_result.get("key", {}).get("id") or ""

    db.execute(
        "INSERT INTO whatsapp_conversations (lead_id, direction, message, wa_msg_id) VALUES (?,?,?,?)",
        [lead_id, "outbound", respuesta, sent_msg_id],
    )

    # Si el lead dice que no le interesa, marcarlo
    texto_lower = text_body.lower()
    if any(kw in texto_lower for kw in ["no gracias", "no me interesa", "no quiero", "basta", "stop"]):
        db.execute(
            "UPDATE leads SET whatsapp_conv_status='descartado', updated_at=? WHERE id=?",
            [now_iso, lead_id]
        )

    db.commit()
    return jsonify({"ok": True})


@app.route("/api/leads/<int:lead_id>/whatsapp_conversations", methods=["GET"])
def get_whatsapp_conversations(lead_id):
    db = get_db()
    convs = [dict(r) for r in db.execute(
        "SELECT * FROM whatsapp_conversations WHERE lead_id=? ORDER BY created_at ASC",
        [lead_id]
    ).fetchall()]
    return jsonify(convs)


@app.route("/api/leads/<int:lead_id>/send_whatsapp", methods=["POST"])
def send_whatsapp_manual(lead_id):
    """Permite a Gabriel enviar un mensaje WA manual desde el dashboard."""
    from utils.whatsapp_sender import send_text

    data    = request.json or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Falta el campo 'message'"}), 400

    db   = get_db()
    lead = db.execute("SELECT * FROM leads WHERE id=?", [lead_id]).fetchone()
    if not lead:
        return jsonify({"error": "Lead no encontrado"}), 404

    telefono = lead["telefono"] or ""
    if not telefono:
        return jsonify({"error": "El lead no tiene teléfono"}), 400

    result = send_text(telefono, message)
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"]}), 500

    wa_msg_id = result.get("key", {}).get("id") or ""
    now_iso   = datetime.now().isoformat()
    db.execute(
        "INSERT INTO whatsapp_conversations (lead_id, direction, message, wa_msg_id) VALUES (?,?,?,?)",
        [lead_id, "outbound", message, wa_msg_id],
    )
    db.execute(
        "UPDATE leads SET whatsapp_last_msg_at=?, updated_at=? WHERE id=?",
        [now_iso, now_iso, lead_id]
    )
    log_activity(db, lead_id, "nota", f"WA manual enviado: {message[:80]}...")
    db.commit()

    return jsonify({"ok": True, "wa_msg_id": wa_msg_id})


# ──────────────────────────────────────────────
#  API: DOMINIO — confirmar compra manual
# ──────────────────────────────────────────────

@app.route("/api/leads/<int:lead_id>/dominio", methods=["POST"])
def confirmar_dominio(lead_id):
    """
    Gabo llama a este endpoint después de comprar el dominio en NIC.ar.
    Marca el dominio como comprado y dispara la configuración en Cloudflare.
    """
    data   = request.json
    dominio = data.get("dominio", "").strip().lower()
    if not dominio:
        return jsonify({"error": "Falta el campo 'dominio'"}), 400

    db = get_db()
    db.execute("""
        UPDATE leads SET
            dominio_comprado = ?,
            dominio_status   = 'comprado',
            updated_at       = ?
        WHERE id = ?
    """, [dominio, datetime.now().isoformat(), lead_id])

    log_activity(db, lead_id, "dominio_comprado",
                 f"Dominio comprado manualmente: {dominio}",
                 {"dominio": dominio})
    db.commit()

    # Disparar deploy en Cloudflare Pages
    from utils.cloudflare_deployer import deploy_landing
    lead = db.execute("SELECT landing_html FROM leads WHERE id=?", [lead_id]).fetchone()
    landing_url = None
    if lead and lead["landing_html"]:
        resultado = deploy_landing(lead_id, dominio, lead["landing_html"])
        if resultado.get("ok"):
            landing_url = resultado["url"]
            db.execute(
                "UPDATE leads SET landing_url=?, dominio_status='configurado', updated_at=? WHERE id=?",
                [landing_url, datetime.now().isoformat(), lead_id]
            )
            log_activity(db, lead_id, "nota",
                         f"Landing desplegada en Cloudflare Pages: {landing_url}",
                         {"landing_url": landing_url})
            db.commit()
        else:
            app.logger.error(f"Error CF deploy para lead {lead_id}: {resultado.get('error')}")

    return jsonify({
        "ok": True,
        "dominio": dominio,
        "landing_url": landing_url,
    })


# ──────────────────────────────────────────────
#  API: LANDING PREVIEW
# ──────────────────────────────────────────────

@app.route("/api/leads/<int:lead_id>/landing_preview")
def landing_preview(lead_id):
    db = get_db()
    lead = db.execute("SELECT landing_html FROM leads WHERE id=?", [lead_id]).fetchone()
    if not lead or not lead["landing_html"]:
        return "Sin landing generada", 404
    return lead["landing_html"], 200, {"Content-Type": "text/html; charset=utf-8"}


# ──────────────────────────────────────────────
#  API: PIPELINE START
# ----------------------------------------------------------------------

@app.route("/api/pipeline/start", methods=["POST"])
def start_pipeline():
    data = request.json or {}
    rubro = (data.get("rubro_slug") or data.get("rubro") or "").strip()
    ciudades = data.get("ciudades", "")
    limit = int(data.get("limit", 30))
    tipo_web = data.get("tipo_web", "sin_web")
    if not rubro:
        return jsonify({"error": "Falta rubro"}), 400

    db = get_db()
    cur = db.execute("INSERT INTO pipeline_runs (rubro_slug) VALUES (?)", [rubro])
    run_id = cur.lastrowid
    db.commit()

    def _runner():
        try:
            run_pipeline(
                rubro_slug=rubro,
                ciudades=[c.strip() for c in ciudades.split(",")] if ciudades else None,
                limit=limit,
                run_id=run_id,
                db_path=DATABASE,
                tipo_web=tipo_web,
            )
        except Exception as e:
            conn = sqlite3.connect(DATABASE)
            conn.row_factory = sqlite3.Row
            cur2 = conn.execute("SELECT log FROM pipeline_runs WHERE id=?", [run_id]).fetchone()
            prev = (cur2["log"] or "") if cur2 else ""
            stamp = datetime.now().strftime("%H:%M:%S")
            new_log = (prev + "\n" if prev else "") + f"[{stamp}] Error: {e}"
            conn.execute(
                "UPDATE pipeline_runs SET status='failed', completed_at=?, log=? WHERE id=?",
                [datetime.now().isoformat(), new_log, run_id],
            )
            conn.commit()
            conn.close()

    threading.Thread(target=_runner, daemon=True).start()
    return jsonify({"ok": True, "run_id": run_id}), 201

#  API: PIPELINE RUNS
# ──────────────────────────────────────────────

@app.route("/api/runs", methods=["GET"])
def get_runs():
    db = get_db()
    return jsonify([dict(r) for r in db.execute(
        "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 20"
    ).fetchall()])


@app.route("/api/runs", methods=["POST"])
def create_run():
    err = require_secret(request)
    if err: return err
    data = request.json
    db   = get_db()
    cur  = db.execute("INSERT INTO pipeline_runs (rubro_slug) VALUES (?)", [data["rubro_slug"]])
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/runs/<int:run_id>", methods=["PATCH"])
def update_run(run_id):
    err = require_secret(request)
    if err: return err
    data    = request.json
    db      = get_db()
    allowed = ["status","leads_encontrados","leads_analizados",
               "landings_creadas","emails_generados","emails_enviados","log"]
    updates = {k: v for k, v in data.items() if k in allowed}
    if "status" in updates and updates["status"] in ("completed","failed"):
        updates["completed_at"] = datetime.now().isoformat()
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        db.execute(f"UPDATE pipeline_runs SET {set_clause} WHERE id = ?",
                   list(updates.values()) + [run_id])
        db.commit()
    return jsonify({"ok": True})


# ──────────────────────────────────────────────
#  ENTRYPOINT
# ──────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    # Iniciar scheduler de follow-ups automáticos
    from utils.follow_up_scheduler import setup_scheduler
    setup_scheduler()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("DEBUG","false") == "true")


