"""
LeadGen - Gabriel Urrutia
Analizador automático de sitios web de leads.

Detecta:
  - Google Ads activos (tag AW- en HTML)
  - Meta Ads / Facebook Pixel
  - Google Analytics / GTM
  - Mobile viewport
  - Teléfono visible en la página
  - WhatsApp link
  - Formulario de contacto
  - SSL / HTTPS
  - Tiempo de respuesta
  - Meta título y descripción

Uso:
  # Analizar CSV scrapeado
  python scrapers/site_analyzer.py --input leads/portones_automaticos/leads_FECHA.csv

  # Analizar lista manual de URLs
  python scrapers/site_analyzer.py --urls "http://ejemplo.com,http://otro.com"
"""

import requests
import re
import csv
import time
import os
import sys
import argparse
from datetime import datetime
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import DELAY_ENTRE_REQUESTS

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

TIMEOUT = 12  # segundos
APIFY_ACTOR = os.environ.get("APIFY_INSTAGRAM_ACTOR", "apify~instagram-scraper")
APIFY_SEARCH_ACTOR = os.environ.get("APIFY_INSTAGRAM_SEARCH_ACTOR", "apify~instagram-search-scraper")
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")

THIRD_PARTY_DOMAINS = {
    "linktr.ee",
    "linktree.com",
    "wa.me",
    "whatsapp.com",
    "calendly.com",
    "booksy.com",
    "timify.com",
    "agenda.com",
    "turnos.com",
    "hotmart.com",
    "mercadopago.com",
    "mpago.la",
}


# ──────────────────────────────────────────────
#  FETCH
# ──────────────────────────────────────────────

def fetch_site(url: str) -> tuple[str | None, float, int]:
    """
    Descarga el HTML de una URL.
    Retorna (html, tiempo_respuesta_seg, status_code).
    """
    if not url.startswith("http"):
        url = "https://" + url
    try:
        t0 = time.time()
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        elapsed = round(time.time() - t0, 2)
        return resp.text, elapsed, resp.status_code
    except requests.exceptions.SSLError:
        try:
            t0 = time.time()
            resp = requests.get(url.replace("https://", "http://"), headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            elapsed = round(time.time() - t0, 2)
            return resp.text, elapsed, resp.status_code
        except Exception:
            return None, 0, 0
    except Exception:
        return None, 0, 0


# ──────────────────────────────────────────────
#  CHECKS INDIVIDUALES
# ──────────────────────────────────────────────

def check_google_ads(html: str) -> bool:
    """Detecta tag de conversión de Google Ads (gtag AW-XXXXXXXX)."""
    return bool(re.search(r"AW-\d{7,12}", html))

def check_meta_ads(html: str) -> bool:
    """Detecta Facebook Pixel o Meta Ads."""
    patterns = [
        r"fbq\s*\(",
        r"facebook\.net/en_US/fbevents\.js",
        r"connect\.facebook\.net",
        r"_fbp",
    ]
    return any(re.search(p, html) for p in patterns)

def check_gtm(html: str) -> bool:
    """Detecta Google Tag Manager."""
    return bool(re.search(r"googletagmanager\.com/gtm\.js", html))

def check_google_analytics(html: str) -> bool:
    """Detecta Google Analytics (GA4 o UA)."""
    patterns = [
        r"G-[A-Z0-9]{6,12}",       # GA4
        r"UA-\d{6,12}-\d",          # Universal Analytics
        r"google-analytics\.com",
    ]
    return any(re.search(p, html) for p in patterns)

def check_mobile_viewport(html: str) -> bool:
    """Detecta meta viewport (indicador básico de mobile-friendly)."""
    return bool(re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.IGNORECASE))

def check_ssl(url: str) -> bool:
    """URL usa HTTPS."""
    return url.startswith("https://")

def check_phone(html: str) -> tuple[bool, str]:
    """Busca número de teléfono argentino visible en el HTML."""
    patterns = [
        r"\+54[\s\-]?9?[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{4}[\s\-]?\d{4}",
        r"0\d{2,4}[\s\-]?\d{6,8}",
        r"15[\s\-]?\d{4}[\s\-]?\d{4}",
        r"\(?\d{2,4}\)?[\s\-]\d{4}[\s\-]\d{4}",
    ]
    for p in patterns:
        m = re.search(p, html)
        if m:
            return True, m.group(0).strip()
    return False, ""

def check_whatsapp(html: str) -> bool:
    """Detecta link de WhatsApp."""
    return bool(re.search(r"wa\.me|whatsapp\.com|api\.whatsapp", html, re.IGNORECASE))

def check_contact_form(html: str) -> bool:
    """Detecta formulario de contacto básico."""
    has_form = bool(re.search(r"<form", html, re.IGNORECASE))
    has_email_input = bool(re.search(r'type=["\']email["\']', html, re.IGNORECASE))
    has_submit = bool(re.search(r'type=["\']submit["\']|<button', html, re.IGNORECASE))
    return has_form and (has_email_input or has_submit)

def check_meta_title(html: str) -> str:
    """Extrae el meta title."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        return title[:80]
    return ""

def check_meta_description(html: str) -> str:
    """Extrae la meta description."""
    m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()[:120]
    return ""


def extract_instagram_url(html: str) -> str:
    """Intenta encontrar un perfil de Instagram en el HTML."""
    if not html:
        return ""
    matches = re.findall(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)", html)
    if not matches:
        return ""
    # Filtrar rutas no-perfil
    for handle in matches:
        if handle.lower() in ("p", "reel", "tv", "stories", "explore"):
            continue
        return f"https://www.instagram.com/{handle}"
    return ""


def is_third_party_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url if url.startswith("http") else "https://" + url)
        host = (parsed.netloc or "").lower()
        host = host.replace("www.", "")
        return host in THIRD_PARTY_DOMAINS
    except Exception:
        return False


def fetch_instagram_profile(insta_url: str) -> dict:
    """Obtiene bio, foto y ultimos posts via Apify (si hay token)."""
    if not APIFY_TOKEN or not insta_url:
        return {}
    url = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
    payload = {
        "directUrls": [insta_url],
        "resultsType": "details",
        "resultsLimit": 1,
    }
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {APIFY_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=90,
        )
        if resp.status_code >= 400:
            return {}
        items = resp.json()
        if not isinstance(items, list) or not items:
            return {}
        profile = items[0]
        bio = profile.get("biography", "") or ""
        profile_pic = profile.get("profilePicUrlHD") or profile.get("profilePicUrl") or ""
        latest_posts = profile.get("latestPosts", []) or []
        images = []
        for p in latest_posts:
            if isinstance(p, dict) and p.get("displayUrl"):
                images.append(p["displayUrl"])
            if len(images) >= 6:
                break
        return {
            "bio": bio,
            "profile_pic": profile_pic,
            "external_url": profile.get("externalUrl") or "",
            "images": images,
        }
    except Exception:
        return {}


def _norm(txt: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (txt or "").lower()).strip()


def _score_profile(company: str, city: str, profile: dict) -> int:
    score = 0
    name = _norm(profile.get("fullName") or profile.get("name") or "")
    username = _norm(profile.get("username") or "")
    bio = _norm(profile.get("biography") or profile.get("bio") or "")
    company_norm = _norm(company)
    city_norm = _norm(city)

    if company_norm and (company_norm in name or company_norm in username):
        score += 2
    if city_norm and city_norm in bio:
        score += 1

    external = _norm(profile.get("externalUrl") or profile.get("externalUrlText") or "")
    if external and (company_norm and company_norm.split(" ")[0] in external):
        score += 1

    return score


def fetch_instagram_by_search(company: str, city: str) -> dict:
    """Busca perfiles por nombre/ciudad y devuelve el mejor match."""
    if not APIFY_TOKEN or not company:
        return {}
    url = f"https://api.apify.com/v2/acts/{APIFY_SEARCH_ACTOR}/run-sync-get-dataset-items"
    payload = {
        "search": f"{company} {city}".strip(),
        "searchType": "place",
        "searchLimit": 3,
        "resultsType": "profiles",
        "resultsLimit": 3,
    }
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {APIFY_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=90,
        )
        if resp.status_code >= 400:
            return {}
        items = resp.json()
        if not isinstance(items, list) or not items:
            return {}

        best = None
        best_score = -1
        for it in items:
            if not isinstance(it, dict):
                continue
            s = _score_profile(company, city, it)
            if s > best_score:
                best_score = s
                best = it

        if not best or best_score < 2:
            return {}

        bio = best.get("biography") or best.get("bio") or ""
        profile_pic = best.get("profilePicUrlHD") or best.get("profilePicUrl") or ""
        images = []
        posts = best.get("latestPosts") or best.get("posts") or []
        if isinstance(posts, list):
            for p in posts:
                if isinstance(p, dict) and p.get("displayUrl"):
                    images.append(p["displayUrl"])
                if len(images) >= 6:
                    break

        username = best.get("username") or ""
        return {
            "bio": bio,
            "profile_pic": profile_pic,
            "external_url": best.get("externalUrl") or best.get("externalUrlText") or "",
            "images": images,
            "username": username,
            "profile_url": f"https://www.instagram.com/{username}" if username else "",
        }
    except Exception:
        return {}


def extract_brand_colors(html: str) -> list[str]:
    """Extrae colores hex más frecuentes desde CSS inline o <style>."""
    if not html:
        return []
    # Capturar colores hex tipo #fff o #ffffff
    colors = re.findall(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\\b", html)
    if not colors:
        return []

    normalized = []
    for c in colors:
        c = c.lower()
        if len(c) == 4:
            # expandir #abc -> #aabbcc
            c = "#" + "".join(ch * 2 for ch in c[1:])
        normalized.append(c)

    # Contar frecuencias
    counts = {}
    for c in normalized:
        counts[c] = counts.get(c, 0) + 1

    # Ordenar por frecuencia
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)

    # Filtrar colores comunes de fondo
    ignore = {"#ffffff", "#000000", "#f5f5f5", "#f6f6f6", "#f7f7f7", "#f8f8f8", "#f9f9f9"}
    palette = [c for c, _ in ordered if c not in ignore]
    if not palette:
        palette = [c for c, _ in ordered]

    # Devolver top 3
    return palette[:3]


# ──────────────────────────────────────────────
#  SCORE Y OPORTUNIDADES
# ──────────────────────────────────────────────

def calcular_score_y_dolores(checks: dict) -> tuple[int, list[str]]:
    """
    Devuelve un score de 0-10 y lista de dolores detectados.
    Score BAJO = más oportunidad de mejora para Gabriel.
    """
    dolores = []
    score = 10

    if not checks["ssl"]:
        dolores.append("❌ Sin HTTPS — pérdida de confianza y penalización en Google")
        score -= 2

    if not checks["mobile_viewport"]:
        dolores.append("📱 Sin optimización mobile — pierden ~50% del tráfico")
        score -= 2

    if checks["tiempo_respuesta"] > 3:
        dolores.append(f"🐌 Carga lenta ({checks['tiempo_respuesta']}s) — Google penaliza y usuarios se van")
        score -= 1

    if not checks["tiene_telefono"]:
        dolores.append("📞 Sin teléfono visible — fricción para contactar")
        score -= 1

    if not checks["whatsapp"]:
        dolores.append("💬 Sin WhatsApp — canal de contacto más usado en Argentina")
        score -= 1

    if not checks["formulario_contacto"]:
        dolores.append("📋 Sin formulario — no capturan leads fuera del horario")
        score -= 1

    if not checks["meta_description"]:
        dolores.append("🔍 Sin meta description — anuncios y resultados orgánicos pobres")
        score -= 1

    if not checks["titulo"] or len(checks["titulo"]) < 10:
        dolores.append("📝 Título de página débil o genérico")
        score -= 1

    return max(score, 0), dolores


# ──────────────────────────────────────────────
#  ANALIZAR UN SITIO
# ──────────────────────────────────────────────

def analizar_sitio(nombre: str, url: str, ciudad: str = "") -> dict:
    """Analiza un sitio y retorna dict con todos los checks."""
    print(f"\n  🔍 Analizando: {nombre}")
    print(f"     URL: {url}")

    if not url:
        return {
            "empresa": nombre,
            "ciudad": ciudad,
            "url": url,
            "accesible": False,
            "error": "Sin URL",
        }

    html, elapsed, status = fetch_site(url)

    if not html or status == 0:
        print(f"     ❌ No accesible (status: {status})")
        return {
            "empresa": nombre,
            "ciudad": ciudad,
            "url": url,
            "accesible": False,
            "error": f"HTTP {status}",
        }

    print(f"     ✅ OK ({status}) — {elapsed}s")

    tiene_tel, numero_tel = check_phone(html)
    instagram_url = extract_instagram_url(html)
    ig_profile = fetch_instagram_profile(instagram_url)
    web_terceros = is_third_party_url(url)
    if not ig_profile and (not url or web_terceros):
        ig_profile = fetch_instagram_by_search(nombre, ciudad)
        if ig_profile.get("profile_url"):
            instagram_url = ig_profile.get("profile_url", instagram_url)

    checks = {
        "empresa": nombre,
        "ciudad": ciudad,
        "url": url,
        "web_terceros": web_terceros,
        "web_propia": False if web_terceros else bool(url),
        "accesible": True,
        "status_http": status,
        "tiempo_respuesta": elapsed,
        "ssl": check_ssl(url if url.startswith("http") else "https://" + url),
        "mobile_viewport": check_mobile_viewport(html),
        "google_ads_detectado": check_google_ads(html),
        "meta_ads_detectado": check_meta_ads(html),
        "google_analytics": check_google_analytics(html),
        "gtm": check_gtm(html),
        "tiene_telefono": tiene_tel,
        "numero_telefono": numero_tel,
        "whatsapp": check_whatsapp(html),
        "formulario_contacto": check_contact_form(html),
        "titulo": check_meta_title(html),
        "meta_description": check_meta_description(html),
        "brand_colors": extract_brand_colors(html),
        "instagram_url": instagram_url,
        "instagram_bio": ig_profile.get("bio", ""),
        "instagram_external_url": ig_profile.get("external_url", ""),
        "instagram_profile_pic": ig_profile.get("profile_pic", ""),
        "instagram_images": ig_profile.get("images", []),
    }

    score, dolores = calcular_score_y_dolores(checks)
    checks["score_calidad"] = score
    checks["dolores"] = " | ".join(dolores)
    checks["cantidad_dolores"] = len(dolores)

    # Print resumen
    ads_str = "🎯 USA GOOGLE ADS" if checks["google_ads_detectado"] else "— sin Ads detectados"
    print(f"     {ads_str} | Score web: {score}/10 | {len(dolores)} problemas")
    if dolores:
        for d in dolores[:3]:
            print(f"       → {d}")

    return checks


# ──────────────────────────────────────────────
#  EXPORTAR RESULTADOS
# ──────────────────────────────────────────────

def exportar_resultados(resultados: list[dict], rubro_slug: str = "leads"):
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    carpeta = os.path.join("exports", rubro_slug)
    os.makedirs(carpeta, exist_ok=True)
    filepath = os.path.join(carpeta, f"analisis_{fecha}.csv")

    campos = [
        "empresa", "ciudad", "url", "accesible", "score_calidad", "cantidad_dolores",
        "google_ads_detectado", "meta_ads_detectado", "google_analytics", "gtm",
        "ssl", "mobile_viewport", "tiempo_respuesta",
        "tiene_telefono", "numero_telefono", "whatsapp", "formulario_contacto",
        "titulo", "meta_description", "dolores", "error",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(resultados)

    print(f"\n📊 Análisis exportado → {filepath}")
    return filepath


# ──────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Analizador de sitios — Gabriel Urrutia")
    parser.add_argument("--input", help="CSV de leads scrapeados")
    parser.add_argument("--urls", help="URLs separadas por coma (modo manual)")
    parser.add_argument("--limit", type=int, default=10, help="Máx de sitios a analizar (default: 10)")
    parser.add_argument("--rubro", default="leads", help="Slug del rubro para organizar exports")
    args = parser.parse_args()

    leads_a_analizar = []

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("WEBSITE"):
                    leads_a_analizar.append({
                        "nombre": row.get("COMPANY", row.get("FIRSTNAME", "?")),
                        "url": row["WEBSITE"],
                        "ciudad": row.get("CIUDAD", ""),
                    })
        print(f"📂 {len(leads_a_analizar)} leads con website encontrados en CSV")

    elif args.urls:
        for url in args.urls.split(","):
            url = url.strip()
            leads_a_analizar.append({"nombre": url, "url": url, "ciudad": ""})
    else:
        print("❌ Necesitás --input o --urls")
        sys.exit(1)

    # Limitar
    leads_a_analizar = leads_a_analizar[:args.limit]
    print(f"\n🚀 Analizando {len(leads_a_analizar)} sitios...\n{'─'*50}")

    resultados = []
    for lead in leads_a_analizar:
        r = analizar_sitio(lead["nombre"], lead["url"], lead.get("ciudad", ""))
        resultados.append(r)
        time.sleep(DELAY_ENTRE_REQUESTS)

    # Resumen final
    accesibles = [r for r in resultados if r.get("accesible")]
    con_ads    = [r for r in accesibles if r.get("google_ads_detectado")]
    oportunidades = sorted(accesibles, key=lambda x: x.get("score_calidad", 10))

    print(f"\n{'═'*50}")
    print(f"📊 RESUMEN FINAL")
    print(f"{'═'*50}")
    print(f"  Sitios analizados : {len(leads_a_analizar)}")
    print(f"  Accesibles        : {len(accesibles)}")
    print(f"  Con Google Ads    : {len(con_ads)} 🎯")
    print(f"\n  🔥 TOP OPORTUNIDADES (score más bajo = más para mejorar):")
    for r in oportunidades[:5]:
        ads_tag = " 🎯 ADS" if r.get("google_ads_detectado") else ""
        print(f"     [{r['score_calidad']}/10]{ads_tag} {r['empresa']} — {r['url']}")

    exportar_resultados(resultados, args.rubro)


if __name__ == "__main__":
    main()
