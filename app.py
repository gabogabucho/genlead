"""
LeadGen Dashboard — Gabriel Urrutia
Backend Flask · deployable en Railway
"""

import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, g, render_template, jsonify, request

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
        with open(schema_path) as f:
            db.executescript(f.read())
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
        "email_asunto", "email_html", "email_brevo_id",
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
    data    = request.json or {}
    tipo    = data.get("type", "")
    payment_id = data.get("data", {}).get("id", "")

    if tipo != "payment" or not payment_id:
        return jsonify({"ok": True})   # Ignorar otros tipos de notificación

    db = get_db()

    # Buscar lead por mp_preference_id o mp_payment_id
    # En producción: llamar a la API de MP con el payment_id para verificar y obtener metadata
    lead = db.execute(
        "SELECT * FROM leads WHERE mp_payment_id=? OR mp_preference_id=?",
        [str(payment_id), str(payment_id)]
    ).fetchone()

    if not lead:
        # Si no se encuentra, guardamos el pago para revisión manual
        app.logger.warning(f"MP Webhook: pago {payment_id} sin lead asociado")
        return jsonify({"ok": True})

    lead_id = lead["id"]

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
    return jsonify({"ok": True})


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

    # TODO (Fase B): Llamar a CF API para configurar zona + DNS + deploy landing
    # cf_worker.configure_domain(lead_id, dominio)

    return jsonify({
        "ok": True,
        "dominio": dominio,
        "proximo_paso": "Configuración Cloudflare pendiente (Fase B)",
    })


# ──────────────────────────────────────────────
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("DEBUG","false") == "true")
