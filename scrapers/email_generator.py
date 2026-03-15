"""
LeadGen - Gabriel Urrutia
Generador de emails personalizados usando Claude API.

Toma el análisis de un sitio web y genera un email
con los dolores ESPECÍFICOS de esa empresa.

Uso:
  # Generar emails desde CSV de análisis
  python scrapers/email_generator.py --input exports/portones_automaticos/analisis_FECHA.csv

  # Modo dry-run: genera emails y los guarda sin enviar
  python scrapers/email_generator.py --input exports/portones_automaticos/analisis_FECHA.csv --dry-run
"""

import anthropic
import csv
import json
import os
import sys
import argparse
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "TU_API_KEY_AQUI")

# ──────────────────────────────────────────────
#  PROMPT SYSTEM — el "copywriter" de Gabriel
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """Sos el asistente de ventas de Gabriel Urrutia, especialista en Google Ads y páginas web de alta conversión en Argentina.

Tu tarea es escribir emails de prospección en frío ULTRA personalizados para dueños de empresas PyME en Argentina.

REGLAS DEL EMAIL:
- Tono: cercano, directo, respetuoso. Ni muy formal ni muy informal. Como habla un profesional argentino.
- Longitud: corto. Máximo 5 párrafos. Cada párrafo máximo 3 líneas.
- Nunca empieces con "Espero que estés bien" ni frases de relleno.
- Mencioná al menos 2 problemas ESPECÍFICOS del sitio que analizaste (los que te pase en el contexto).
- Si detectamos que NO tienen Google Ads: el enfoque es "estás perdiendo clientes frente a competidores que sí invierten".
- Si detectamos que SÍ tienen Google Ads: el enfoque es "tu inversión en Ads no está convirtiendo todo lo que podría".
- Cerrá siempre con una pregunta simple que invite a responder (no "¿Te interesa?" sino algo más específico).
- El email va en formato HTML limpio, inline styles solamente, apto para clientes de email.
- El asunto del email va PRIMERO, separado con el tag <ASUNTO> así: <ASUNTO>El texto del asunto aquí</ASUNTO>

OFERTA DE GABRIEL:
- Servicio: Gestión de Google Ads + Meta Ads + Página web nueva optimizada para conversión
- Precio: USD 1.000/mes
- Garantía: si en 30 días no ven mejora, cancelan sin cargo
- Web: gabrielurrutia.com.ar
- WhatsApp: (insertar número)

FORMATO DE RESPUESTA:
Devolvé SOLO el asunto y el HTML del email. Nada más. Sin explicaciones."""


# ──────────────────────────────────────────────
#  GENERAR EMAIL PARA UN LEAD
# ──────────────────────────────────────────────

def generar_email(lead: dict, client: anthropic.Anthropic) -> dict:
    """
    Toma un dict de análisis y genera el email personalizado.
    Retorna el lead enriquecido con 'email_asunto' y 'email_html'.
    """
    empresa    = lead.get("empresa", "la empresa")
    ciudad     = lead.get("ciudad", "")
    url        = lead.get("url", "")
    dolores    = lead.get("dolores", "")
    tiene_ads  = lead.get("google_ads_detectado", "False") in (True, "True", "true", "1")
    score      = lead.get("score_calidad", "?")
    titulo     = lead.get("titulo", "")
    whatsapp   = lead.get("whatsapp", "False") in (True, "True", "true", "1")
    mobile     = lead.get("mobile_viewport", "True") in (True, "True", "true", "1")
    formulario = lead.get("formulario_contacto", "False") in (True, "True", "true", "1")
    telefono   = lead.get("tiene_telefono", "True") in (True, "True", "true", "1")
    tiempo_resp= lead.get("tiempo_respuesta", "?")

    # Construir contexto detallado del análisis
    contexto_analisis = f"""
EMPRESA: {empresa}
CIUDAD: {ciudad}
SITIO WEB: {url}
TÍTULO DE SU PÁGINA: {titulo}
SCORE DE CALIDAD WEB: {score}/10
USA GOOGLE ADS: {"SÍ" if tiene_ads else "NO"}

PROBLEMAS DETECTADOS AUTOMÁTICAMENTE:
{dolores if dolores else "El sitio parece bien configurado, buscar ángulo diferencial"}

DETALLE TÉCNICO:
- WhatsApp en el sitio: {"Sí" if whatsapp else "NO - no tienen botón de WhatsApp"}
- Formulario de contacto: {"Sí" if formulario else "NO - no capturan leads fuera de horario"}
- Optimizado para mobile: {"Sí" if mobile else "NO - sitio no adaptado para celulares"}
- Teléfono visible: {"Sí" if telefono else "NO - difícil contactarlos"}
- Velocidad de carga: {tiempo_resp}s {"(aceptable)" if float(str(tiempo_resp).replace("?","0") or 0) < 2 else "(LENTO - Google penaliza)"}
"""

    prompt_usuario = f"""Escribí un email de prospección en frío para esta empresa:

{contexto_analisis}

Generá el asunto y el HTML del email personalizado siguiendo todas las reglas del sistema."""

    try:
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt_usuario}],
        )
        respuesta = message.content[0].text.strip()

        # Extraer asunto
        asunto = ""
        html_email = respuesta
        if "<ASUNTO>" in respuesta:
            import re
            m = re.search(r"<ASUNTO>(.*?)</ASUNTO>", respuesta, re.DOTALL)
            if m:
                asunto = m.group(1).strip()
                html_email = respuesta.replace(f"<ASUNTO>{m.group(1)}</ASUNTO>", "").strip()

        return {**lead, "email_asunto": asunto, "email_html": html_email, "error_generacion": ""}

    except Exception as e:
        print(f"  ❌ Error generando email para {empresa}: {e}")
        return {**lead, "email_asunto": "", "email_html": "", "error_generacion": str(e)}


# ──────────────────────────────────────────────
#  EXPORTAR
# ──────────────────────────────────────────────

def exportar_emails(resultados: list[dict], rubro_slug: str = "leads"):
    """
    Guarda:
    - Un CSV con todos los campos + asunto + html del email
    - Un HTML individual por empresa en emails/
    """
    fecha    = datetime.now().strftime("%Y%m%d_%H%M")
    carpeta  = os.path.join("exports", rubro_slug, f"emails_{fecha}")
    os.makedirs(carpeta, exist_ok=True)

    # CSV master
    csv_path = os.path.join(carpeta, "leads_con_emails.csv")
    campos   = list(resultados[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        writer.writeheader()
        # Omitir html en CSV (muy largo), solo guardar asunto
        for r in resultados:
            row = {k: v for k, v in r.items() if k != "email_html"}
            writer.writerow(row)

    # HTMLs individuales
    for r in resultados:
        if r.get("email_html"):
            nombre_safe = r["empresa"].replace(" ", "_").replace("/", "-")
            html_path   = os.path.join(carpeta, f"{nombre_safe}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(f"<!-- ASUNTO: {r.get('email_asunto', '')} -->\n")
                f.write(r["email_html"])

    print(f"\n📧 Emails exportados → {carpeta}/")
    print(f"   CSV master    : leads_con_emails.csv")
    print(f"   HTMLs         : uno por empresa")
    return carpeta


# ──────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generador de emails — Gabriel Urrutia")
    parser.add_argument("--input",    required=True, help="CSV de análisis (salida de site_analyzer.py)")
    parser.add_argument("--rubro",    default="leads", help="Slug del rubro")
    parser.add_argument("--limit",    type=int, default=10, help="Máx leads a procesar")
    parser.add_argument("--dry-run",  action="store_true", help="Genera emails pero no envía nada")
    parser.add_argument("--api-key",  default=ANTHROPIC_API_KEY, help="Anthropic API key")
    args = parser.parse_args()

    client = anthropic.Anthropic(api_key=args.api_key)

    # Leer análisis
    leads = []
    with open(args.input, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("accesible", "").lower() in ("true", "1", "yes"):
                leads.append(row)

    leads = leads[:args.limit]
    print(f"\n✉️  Generando emails personalizados para {len(leads)} empresas...\n{'─'*50}")

    resultados = []
    for lead in leads:
        print(f"\n  📝 {lead['empresa']} ({lead.get('ciudad', '')})")
        print(f"     Score: {lead.get('score_calidad','?')}/10 | Ads: {lead.get('google_ads_detectado','?')}")
        r = generar_email(lead, client)
        if r.get("email_asunto"):
            print(f"     ✅ Asunto: {r['email_asunto']}")
        resultados.append(r)
        time.sleep(0.5)

    carpeta = exportar_emails(resultados, args.rubro)

    print(f"\n🎯 Listo. Revisá los HTMLs en: {carpeta}")
    if args.dry_run:
        print("   (modo dry-run — no se envió nada)")


if __name__ == "__main__":
    main()
