"""
WhatsApp Bot — Respuesta automática a prospectos
Gabriel Urrutia · LeadGen

Arquitectura:
  1. Detección de intención por keywords (rápido, sin API)
  2. Fallback a Claude haiku si la intención no se reconoce (~$0.003/mensaje)

El bot responde preguntas comunes sobre el servicio de página web.
Cuando el lead dice "cómo pago" o similar, le envía el link de MercadoPago.
"""

import os
import logging
from anthropic import Anthropic

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  Mapa de intenciones → keywords
# ─────────────────────────────────────────────────────────────────────────────

INTENCIONES = {
    "precio": [
        "precio", "cuánto", "cuanto", "costo", "cobran", "cobras", "cobro",
        "vale", "cuánto sale", "cuanto sale", "tarifa", "fee", "valor",
    ],
    "que_incluye": [
        "incluye", "viene", "trae", "tiene", "qué tiene", "que tiene",
        "qué es", "que es", "de qué se trata", "explicame", "explicá",
        "contame", "cuéntame", "detalle", "información", "info",
    ],
    "pago": [
        "pagar", "pago", "mercadopago", "mp", "link de pago", "cómo pago",
        "como pago", "cómo se paga", "como se paga", "quiero pagar",
        "quiero contratar", "me interesa", "lo quiero",
    ],
    "dominio": [
        "dominio", ".com.ar", "url propia", "dirección web", "mi url",
        "nombre del sitio", "www", "página propia",
    ],
    "tiempo": [
        "cuánto tarda", "cuanto tarda", "días", "plazo", "cuándo", "cuando",
        "en cuánto tiempo", "demora", "tiempo",
    ],
    "no_interesa": [
        "no gracias", "no me interesa", "no quiero", "basta", "stop",
        "parar", "pará", "no necesito", "ya tengo", "chau", "adiós",
    ],
    "demo": [
        "demo", "ejemplo", "muestra", "ver la página", "ver el sitio",
        "link", "enlace", "url de la demo",
    ],
}


def _detectar_intencion(texto: str) -> str | None:
    texto_lower = texto.lower().strip()
    for intencion, keywords in INTENCIONES.items():
        for kw in keywords:
            if kw in texto_lower:
                return intencion
    return None


def _respuesta_por_intencion(intencion: str, lead: dict) -> str:
    empresa    = lead.get("empresa") or "tu negocio"
    landing    = lead.get("landing_url") or lead.get("landing_url_live") or ""
    mp_link    = lead.get("mp_payment_link") or ""
    rubro      = lead.get("rubro_slug", "").replace("_", " ")

    respuestas = {
        "precio": (
            f"El servicio completo para {empresa} cuesta *$50.000/mes* 🎯\n\n"
            "Incluye:\n"
            "✅ Página web profesional\n"
            "✅ Dominio .com.ar propio\n"
            "✅ Hosting incluido (Cloudflare)\n"
            "✅ Botón de WhatsApp directo\n"
            "✅ Mapa de Google\n"
            "✅ Links a tus redes sociales\n\n"
            "Sin costos adicionales. Sin sorpresas."
        ),
        "que_incluye": (
            f"Para {empresa} armamos una página web completa que incluye:\n\n"
            "📱 *Botón de WhatsApp* para que tus clientes te escriban directo\n"
            "📍 *Mapa de Google* con tu ubicación\n"
            "📸 *Galería de imágenes* de tu negocio\n"
            "🔗 *Links a tus redes* (Instagram, Facebook, etc.)\n"
            "⏰ *Horarios y servicios*\n"
            "🌐 *Dominio .com.ar* propio (ej: tunegocio.com.ar)\n\n"
            + (f"Mirá la demo que te armé: {landing}" if landing else "")
        ),
        "pago": (
            "Para contratar el servicio pagás con MercadoPago 🔒\n\n"
            + (f"*Link de pago:* {mp_link}\n\n" if mp_link else "")
            + "El cobro es mensual, $50.000/mes. Podés cancelar cuando quieras.\n\n"
            "Una vez confirmado el pago, en 24-48hs tu página está online con tu dominio propio. 🚀"
        ),
        "dominio": (
            "El dominio .com.ar queda *a tu nombre* ✅\n\n"
            f"Lo registramos en NIC.ar (el registro oficial de Argentina). "
            f"Algo como *tunegocionombre.com.ar*.\n\n"
            "El hosting es en Cloudflare (la red más rápida del mundo). "
            "Todo incluido en los $50.000/mes."
        ),
        "tiempo": (
            "Una vez que confirmás el pago:\n\n"
            "⚡ *24-48 horas* y tu página está online con tu dominio .com.ar\n\n"
            "Si querés hacer cambios después (actualizar precios, fotos, horarios), "
            "solo avisame y lo actualizamos."
        ),
        "no_interesa": (
            f"Entendido, sin problema! 🙏 "
            f"Si en algún momento cambiás de idea, acá voy a estar. "
            f"Mucho éxito con {empresa}! 💪"
        ),
        "demo": (
            (f"Acá está la demo que armé para {empresa}:\n\n🌐 {landing}\n\n"
             "¿Qué te parece? ¿Querés hacer algún cambio o ya la querés online?"
             if landing else
             f"Estoy armando la demo para {empresa}! En breve te la mando. 🔨")
        ),
    }

    return respuestas.get(intencion, "")


def _respuesta_claude_fallback(texto: str, lead: dict, historial: list[dict]) -> str:
    """
    Usa Claude Haiku para responder mensajes que no caen en ninguna intención conocida.
    Solo se llama cuando el mapa de keywords no matchea.
    """
    try:
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

        empresa = lead.get("empresa") or "el negocio"
        landing = lead.get("landing_url") or ""
        mp_link = lead.get("mp_payment_link") or ""
        ciudad  = lead.get("ciudad") or "Argentina"

        system_prompt = (
            f"Sos un asistente de ventas de Gabriel Urrutia, un diseñador web argentino. "
            f"Estás hablando con el dueño de '{empresa}' en {ciudad}. "
            f"Le ofrecés una página web profesional por $50.000/mes (pesos argentinos), "
            f"que incluye dominio .com.ar, hosting, botón de WhatsApp, mapa, galería y redes sociales. "
            + (f"Demo de su página: {landing}. " if landing else "")
            + (f"Link de pago MercadoPago: {mp_link}. " if mp_link else "")
            + "Respondé de manera amigable, concisa (máximo 3 oraciones), en español rioplatense. "
            "Si te preguntan algo que no tiene que ver con el servicio, "
            "redirigí la conversación al tema de la página web."
        )

        # Incluir los últimos 5 mensajes del historial para contexto
        messages = []
        for msg in historial[-5:]:
            role = "user" if msg.get("direction") == "inbound" else "assistant"
            messages.append({"role": role, "content": msg.get("message", "")})

        # Agregar el mensaje actual
        messages.append({"role": "user", "content": texto})

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text

    except Exception as e:
        logger.error(f"[WA Bot] Error en fallback Claude: {e}")
        return (
            "Gracias por escribirme! 🙏 "
            "Cualquier pregunta sobre la página web que armé para tu negocio, "
            "con gusto te respondo."
        )


def procesar_mensaje(lead: dict, texto: str, historial: list[dict]) -> str:
    """
    Procesa un mensaje entrante y retorna la respuesta del bot.

    Args:
        lead: Dict con datos del lead (empresa, telefono, landing_url, mp_payment_link, etc.)
        texto: Texto del mensaje entrante
        historial: Lista de dicts con mensajes anteriores [{direction, message}, ...]

    Returns:
        String con la respuesta a enviar
    """
    if not texto or not texto.strip():
        return ""

    intencion = _detectar_intencion(texto)
    logger.info(f"[WA Bot] Lead {lead.get('id')} — intención detectada: {intencion!r}")

    if intencion:
        return _respuesta_por_intencion(intencion, lead)

    # Fallback: Claude Haiku
    logger.info(f"[WA Bot] Lead {lead.get('id')} — usando fallback Claude para: {texto!r}")
    return _respuesta_claude_fallback(texto, lead, historial)
