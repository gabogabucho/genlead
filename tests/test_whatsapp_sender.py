"""
Test manual para utils/whatsapp_sender.py
Ejecutar con: python tests/test_whatsapp_sender.py

Requiere que EVOLUTION_API_KEY, EVOLUTION_API_URL y EVOLUTION_INSTANCE_NAME
estén configurados en .env y que la instancia tenga el QR escaneado.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"), override=True)

from utils.whatsapp_sender import send_text, _normalize_phone_ar

# ── Test de normalización de teléfonos argentinos ────────────────────────────
tests_normalizacion = [
    ("011-4123-4567",     "5491141234567"),
    ("+54 9 11 4123 4567","5491141234567"),
    ("0351-4234567",      "543514234567"),
    ("+54911-4567-8901",  "54911456789"),    # más de 13 dígitos → acepta tal cual
    ("15-3456-7890",      ""),               # sin prefijo de área → no se puede normalizar
]

print("=== Test normalización de teléfonos ===")
for input_phone, expected in tests_normalizacion:
    result = _normalize_phone_ar(input_phone)
    status = "✓" if result == expected else f"✗ (esperado: {expected!r})"
    print(f"  {input_phone!r:30s} → {result!r:20s} {status}")

# ── Test de envío real ────────────────────────────────────────────────────────
TEST_PHONE = os.environ.get("TEST_PHONE", "")

if not TEST_PHONE:
    print("\n⚠  Configura TEST_PHONE en .env para probar el envío real.")
    print("   Ej: TEST_PHONE=5491145678901")
    sys.exit(0)

print(f"\n=== Test de envío real a {TEST_PHONE} ===")
result = send_text(TEST_PHONE, "✅ Test de LeadGen WhatsApp Bot — Evolution API funcionando correctamente.")
print(f"Respuesta: {result}")

if "error" not in result:
    print("✓ Envío exitoso!")
else:
    print(f"✗ Error: {result['error']}")
    sys.exit(1)
