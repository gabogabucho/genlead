# LeadGen — Gabriel Urrutia

Sistema semi-automatizado para encontrar negocios en rubros "no cool" que invierten en Google Ads y tienen oportunidades de mejora claras.

## Flujo completo

```
1. Scraping        →  scrapers/google_places_scraper.py
2. Revisión manual →  Abrís el CSV, marcás los que tienen Ads visibles
3. Búsqueda emails →  Manual (web del negocio) o hunter.io
4. Exportar Brevo  →  utils/brevo_export.py
5. Campaña Brevo   →  Importás el CSV, usás template de portones
```

## Setup inicial

```bash
pip install requests
```

Editá `config/settings.py` y poné tu API key de Google Places.

## Correr el scraper

```bash
# Rubro completo, todas las ciudades configuradas
python scrapers/google_places_scraper.py --rubro portones_automaticos

# Solo Buenos Aires y Córdoba
python scrapers/google_places_scraper.py --rubro portones_automaticos --ciudades "Buenos Aires,Córdoba"
```

El CSV queda en `leads/portones_automaticos/leads_YYYYMMDD_HHMM.csv`

## Preparar para Brevo

```bash
python utils/brevo_export.py --input leads/portones_automaticos/leads_20240313_1000.csv --rubro portones_automaticos
```

Genera:
- `exports/portones_automaticos/brevo_listos_FECHA.csv` → importar directo en Brevo
- `exports/portones_automaticos/pendientes_email_FECHA.csv` → completar emails primero

## Agregar un rubro nuevo

En `config/settings.py`, dentro de `RUBROS`, copiá el bloque de `portones_automaticos` y:
1. Cambiá el slug (ej: `plomeros`)
2. Actualizá `queries` con términos de búsqueda del rubro
3. Creá la plantilla en `templates/plomeros_email.html`

## Variables en templates Brevo

| Variable         | Qué es                        |
|-----------------|-------------------------------|
| `{{FIRSTNAME}}`  | Nombre del negocio            |
| `{{COMPANY}}`    | Nombre del negocio (igual)    |
| `{{unsubscribe}}`| Link de baja (Brevo automático)|

## Estructura de carpetas

```
LeadGen_GabrielUrrutia/
├── config/
│   └── settings.py          ← API keys, ciudades, rubros
├── scrapers/
│   └── google_places_scraper.py
├── templates/
│   └── portones_email.html  ← Template HTML para Brevo
├── leads/
│   └── portones_automaticos/
│       └── leads_FECHA.csv
├── utils/
│   └── brevo_export.py
├── exports/
│   └── portones_automaticos/
│       ├── brevo_listos_FECHA.csv
│       └── pendientes_email_FECHA.csv
└── README.md
```
