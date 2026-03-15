# ============================================================
#  LeadGen - Gabriel Urrutia
#  Configuración central del proyecto
# ============================================================

# --- API Keys ---
GOOGLE_PLACES_API_KEY = "AIzaSyCl5H7jxtF4_hzvJHLlsTHZ-IJrC-DBmUY"  # Reemplazar

# --- Ciudades objetivo (Argentina) ---
# Podés agregar o quitar ciudades según el rubro
CIUDADES_ARG = [
    "Buenos Aires, Argentina",
    "Córdoba, Argentina",
    "Rosario, Argentina",
    "Mendoza, Argentina",
    "La Plata, Argentina",
    "Mar del Plata, Argentina",
    "San Miguel de Tucumán, Argentina",
    "Salta, Argentina",
]

# --- Rubros disponibles ---
# Cada rubro tiene: slug, query de búsqueda, y keywords de dolor para el email
RUBROS = {
    "portones_automaticos": {
        "nombre": "Portones Automáticos",
        "queries": [
            "portones automáticos",
            "automatización de portones",
            "motores para portones",
            "portones corredizos automáticos",
        ],
        "template_email": "templates/portones_email.html",
    },
    "barberias": {
        "nombre": "Barberías",
        "queries": [
            "barbería",
            "barberias",
            "barber shop",
            "corte de pelo hombre",
        ],
        "template_email": "templates/portones_email.html",
    },
    "veterinarias": {
        "nombre": "Veterinarias",
        "queries": [
            "veterinaria",
            "veterinario",
            "clínica veterinaria",
            "hospital veterinario",
        ],
        "template_email": "templates/portones_email.html",
    },
    "consultorios_medicos": {
        "nombre": "Consultorios Médicos",
        "queries": [
            "consultorio médico",
            "médico clínico",
            "médico de cabecera",
            "consultorios odontológicos",
            "odontólogo",
        ],
        "template_email": "templates/portones_email.html",
    },
    "estudios_juridicos": {
        "nombre": "Estudios Jurídicos / Abogados",
        "queries": [
            "estudio jurídico",
            "abogados",
            "abogado",
            "estudio de abogados",
            "asesoría legal",
        ],
        "template_email": "templates/portones_email.html",
    },
    "peluquerias": {
        "nombre": "Peluquerías",
        "queries": [
            "peluquería",
            "peluqueria femenina",
            "estilista",
            "salón de belleza",
        ],
        "template_email": "templates/portones_email.html",
    },
    "esteticas_spa": {
        "nombre": "Estéticas y Spa",
        "queries": [
            "estética",
            "spa",
            "centro de estética",
            "depilación",
            "masajes",
        ],
        "template_email": "templates/portones_email.html",
    },
    "plantas_decorativas": {
        "nombre": "Plantas Decorativas",
        "queries": [
            "plantas decorativas",
            "vivero",
            "floristería",
            "jardinería",
            "vivero de plantas",
        ],
        "template_email": "templates/portones_email.html",
    },
    "tiendas_autor": {
        "nombre": "Tiendas de Autor / Indumentaria",
        "queries": [
            "tienda de ropa",
            "boutique",
            "indumentaria",
            "ropa de diseño",
            "tienda de diseñador",
        ],
        "template_email": "templates/portones_email.html",
    },
}

# --- Scraping ---
MAX_RESULTS_POR_QUERY = 20       # Google Places devuelve máx 20 por página
DELAY_ENTRE_REQUESTS = 1.5       # segundos (para no quemar la API)
RADIO_BUSQUEDA_METROS = 50000    # 50 km radio por ciudad

# --- Exportación Brevo ---
# Columnas que Brevo espera para importar contactos
BREVO_COLUMNS = [
    "EMAIL",
    "FIRSTNAME",   # Usaremos nombre del negocio
    "LASTNAME",
    "COMPANY",
    "PHONE",
    "WEBSITE",
    "CIUDAD",
    "RUBRO",
    "TIENE_WEBSITE",    # Sí/No — útil para filtrar en Brevo
    "GOOGLE_MAPS_URL",
    "NOTAS",
]
