-- LeadGen Dashboard — Gabriel Urrutia
-- Schema SQLite v2 (CRM + MercadoPago + Dominio)

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────
--  RUBROS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rubros (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT    UNIQUE NOT NULL,
    nombre      TEXT    NOT NULL,
    activo      INTEGER DEFAULT 1,
    created_at  TEXT    DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────
--  LEADS
--
--  Status flow:
--  nuevo → analizado → [Gabo elige tipo] → landing_lista
--       → email_listo → enviado → pagado → en_proceso → cerrado
--                                       ↘ descartado
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leads (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    rubro_slug              TEXT    NOT NULL REFERENCES rubros(slug),

    -- Info básica
    empresa                 TEXT    NOT NULL,
    ciudad                  TEXT,
    url                     TEXT,
    email                   TEXT,
    telefono                TEXT,
    google_maps_url         TEXT,

    -- Análisis del sitio
    google_ads_detectado    INTEGER DEFAULT 0,
    meta_ads_detectado      INTEGER DEFAULT 0,
    google_analytics        INTEGER DEFAULT 0,
    gtm                     INTEGER DEFAULT 0,
    ssl                     INTEGER DEFAULT 0,
    mobile_viewport         INTEGER DEFAULT 0,
    tiene_whatsapp          INTEGER DEFAULT 0,
    tiene_formulario        INTEGER DEFAULT 0,
    tiene_telefono_visible  INTEGER DEFAULT 0,
    tiempo_respuesta        REAL,
    score_calidad           INTEGER DEFAULT 0,
    dolores                 TEXT,
    titulo_pagina           TEXT,
    meta_description        TEXT,

    -- Tipo de servicio (sugerido por IA, confirmado por Gabo)
    -- 'simple'  → pago único + dominio
    -- 'pro'     → mensual (Ads + landing)
    -- 'ninguno' → no califica
    tipo_servicio           TEXT    DEFAULT 'ninguno',
    tipo_confirmado         INTEGER DEFAULT 0,   -- 0=sugerido, 1=confirmado por Gabo

    -- Landing generada
    landing_url             TEXT,   -- URL en Cloudflare (borrador)
    landing_url_live        TEXT,   -- URL final con dominio propio
    landing_html            TEXT,
    landing_tipo            TEXT,
    landing_deploy_id       TEXT,

    -- Email generado
    email_asunto            TEXT,
    email_html              TEXT,
    email_brevo_id          TEXT,
    whatsapp_text           TEXT,

    -- ── MercadoPago ──────────────────────
    mp_preference_id        TEXT,   -- ID de preferencia MP
    mp_payment_link         TEXT,   -- Link de pago para incluir en landing/email
    mp_payment_status       TEXT    DEFAULT 'pendiente',
    -- pendiente | aprobado | rechazado | cancelado
    mp_payment_id           TEXT,   -- ID del pago confirmado por MP
    mp_monto                REAL,   -- Monto cobrado (puede variar: simple vs pro)
    mp_fecha_pago           TEXT,

    -- ── Dominio ──────────────────────────
    dominio_sugerido        TEXT,   -- ej: "elrulo-barberia.com.ar"
    dominio_comprado        TEXT,   -- el que realmente se compró (puede diferir)
    dominio_status          TEXT    DEFAULT 'sin_asignar',
    -- sin_asignar | pendiente_compra | comprado | cf_configurado | live
    dominio_cf_zone_id      TEXT,   -- Cloudflare Zone ID (post-config)
    dominio_fecha_vencimiento TEXT, -- Para renovación anual

    -- ── CRM ──────────────────────────────
    deal_value              REAL    DEFAULT 0,   -- Valor del deal (USD)
    follow_up_date          TEXT,   -- Fecha próximo seguimiento
    follow_up_done          INTEGER DEFAULT 0,

    -- Estado global del lead
    status                  TEXT    DEFAULT 'nuevo',
    notas                   TEXT,

    -- ── WhatsApp Outbound ────────────────────
    whatsapp_sent_at        TEXT,   -- datetime del primer envío WA
    whatsapp_sent_status    TEXT    DEFAULT 'pendiente',
    -- pendiente | enviado | fallido
    whatsapp_follow_up_3d   INTEGER DEFAULT 0,  -- 1 = follow-up día 3 enviado
    whatsapp_follow_up_7d   INTEGER DEFAULT 0,  -- 1 = follow-up día 7 enviado

    -- ── WhatsApp Inbound ─────────────────────
    whatsapp_last_msg_at    TEXT,   -- último mensaje recibido
    whatsapp_conv_status    TEXT    DEFAULT 'sin_contacto',
    -- sin_contacto | activo | esperando_pago | cerrado | descartado | sin_respuesta

    created_at              TEXT    DEFAULT (datetime('now')),
    updated_at              TEXT    DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────
--  ACTIVITY LOG (CRM Timeline)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id     INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    tipo        TEXT    NOT NULL,
    -- nota | email_enviado | llamada | reunion | pago_recibido
    -- dominio_comprado | cf_configurado | seguimiento | cierre
    descripcion TEXT,
    metadata    TEXT,   -- JSON con datos extra (monto, dominio, etc.)
    created_at  TEXT    DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────
--  PIPELINE RUNS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    rubro_slug          TEXT    NOT NULL,
    status              TEXT    DEFAULT 'running',
    leads_encontrados   INTEGER DEFAULT 0,
    leads_analizados    INTEGER DEFAULT 0,
    landings_creadas    INTEGER DEFAULT 0,
    emails_generados    INTEGER DEFAULT 0,
    emails_enviados     INTEGER DEFAULT 0,
    log                 TEXT,
    started_at          TEXT    DEFAULT (datetime('now')),
    completed_at        TEXT
);

-- ─────────────────────────────────────────
--  WHATSAPP CONVERSATIONS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS whatsapp_conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id     INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    direction   TEXT    NOT NULL,   -- 'outbound' | 'inbound'
    message     TEXT    NOT NULL,
    wa_msg_id   TEXT,               -- ID del mensaje en Evolution API
    created_at  TEXT    DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────
--  ÍNDICES
-- ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_leads_rubro        ON leads(rubro_slug);
CREATE INDEX IF NOT EXISTS idx_leads_status       ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_tipo         ON leads(tipo_servicio);
CREATE INDEX IF NOT EXISTS idx_leads_follow_up    ON leads(follow_up_date);
CREATE INDEX IF NOT EXISTS idx_leads_mp_status    ON leads(mp_payment_status);
CREATE INDEX IF NOT EXISTS idx_leads_telefono     ON leads(telefono);
CREATE INDEX IF NOT EXISTS idx_activities_lead    ON activities(lead_id);
CREATE INDEX IF NOT EXISTS idx_wa_conv_lead       ON whatsapp_conversations(lead_id);
CREATE INDEX IF NOT EXISTS idx_wa_conv_direction  ON whatsapp_conversations(direction);

-- ─────────────────────────────────────────
--  SEED: rubros iniciales
-- ─────────────────────────────────────────
INSERT OR IGNORE INTO rubros (slug, nombre) VALUES
    ('portones_automaticos',  'Portones Automáticos'),
    ('barberias',             'Barberías'),
    ('plomeros',              'Plomería y Gas'),
    ('electricistas',         'Electricistas'),
    ('veterinarias',          'Veterinarias'),
    ('consultorios_medicos',  'Consultorios Médicos'),
    ('estudios_juridicos',    'Estudios Jurídicos'),
    ('peluquerias',           'Peluquerías'),
    ('esteticas_spa',         'Estéticas y Spa'),
    ('plantas_decorativas',   'Plantas Decorativas'),
    ('tiendas_autor',         'Tiendas de Autor');
