"""
WhatsApp Sender — Evolution API wrapper
Gabriel Urrutia · LeadGen

Evolution API es open source y se deploya en el mismo VPS.
Endpoint base: http://localhost:8080 (configurable via EVOLUTION_API_URL)

Docs: https://doc.evolution-api.com/
"""

import os
import re
import requests

EVOLUTION_API_URL      = os.environ.get("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY      = os.environ.get("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE     = os.environ.get("EVOLUTION_INSTANCE_NAME", "vendedor")


def _normalize_phone_ar(phone: str) -> str:
    """
    Normaliza un número de teléfono argentino al formato E.164 sin '+':
    5491145678901  (celular GBA)
    5493516234567  (celular Córdoba)

    Formatos de entrada aceptados:
      011-4xxx-xxxx   → 5491145678xxx
      +54 9 11 xxxx   → 549114xxxxxxx
      0351 4xx-xxxx   → 543514xxxxxxx
      15-3xxx-xxxx    → depende de área (se ignoran sin prefijo de área)
      (011) 4xxx-xxxx → 5491145678xxx
      +5491145678901  → 5491145678901
    """
    if not phone:
        return ""

    # 1. Quitar todo excepto dígitos y el + inicial
    cleaned = re.sub(r"[^\d+]", "", phone)

    # 2. Quitar el + si existe al inicio
    cleaned = cleaned.lstrip("+")

    # 3. Si ya empieza con 54 y tiene 13 dígitos → ya está en formato correcto
    if cleaned.startswith("54") and len(cleaned) >= 12:
        return cleaned

    # 4. Si empieza con 0 → reemplazar el 0 por 54
    if cleaned.startswith("0"):
        cleaned = "54" + cleaned[1:]

    # 5. Si empieza con 54 pero falta el 9 (ej: 541145678901 → 5491145678901)
    # El 9 es requerido para celulares. Si el número es 54 + código área + número sin 9:
    if cleaned.startswith("54") and len(cleaned) == 12:
        # Insertar 9 después de 54
        cleaned = "54" + "9" + cleaned[2:]

    # 6. Si quedó muy corto (ej: solo un número local), retornar vacío para evitar envíos erróneos
    if len(cleaned) < 10:
        return ""

    return cleaned


def send_text(phone: str, message: str) -> dict:
    """
    Envía un mensaje de texto por WhatsApp via Evolution API.

    Args:
        phone: Número de teléfono (cualquier formato argentino)
        message: Texto a enviar

    Returns:
        dict con la respuesta de la API, o {"error": str} si falla.
    """
    normalized = _normalize_phone_ar(phone)
    if not normalized:
        print(f"[WA Sender] Teléfono inválido o no normalizable: {phone!r}")
        return {"error": f"Teléfono inválido: {phone}"}

    if not EVOLUTION_API_KEY:
        print("[WA Sender] EVOLUTION_API_KEY no configurada en .env")
        return {"error": "EVOLUTION_API_KEY no configurada"}

    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "number": normalized,
        "text": message,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        msg_id = data.get("key", {}).get("id") or data.get("messageId", "")
        print(f"[WA Sender] Mensaje enviado a {normalized}. ID: {msg_id}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"[WA Sender] Error enviando mensaje a {normalized}: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"[WA Sender] Response: {e.response.text}")
        return {"error": str(e)}
