import os
import requests

MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "TEST-TU_ACCESS_TOKEN_AQUI")
VENDEDOR_EMAIL = os.environ.get("VENDEDOR_EMAIL", "tucorreo@ejemplo.com")
MP_WEBHOOK_URL = os.environ.get("MP_WEBHOOK_URL", "https://tudominio.com/api/mp/webhook")
BACK_URL_BASE  = os.environ.get("BACK_URL_BASE", "https://gabrielurrutia.com.ar")

def generar_suscripcion(lead_id: int, empresa: str, monto: float = 50000.0) -> dict:
    """
    Genera un link de suscripción recurrente mensual en MercadoPago (Preapproval).
    El cliente paga $50.000/mes automáticamente.

    Returns dict con 'preapproval_id', 'init_point' (link de pago) y 'sandbox_init_point'.
    """
    url = "https://api.mercadopago.com/preapproval"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "reason": f"Página web + dominio .com.ar — {empresa}",
        "auto_recurring": {
            "frequency":          1,
            "frequency_type":     "months",
            "transaction_amount": float(monto),
            "currency_id":        "ARS",
        },
        "back_url":          f"{BACK_URL_BASE}/exito",
        "external_reference": str(lead_id),
        "notification_url":   MP_WEBHOOK_URL,
        "status":             "pending",
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return {
            "preapproval_id": data.get("id"),
            "init_point":     data.get("init_point"),
            "sandbox_init_point": data.get("sandbox_init_point"),
        }
    except requests.exceptions.RequestException as e:
        print(f"Error generando suscripción MP para lead {lead_id}: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response: {e.response.text}")
        return {}


def generar_link_pago(lead_id: int, titulo_servicio: str, monto: float, descripcion: str) -> dict:
    """
    Genera un link de pago de MercadoPago (Preference) para un lead específico.
    Retorna un diccionario con 'preference_id' y 'init_point' (el link).
    """
    url = "https://api.mercadopago.com/checkout/preferences"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "items": [
            {
                "title": titulo_servicio,
                "description": descripcion,
                "quantity": 1,
                "currency_id": "ARS",
                "unit_price": float(monto)
            }
        ],
        "payer": {
            "email": VENDEDOR_EMAIL # Opcionalmente el del cliente si lo tuvieramos
        },
        "external_reference": str(lead_id),
        "notification_url": os.environ.get("MP_WEBHOOK_URL", "https://tudominio.com/api/mp/webhook"),
        "auto_return": "approved",
        "back_urls": {
            "success": "https://gabrielurrutia.com.ar/exito",
            "failure": "https://gabrielurrutia.com.ar/error",
            "pending": "https://gabrielurrutia.com.ar/pendiente"
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return {
            "preference_id": data.get("id"),
            "init_point": data.get("init_point"),   # Link de pago (producción)
            "sandbox_init_point": data.get("sandbox_init_point") # Link de pago (pruebas)
        }
    except requests.exceptions.RequestException as e:
        print(f"Error generando link de MP para lead {lead_id}: {e}")
        if response is not None:
             print(f"Response: {response.text}")
        return {}
