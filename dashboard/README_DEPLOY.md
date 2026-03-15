# Deploy en Railway — LeadGen Dashboard

## En 5 minutos tenés el dashboard online

---

### Paso 1 — Subir a GitHub
```bash
cd LeadGen_GabrielUrrutia/dashboard
git init
git add .
git commit -m "LeadGen dashboard v1"
# Crear repo en github.com/new, luego:
git remote add origin https://github.com/TU_USUARIO/leadgen-dashboard
git push -u origin main
```

---

### Paso 2 — Crear proyecto en Railway
1. Ir a [railway.app](https://railway.app) → **New Project**
2. Elegir **Deploy from GitHub repo**
3. Seleccionar `leadgen-dashboard`
4. Railway detecta el `Procfile` automáticamente → Deploy automático

---

### Paso 3 — Agregar volumen persistente (para SQLite)
En el proyecto Railway:
1. Click en el servicio → **Add Volume**
2. Mount path: `/data`

Esto asegura que la DB **sobrevive a cada deploy**.

---

### Paso 4 — Variables de entorno
En el servicio → **Variables** → agregar:

| Variable              | Valor                              |
|-----------------------|------------------------------------|
| `API_SECRET`          | Clave larga y secreta (ej: `gab-leadgen-secret-2024-xxxxx`) |
| `DATABASE_PATH`       | `/data/leadgen.db`                 |
| `MP_WEBHOOK_SECRET`   | (lo obtenés al configurar el webhook en MP) |

---

### Paso 5 — (Opcional) Dominio personalizado
En el servicio → **Settings** → **Networking** → **Add custom domain**

Sugerido: `leads.gabrielurrutia.com.ar`

Apuntá el CNAME en Cloudflare DNS al dominio que te da Railway.

---

### Paso 6 — Configurar webhook de MercadoPago
En tu cuenta de MP → [Webhooks](https://www.mercadopago.com.ar/developers/panel/webhooks):
- URL: `https://TU-APP.railway.app/api/mp/webhook`
- Eventos: `payment`

---

## Conectar el pipeline al dashboard

El pipeline (CrewAI) necesita estas dos variables de entorno:

```bash
DASHBOARD_URL=https://TU-APP.railway.app
DASHBOARD_SECRET=<mismo API_SECRET de arriba>
```

Con eso el pipeline puede crear leads y actualizarlos via REST:

```python
# Ejemplo desde el pipeline
import requests

headers = {"X-API-Secret": os.environ["DASHBOARD_SECRET"]}
requests.post(f"{DASHBOARD_URL}/api/leads", json={...}, headers=headers)
```

---

## Correr localmente para desarrollo

```bash
pip install -r requirements.txt
DATABASE_PATH=./dev.db API_SECRET=dev python3 app.py
# → http://localhost:5000
```

---

## Resumen de endpoints

| Método | Endpoint                              | Descripción                        |
|--------|---------------------------------------|------------------------------------|
| GET    | `/`                                   | Dashboard UI                       |
| GET    | `/api/stats`                          | KPIs y totales                     |
| GET    | `/api/rubros`                         | Lista de rubros                    |
| GET    | `/api/leads`                          | Lista de leads (filtrable)         |
| POST   | `/api/leads`                          | Crear lead (requiere API_SECRET)   |
| PATCH  | `/api/leads/:id`                      | Actualizar lead                    |
| GET    | `/api/leads/:id/activities`           | Timeline del lead                  |
| POST   | `/api/leads/:id/activities`           | Agregar actividad                  |
| POST   | `/api/leads/:id/dominio`              | Confirmar compra de dominio        |
| POST   | `/api/mp/webhook`                     | Webhook de MercadoPago             |
| GET    | `/api/runs`                           | Historial de pipeline runs         |
