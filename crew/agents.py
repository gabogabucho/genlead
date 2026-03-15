from crewai import Agent, LLM
from crewai.tools import tool
import os

claude_llm = LLM(model="anthropic/claude-3-5-sonnet-20240620", temperature=0.7)

try:
    from .tools import (
        fetch_pending_leads_tool,
        site_analyzer_tool,
        generate_payment_link_tool,
        update_lead_db_tool,
        generate_pitch_email_tool,
        generate_whatsapp_pitch_tool,
    )
except Exception:
    from tools import (
        fetch_pending_leads_tool,
        site_analyzer_tool,
        generate_payment_link_tool,
        update_lead_db_tool,
        generate_pitch_email_tool,
    )

from utils.email_sender import send_email

@tool("Send Direct Email Tool")
def send_email_wrapper_tool_if_needed(to_email: str, subject: str, html: str) -> str:
    """Envía un email directo a través de Brevo. Úsalo SOLO si te piden enviarlo en el momento."""
    return send_email(to_email, "Contacto", subject, html)


def create_lead_analyst():
    return Agent(
        role="Estratega de Ventas y Analista de Leads Digitales",
        goal="Analizar empresas argentinas locales, evaluar su presencia digital, y determinar si necesitan un servicio 'simple' (web básica) o 'pro' (rediseño completo y Ads).",
        backstory=(
            "Sos un consultor de marketing argentino experto en captación de leads. "
            "Revisás reportes técnicos de scraping y decidís rápidamente si un negocio "
            "es de barrio (necesita presencia básica) o si ya están invirtiendo en publicidad digital "
            "pero lo están haciendo mal (necesitan servicio pro de Google y Meta Ads)."
        ),
        tools=[fetch_pending_leads_tool, site_analyzer_tool, update_lead_db_tool],
        verbose=True,
        allow_delegation=False,
        llm=claude_llm
    )

def create_landing_developer():
    return Agent(
        role="Desarrollador Frontend Tailwind",
        goal="Generar una landing page en un solo archivo HTML utilizando TailwindCSS basándose en los datos del negocio y el tipo de servicio ofrecido.",
        backstory=(
            "Sos un diseñador web veloz y moderno. Creás demos de páginas web en HTML "
            "escribiendo todo integrado usando CDN de TailwindCSS (y librerías como AlpineJS si hace falta). "
            "Tus diseños son responsivos, limpios y están orientados 100% a la conversión (botones grandes, "
            "formularios visibles). Escribís código perfecto sin markdown blocks extraños si es posible, directo para guardar."
        ),
        tools=[],  # Solo genera el código basado en el prompt
        verbose=True,
        allow_delegation=False,
        llm=claude_llm
    )

def create_sales_closer():
    return Agent(
        role="Closer de Ventas Automatizado",
        goal="Orquestar la creación del link de pago, la generación del email personalizado y guardar todo empaquetado final en la base de datos.",
        backstory=(
            "Sos el último eslabón de la agencia de Gabriel. Tomás la evaluación inicial, "
            "pedís los links de pago, y ensamblás el email final usando el generador de textos (Claude)."
            "Finalmente, grabás todo el paquete listo para enviar en la base de datos para que luego se envíen automáticamente."
        ),
        tools=[generate_payment_link_tool, generate_pitch_email_tool, generate_whatsapp_pitch_tool, update_lead_db_tool, send_email_wrapper_tool_if_needed],
        verbose=True,
        allow_delegation=False,
        llm=claude_llm
    )

