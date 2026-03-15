"""
LeadGen - Gabriel Urrutia
Scraper de negocios usando Google Places API (Text Search)

Uso:
    python scrapers/google_places_scraper.py --rubro portones_automaticos
    python scrapers/google_places_scraper.py --rubro portones_automaticos --ciudades "Buenos Aires,Córdoba"
"""

import requests
import time
import json
import csv
import argparse
import os
import sys
from datetime import datetime

# Agregar root al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    GOOGLE_PLACES_API_KEY,
    CIUDADES_ARG,
    RUBROS,
    DELAY_ENTRE_REQUESTS,
    RADIO_BUSQUEDA_METROS,
    BREVO_COLUMNS,
)

BASE_URL = "https://maps.googleapis.com/maps/api/place"


# ──────────────────────────────────────────────
#  GEOCODING: ciudad → coordenadas
# ──────────────────────────────────────────────

def geocode_ciudad(ciudad: str) -> tuple[float, float] | None:
    """Convierte nombre de ciudad a (lat, lng)."""
    url = f"https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": ciudad, "key": GOOGLE_PLACES_API_KEY}
    resp = requests.get(url, params=params)
    data = resp.json()
    if data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    print(f"  ⚠️  No se pudo geocodificar: {ciudad}")
    return None


# ──────────────────────────────────────────────
#  SEARCH: query + ciudad → lista de places
# ──────────────────────────────────────────────

def buscar_lugares(query: str, location: tuple, radio: int = RADIO_BUSQUEDA_METROS) -> list[dict]:
    """
    Llama a Places Text Search y recorre páginas.
    Devuelve lista cruda de place results.
    """
    resultados = []
    url = f"{BASE_URL}/textsearch/json"
    params = {
        "query": query,
        "location": f"{location[0]},{location[1]}",
        "radius": radio,
        "language": "es",
        "key": GOOGLE_PLACES_API_KEY,
    }

    while True:
        resp = requests.get(url, params=params)
        data = resp.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            print(f"  ❌ Error API: {data.get('status')} — {data.get('error_message', '')}")
            break

        batch = data.get("results", [])
        resultados.extend(batch)
        print(f"     → {len(batch)} resultados (total: {len(resultados)})")

        next_token = data.get("next_page_token")
        if not next_token:
            break

        # Google requiere ~2 seg antes de usar el next_page_token
        time.sleep(2.5)
        params = {"pagetoken": next_token, "key": GOOGLE_PLACES_API_KEY}

    return resultados


# ──────────────────────────────────────────────
#  DETALLE: place_id → info completa
# ──────────────────────────────────────────────

def obtener_detalle(place_id: str) -> dict:
    """Obtiene website, teléfono y otros campos extra de un place."""
    url = f"{BASE_URL}/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_phone_number,website,url,formatted_address",
        "language": "es",
        "key": GOOGLE_PLACES_API_KEY,
    }
    time.sleep(DELAY_ENTRE_REQUESTS)
    resp = requests.get(url, params=params)
    data = resp.json()
    return data.get("result", {})


# ──────────────────────────────────────────────
#  NORMALIZAR: convertir resultado a fila CSV
# ──────────────────────────────────────────────

def normalizar_lead(detalle: dict, ciudad: str, rubro: str) -> dict:
    """Convierte un dict de Places Detail al formato Brevo."""
    website = detalle.get("website", "")
    tiene_website = "Sí" if website else "No"

    nombre = detalle.get("name", "")
    telefono = detalle.get("formatted_phone_number", "")
    maps_url = detalle.get("url", "")
    direccion = detalle.get("formatted_address", "")

    return {
        "EMAIL": "",                    # A completar manualmente o con hunter.io
        "FIRSTNAME": nombre,
        "LASTNAME": "",
        "COMPANY": nombre,
        "PHONE": telefono,
        "WEBSITE": website,
        "CIUDAD": ciudad.replace(", Argentina", ""),
        "RUBRO": rubro,
        "TIENE_WEBSITE": tiene_website,
        "GOOGLE_MAPS_URL": maps_url,
        "NOTAS": direccion,
    }


# ──────────────────────────────────────────────
#  DEDUPLICAR por nombre + ciudad
# ──────────────────────────────────────────────

def deduplicar(leads: list[dict]) -> list[dict]:
    vistos = set()
    unicos = []
    for lead in leads:
        key = (lead["COMPANY"].lower().strip(), lead["CIUDAD"].lower().strip())
        if key not in vistos:
            vistos.add(key)
            unicos.append(lead)
    return unicos


# ──────────────────────────────────────────────
#  EXPORTAR a CSV (formato Brevo)
# ──────────────────────────────────────────────

def exportar_csv(leads: list[dict], rubro_slug: str) -> str:
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    carpeta = os.path.join("leads", rubro_slug)
    os.makedirs(carpeta, exist_ok=True)
    filepath = os.path.join(carpeta, f"leads_{fecha}.csv")

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BREVO_COLUMNS)
        writer.writeheader()
        writer.writerows(leads)

    return filepath


# ──────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scraper de leads — Gabriel Urrutia")
    parser.add_argument("--rubro", required=True, help="Slug del rubro (ej: portones_automaticos)")
    parser.add_argument("--ciudades", default=None, help="Ciudades separadas por coma (sobreescribe settings)")
    args = parser.parse_args()

    rubro_slug = args.rubro
    if rubro_slug not in RUBROS:
        print(f"❌ Rubro '{rubro_slug}' no encontrado. Disponibles: {list(RUBROS.keys())}")
        sys.exit(1)

    rubro_cfg = RUBROS[rubro_slug]
    ciudades = args.ciudades.split(",") if args.ciudades else CIUDADES_ARG
    ciudades = [c.strip() for c in ciudades]

    print(f"\n🚀 Iniciando scraping de: {rubro_cfg['nombre']}")
    print(f"   Ciudades: {ciudades}")
    print(f"   Queries: {rubro_cfg['queries']}\n")

    todos_los_leads = []
    place_ids_vistos = set()

    for ciudad in ciudades:
        print(f"\n📍 Ciudad: {ciudad}")
        coords = geocode_ciudad(ciudad)
        if not coords:
            continue

        for query in rubro_cfg["queries"]:
            print(f"  🔍 Query: '{query}'")
            resultados = buscar_lugares(query, coords)
            time.sleep(DELAY_ENTRE_REQUESTS)

            for r in resultados:
                place_id = r.get("place_id")
                if not place_id or place_id in place_ids_vistos:
                    continue
                place_ids_vistos.add(place_id)

                detalle = obtener_detalle(place_id)
                lead = normalizar_lead(detalle, ciudad, rubro_cfg["nombre"])
                todos_los_leads.append(lead)
                print(f"     ✅ {lead['COMPANY']} | {lead['WEBSITE'] or 'sin web'} | {lead['PHONE'] or 'sin tel'}")

    # Deduplicar
    leads_unicos = deduplicar(todos_los_leads)
    print(f"\n📊 Total bruto: {len(todos_los_leads)} | Únicos: {len(leads_unicos)}")

    # Exportar
    archivo = exportar_csv(leads_unicos, rubro_slug)
    print(f"\n✅ CSV exportado en: {archivo}")
    print(f"   Listo para importar en Brevo 🎯\n")


if __name__ == "__main__":
    main()
