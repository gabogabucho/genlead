import os
import requests

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "TU_BREVO_API_KEY_AQUI")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "gabriel@gabrielurrutia.com.ar")
SENDER_NAME = os.environ.get("SENDER_NAME", "Gabriel Urrutia")

def send_email(to_email: str, to_name: str, subject: str, html_content: str) -> str:
    """
    Envía un email usando la API de Brevo (Sendinblue).
    Retorna el messageId si es exitoso, o un string vacío si falla.
    """
    if not to_email or "@" not in to_email:
        print(f"Email inválido: {to_email}")
        return ""

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    payload = {
        "sender": {
            "name": SENDER_NAME,
            "email": SENDER_EMAIL
        },
        "to": [
            {
                "email": to_email,
                "name": to_name
            }
        ],
        "subject": subject,
        "htmlContent": html_content
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        print(f"Email enviado a {to_email}. Message ID: {data.get('messageId')}")
        return data.get("messageId", "")
    except requests.exceptions.RequestException as e:
        print(f"Error enviando email a {to_email}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return ""
