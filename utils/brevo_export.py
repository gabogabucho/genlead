"""
LeadGen - Gabriel Urrutia
Utilidad para preparar el CSV final listo para importar en Brevo.

- Filtra leads sin email (para revisión manual)
- Filtra leads CON website (más probable que usen Ads)
- Genera dos archivos: listos_brevo.csv y pendientes_email.csv
"""

import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import BREVO_COLUMNS


def procesar_leads(input_csv: str, rubro_slug: str):
    """
    Lee un CSV de leads scrapeados y lo divide en:
    - listos_brevo.csv     → tienen email, listos para importar
    - pendientes_email.csv → no tienen email, requieren búsqueda manual
    """
    if not os.path.exists(input_csv):
        print(f"❌ Archivo no encontrado: {input_csv}")
        return

    listos = []
    pendientes = []

    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = row.get("EMAIL", "").strip()
            if email and "@" in email:
                listos.append(row)
            else:
                pendientes.append(row)

    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    carpeta = os.path.join("exports", rubro_slug)
    os.makedirs(carpeta, exist_ok=True)

    # Exportar listos
    if listos:
        out_listos = os.path.join(carpeta, f"brevo_listos_{fecha}.csv")
        _escribir_csv(listos, out_listos)
        print(f"✅ {len(listos)} leads listos para Brevo → {out_listos}")
    else:
        print("⚠️  No hay leads con email aún.")

    # Exportar pendientes
    if pendientes:
        out_pend = os.path.join(carpeta, f"pendientes_email_{fecha}.csv")
        _escribir_csv(pendientes, out_pend)
        print(f"📋 {len(pendientes)} leads sin email → {out_pend}")
        print("   Tip: buscá el email manualmente en el sitio web o usando hunter.io")


def _escribir_csv(rows: list[dict], filepath: str):
    """Escribe una lista de dicts a CSV."""
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="CSV generado por el scraper")
    parser.add_argument("--rubro", required=True, help="Slug del rubro")
    args = parser.parse_args()
    procesar_leads(args.input, args.rubro)
