import os
import sqlite3
import json
from crewai.tools import tool

# Importar scripts existentes
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.site_analyzer import analizar_sitio
from utils.mercadopago_integration import generar_link_pago, generar_suscripcion
from utils.email_sender import send_email
import anthropic

from scrapers.email_generator import generar_email as email_gen_viejo
from scrapers.whatsapp_generator import generar_whatsapp as whatsapp_gen

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "leadgen.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

@tool("Fetch Pending Leads Tool")
def fetch_pending_leads_tool(limit: int = 5) -> str:
    """
    Busca leads en la base de datos que estén en estado 'nuevo'.
    Útil para saber qué empresas analizar y prospectar.
    Retorna un JSON con la lista de leads.
    """
    conn = get_db_connection()
    lead_id = os.environ.get("LEAD_ID", "").strip()
    if lead_id:
        leads = conn.execute(
            "SELECT id, empresa, ciudad, rubro_slug, url, email, telefono FROM leads WHERE id = ?",
            [lead_id]
        ).fetchall()
    else:
        leads = conn.execute(
            "SELECT id, empresa, ciudad, rubro_slug, url, email, telefono FROM leads WHERE status='nuevo' LIMIT ?",
            [limit]
        ).fetchall()
    conn.close()
    return json.dumps([dict(l) for l in leads])

@tool("Site Analyzer Tool")
def site_analyzer_tool(empresa: str, url: str, ciudad: str) -> str:
    """
    Analiza la página web del lead para detectar si tiene Google Ads, Meta Ads,
    Analytics, si es responsive, si tiene WhatsApp, etc.
    Devuelve un JSON con 'score_calidad' y 'dolores'.
    """
    if not url or url.lower() == "none" or url == "":
        return json.dumps({"error": "No hay URL para analizar", "score_calidad": 0, "dolores": "No tiene sitio web."})
    
    analysis = analizar_sitio(empresa, url, ciudad)
    return json.dumps(analysis)

@tool("Generate Payment Link Tool")
def generate_payment_link_tool(lead_id: int, tipo_servicio: str) -> str:
    """
    Genera un link de MercadoPago. 
    Usa tipo_servicio: 'simple' (USD/ARS equivalente para web básica, ej: $150.000) 
    o 'pro' (setup de ads + landing, ej: $300.000).
    Retorna el init_point (link de pago).
    """
    if tipo_servicio == "simple":
        # Suscripción mensual recurrente $50.000/mes (modelo del Servicio 1)
        conn = get_db_connection()
        lead = conn.execute("SELECT empresa FROM leads WHERE id=?", [lead_id]).fetchone()
        conn.close()
        empresa = lead["empresa"] if lead else f"Lead {lead_id}"
        resultado = generar_suscripcion(lead_id, empresa, monto=50000.0)
        return resultado.get("init_point") or resultado.get("sandbox_init_point") or ""
    else:
        monto = 300000.0
        titulo = "Setup Completo: Google Ads + Meta Ads + Landing Page"
        desc = "Configuración inicial de campañas de performance y rediseño web enfocado en conversiones."
        resultado = generar_link_pago(lead_id, titulo, monto, desc)
        return resultado.get("init_point", "")

@tool("Update Lead Database Tool")
def update_lead_db_tool(lead_id: int, updates_json: str) -> str:
    """
    Actualiza el registro del lead en la base de datos SQLite.
    updates_json debe ser un string JSON con las llaves a actualizar, validas:
    'status', 'tipo_servicio', 'landing_html', 'email_html', 'email_asunto', 'mp_payment_link'
    """
    conn = get_db_connection()
    try:
        updates = json.loads(updates_json)
        allowed = ["status", "tipo_servicio", "landing_html", "email_html", "email_asunto", "mp_payment_link", "score_calidad", "dolores", "google_ads_detectado", "whatsapp_text"]
        
        valid_updates = {k: v for k, v in updates.items() if k in allowed}
        if not valid_updates:
            return "Error: No valid fields provided."
            
        set_clause = ", ".join(f"{k} = ?" for k in valid_updates)
        values = list(valid_updates.values()) + [lead_id]
        
        conn.execute(f"UPDATE leads SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return f"Lead {lead_id} updated successfully."
    except Exception as e:
        return f"Error updating DB: {e}"
    finally:
        conn.close()

@tool("Generate Pitch Email Tool")
def generate_pitch_email_tool(analysis_json: str) -> str:
    """
    Utiliza el generador de emails de Gabriel (Claude Opus) para armar el pitch de ventas
    altamente personalizado basado en el análisis del sitio.
    analysis_json debe ser el dict devuelto por Site Analyzer Tool.
    Retorna un JSON con 'email_asunto' y 'email_html'.
    """
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    try:
        data = json.loads(analysis_json)
        resultado = email_gen_viejo(data, client)
        return json.dumps({
            "email_asunto": resultado.get("email_asunto", ""),
            "email_html": resultado.get("email_html", "")
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool("Generate WhatsApp Pitch Tool")
def generate_whatsapp_pitch_tool(analysis_json: str) -> str:
    """
    Genera un mensaje corto de WhatsApp para servicios basicos.
    Enfocado en beneficio y posicionamiento, sin precios.
    Retorna un JSON con 'whatsapp_text'.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    try:
        data = json.loads(analysis_json)
        resultado = whatsapp_gen(data, client)
        return json.dumps({
            "whatsapp_text": resultado.get("whatsapp_text", "")
        })
    except Exception as e:
        return json.dumps({"error": str(e)})
