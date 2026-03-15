# PLAN DE TRABAJO — LeadGen Automatizado
**Proyecto:** Sistema de ventas automatizado para Gabriel Urrutia
**Objetivo final:** Pipeline completo funcionando end-to-end:
Scouting → Análisis → Calificación → Landing → Deploy Cloudflare → Pitch Email → Seguimiento MP

> **Para Claude Code:** Ejecutá cada fase en orden. No avances a la siguiente hasta que los tests de la fase actual pasen. Ante cualquier duda de diseño, preguntá antes de implementar.

---

## CONTEXTO ARQUITECTÓNICO

```
LeadGen_GabrielUrrutia/
├── config/settings.py          ← API keys, rubros, ciudades
├── scrapers/
│   ├── google_places_scraper.py  ← FUNCIONA - no tocar
│   ├── site_analyzer.py          ← FUNCIONA - no tocar
│   ├── email_generator.py        ← FUNCIONA - no tocar
│   └── whatsapp_generator.py     ← FUNCIONA - no tocar
├── crew/
│   ├── agents.py                 ← BUG CRÍTICO - fase 1
│   ├── tasks.py                  ← FUNCIONA
│   ├── tools.py                  ← FUNCIONA
│   └── main.py                   ← FUNCIONA
├── utils/
│   ├── pipeline_runner.py        ← FUNCIONA
│   ├── agent_runner.py           ← FUNCIONA
│   ├── email_sender.py           ← FUNCIONA (falta Brevo key real)
│   ├── mercadopago_integration.py← FUNCIONA (falta MP token real)
│   └── cloudflare_deployer.py    ← NO EXISTE - crear en fase 3
├── dashboard/
│   ├── app.py                    ← FUNCIONA + fix webhook MP - fase 2
│   ├── schema.sql                ← FUNCIONA
│   └── templates/index.html     ← Agregar botón agente - fase 4
└── .env                          ← Faltan BREVO_API_KEY y MP_ACCESS_TOKEN reales
```

**Stack:** Python 3.10+, Flask, SQLite, CrewAI, Claude API (Anthropic), Cloudflare Pages API, Brevo API, MercadoPago API
**DB:** `dashboard/leadgen.db` (SQLite)
**VPS:** deployado manualmente — el dashboard corre en producción

---

## FASE 1 — Bugs críticos (hacer primero, bloquean todo lo demás)

### 1.1 Fix NameError en `crew/agents.py`

**Problema:** `create_sales_closer()` en la línea ~65 referencia `send_email_wrapper_tool_if_needed` antes de que esa función esté definida (se define en la línea ~77). Produce `NameError` al importar el módulo — el crew no puede arrancar.

**Solución:** Mover la definición de `send_email_wrapper_tool_if_needed` (y su import de `send_email`) al inicio del archivo, antes de las funciones `create_*`.

**Archivo:** `crew/agents.py`

**Validación:**
```bash
cd /ruta/al/proyecto
python -c "from crew.agents import create_lead_analyst, create_landing_developer, create_sales_closer; print('OK')"
```
Debe imprimir `OK` sin errores.

---

### 1.2 Fix WAL mode en SQLite

**Problema:** Dashboard Flask y CrewAI comparten el mismo `leadgen.db`. Si corren simultáneamente (el dashboard está siempre up en VPS), SQLite puede dar `database is locked`.

**Solución:** En `dashboard/app.py`, dentro de `get_db()`, agregar `db.execute("PRAGMA journal_mode=WAL")` justo después de crear la conexión.

**Archivo:** `dashboard/app.py`, función `get_db()`

**También:** Hacer lo mismo en `crew/tools.py`, función `get_db_connection()`.

**Validación:** Correr el crew mientras el dashboard está activo y verificar que no hay errores de lock.

---

### 1.3 Fix webhook de MercadoPago en `dashboard/app.py`

**Problema:** El endpoint `/api/mp/webhook` recibe un `payment_id` nuevo de MP y busca ese ID en la DB. Pero ese ID nunca fue guardado previamente (es el primer contacto), entonces siempre falla con "pago sin lead asociado".

**La lógica correcta es:**
1. Recibir el `payment_id` del webhook de MP
2. Llamar a `GET https://api.mercadopago.com/v1/payments/{payment_id}` con `Authorization: Bearer {MP_ACCESS_TOKEN}`
3. Extraer `external_reference` de la respuesta (ese valor es el `lead_id` que se guardó al crear la preferencia en `mercadopago_integration.py`)
4. Buscar el lead por `id = external_reference`
5. Actualizar el lead con status `pagado` y guardar el `payment_id`

**Archivo:** `dashboard/app.py`, función `mp_webhook()`

**Variables de entorno necesarias:** `MP_ACCESS_TOKEN` (ya está en `.env`, falta el valor real)

**Validación:** Simular un webhook con curl:
```bash
curl -X POST http://localhost:5000/api/mp/webhook \
  -H "Content-Type: application/json" \
  -d '{"type":"payment","data":{"id":"TEST_PAYMENT_ID"}}'
```
Debe responder `{"ok": true}` sin errores en el log. En producción, MP confirmará el pago real.

---

## FASE 2 — Cloudflare Pages Deployer (crear desde cero)

**Descripción:** Cuando el crew genera una landing (`landing_html` en la DB), Gabriel compra el dominio en NIC.ar y lo ingresa en el dashboard. Ese evento debe disparar el deploy automático en Cloudflare Pages.

**Crear archivo:** `utils/cloudflare_deployer.py`

### Lógica del deployer

El flujo completo es:

```
lead tiene landing_html en DB
  → Gabriel ingresa dominio en dashboard (POST /api/leads/<id>/dominio)
  → app.py llama a cloudflare_deployer.deploy_landing(lead_id, dominio)
  → deployer crea/actualiza el proyecto en CF Pages
  → deployer sube el HTML como deployment
  → deployer configura el dominio custom
  → deployer actualiza el lead con landing_url y landing_url_live=1
```

### Variables de entorno a agregar al `.env`

```bash
CF_API_TOKEN=           # Cloudflare API Token con permisos: Cloudflare Pages:Edit
CF_ACCOUNT_ID=          # Account ID (se ve en el dashboard de CF, esquina derecha)
CF_PAGES_PROJECT_PREFIX=leadgen-  # Los proyectos se llamarán leadgen-{lead_id}
```

### Implementación de `utils/cloudflare_deployer.py`

La función principal debe ser:

```python
def deploy_landing(lead_id: int, dominio: str, html_content: str) -> dict:
    """
    Despliega un HTML en Cloudflare Pages y configura el dominio custom.
    Retorna {"url": str, "deployment_id": str, "ok": bool}
    """
```

**Pasos internos:**

1. **Crear o verificar que existe el proyecto en CF Pages**
   - `GET https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/pages/projects/{project_name}`
   - Si no existe (404): `POST` para crearlo con `production_branch: "main"`
   - El `project_name` será `{CF_PAGES_PROJECT_PREFIX}{lead_id}` (ej: `leadgen-42`)

2. **Subir el HTML como deployment directo**
   - CF Pages acepta deployments via `POST /accounts/{id}/pages/projects/{name}/deployments`
   - El body debe ser `multipart/form-data` con un archivo `_worker.js` vacío (requerido por CF) y el `index.html` con el contenido de la landing
   - CF genera automáticamente una URL tipo `{project_name}.pages.dev`

3. **Configurar dominio custom** (solo si el dominio es distinto de `.pages.dev`)
   - `POST /accounts/{CF_ACCOUNT_ID}/pages/projects/{project_name}/domains`
   - Body: `{"name": dominio}` (ej: `portonessur.com.ar`)
   - CF devuelve el status de verificación del dominio

4. **Actualizar el lead en la DB**
   - `landing_url`: la URL de pages.dev como preview inmediata
   - `landing_url_live`: 1 cuando el dominio custom esté activo
   - `dominio_status`: `'configurado'`

**Manejo de errores:**
- Si CF devuelve error, loguear y retornar `{"ok": False, "error": "..."}`
- No romper el flujo del dashboard por un error de CF — el dashboard debe informar pero no crashear

### Conectar el deployer con `dashboard/app.py`

En la función `confirmar_dominio()` (endpoint `POST /api/leads/<id>/dominio`), reemplazar el `TODO (Fase B)` con la llamada real:

```python
# Obtener el landing_html del lead
lead = db.execute("SELECT landing_html FROM leads WHERE id=?", [lead_id]).fetchone()
if lead and lead["landing_html"]:
    resultado = deploy_landing(lead_id, dominio, lead["landing_html"])
    if resultado.get("ok"):
        db.execute("UPDATE leads SET landing_url=?, dominio_status='configurado' WHERE id=?",
                   [resultado["url"], lead_id])
```

**Validación:**
```bash
# Con un lead que tenga landing_html en la DB:
curl -X POST http://localhost:5000/api/leads/1/dominio \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: dev-secret-change-me" \
  -d '{"dominio": "test-portones.pages.dev"}'
# Debe retornar {"ok": true, "dominio": "...", "landing_url": "https://...pages.dev"}
```

---

## FASE 3 — Integrar crew con dashboard (botón "Ejecutar Agente")

**Descripción:** El dashboard ya tiene el endpoint `POST /api/leads/<id>/run_agent` pero el `index.html` no tiene el botón visible para llamarlo.

**Verificar primero:** Buscar en `dashboard/templates/index.html` si ya existe algún botón o acción "run agent" / "ejecutar agente". Leer el HTML completo para no duplicar.

### Si NO existe el botón, agregar en la tabla de leads

En la columna "Acciones" de la tabla (dentro del `<template x-for="lead in leads">`), agregar:

```html
<!-- Botón ejecutar agente (solo si status es 'nuevo' o 'analizado') -->
<template x-if="['nuevo','analizado'].includes(lead.status)">
  <button @click.stop="runAgent(lead.id)"
          :disabled="agentRunning[lead.id]"
          class="text-xs px-2 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 disabled:opacity-50 transition">
    <span x-text="agentRunning[lead.id] ? '⏳' : '🤖'"></span>
  </button>
</template>
```

### Agregar la función `runAgent()` en el Alpine.js app()

```javascript
agentRunning: {},

async runAgent(leadId) {
  this.agentRunning[leadId] = true;
  try {
    const r = await fetch(`/api/leads/${leadId}/run_agent`, {
      method: 'POST',
      headers: {'X-API-Secret': 'dev-secret-change-me'}
    });
    const data = await r.json();
    if (data.ok) {
      alert('Agente iniciado en background. Actualizá en unos minutos.');
    } else {
      alert('Error: ' + (data.error || 'desconocido'));
    }
  } catch(e) {
    alert('Error de conexión');
  } finally {
    this.agentRunning[leadId] = false;
    this.loadLeads();
  }
}
```

### Verificar el endpoint en `dashboard/app.py`

El endpoint `POST /api/leads/<id>/run_agent` debe:
1. Llamar a `agent_runner.run_agent_for_lead(lead_id)` en un thread separado (para no bloquear el request HTTP)
2. Retornar `{"ok": true}` inmediatamente

Si actualmente es síncrono (bloquea el request), cambiarlo a threading:

```python
import threading

@app.route("/api/leads/<int:lead_id>/run_agent", methods=["POST"])
def run_agent(lead_id):
    err = require_secret(request)
    if err: return err

    def _run():
        from utils.agent_runner import run_agent_for_lead
        run_agent_for_lead(lead_id)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({"ok": True, "message": f"Agente iniciado para lead {lead_id}"})
```

**Validación:**
```bash
curl -X POST http://localhost:5000/api/leads/1/run_agent \
  -H "X-API-Secret: dev-secret-change-me"
# Debe responder inmediatamente con {"ok": true}
# En los logs del servidor, se debe ver CrewAI arrancando en background
```

---

## FASE 4 — Preview de landing en el dashboard

**Descripción:** Cuando el lead tiene `landing_html` en la DB, mostrar un botón "Ver Preview" que abra el HTML en un modal o nueva pestaña.

**Agregar endpoint en `dashboard/app.py`:**

```python
@app.route("/api/leads/<int:lead_id>/landing_preview")
def landing_preview(lead_id):
    db = get_db()
    lead = db.execute("SELECT landing_html FROM leads WHERE id=?", [lead_id]).fetchone()
    if not lead or not lead["landing_html"]:
        return "Sin landing generada", 404
    return lead["landing_html"], 200, {"Content-Type": "text/html; charset=utf-8"}
```

**En el panel de detalle del lead** (el drawer/modal que abre al hacer click en un lead en `index.html`), agregar:

```html
<template x-if="selectedLead?.landing_html">
  <a :href="'/api/leads/' + selectedLead.id + '/landing_preview'"
     target="_blank"
     class="flex items-center gap-1.5 text-xs text-purple-600 hover:text-purple-800">
    🖥 Ver preview de landing
  </a>
</template>
```

---

## FASE 5 — Tests de integración end-to-end

Una vez completadas las fases anteriores, ejecutar el flujo completo con datos reales:

### Test 1: Scouting
```bash
cd /ruta/al/proyecto
python utils/pipeline_runner.py  # O via dashboard: POST /api/runs
# Verificar que aparecen leads en status 'nuevo' en el dashboard
```

### Test 2: Crew para un lead
```bash
LEAD_ID=1 python crew/main.py
# Verificar en la DB:
#   - status cambia a 'landing_lista'
#   - landing_html tiene contenido
#   - email_html tiene contenido
#   - mp_payment_link tiene URL de MP
```

### Test 3: Cloudflare deploy
```bash
curl -X POST http://localhost:5000/api/leads/1/dominio \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: {API_SECRET}" \
  -d '{"dominio": "test.pages.dev"}'
# Verificar que landing_url se actualiza en el lead
```

### Test 4: Email pitch
```bash
# Via dashboard: cambiar status a 'enviado' y verificar que
# el email_html + email_asunto están guardados en el lead
```

### Test 5: Webhook MP (sandbox)
```bash
# Crear una preferencia de pago de prueba, completar el pago en sandbox de MP
# Verificar que el webhook cambia status a 'pagado'
```

---

## VARIABLES DE ENTORNO REQUERIDAS

Todas van en el `.env` de la raíz del proyecto. Las que tienen valor real ya están; las que dicen `COMPLETAR` necesitan su valor:

```bash
# Ya configuradas
ANTHROPIC_API_KEY=sk-ant-...          # OK
APIFY_TOKEN=apify_api_...             # OK
SENDER_EMAIL=gabriel@gabrielurrutia.com.ar  # OK
VENDEDOR_EMAIL=gabriel@gabrielurrutia.com.ar # OK
DATABASE_PATH=dashboard/leadgen.db    # OK
API_SECRET=dev-secret-change-me       # Cambiar en producción

# COMPLETAR antes de poder usar el sistema
BREVO_API_KEY=                        # API key de Brevo (app.brevo.com → Settings → API Keys)
MP_ACCESS_TOKEN=                      # MP Access Token productivo (mercadopago.com.ar → Credenciales)
MP_WEBHOOK_URL=https://{VPS_URL}/api/mp/webhook  # URL pública del VPS

# COMPLETAR para Cloudflare (Fase 3)
CF_API_TOKEN=                         # CF Token con permiso Cloudflare Pages:Edit
CF_ACCOUNT_ID=                        # Account ID del panel de CF
CF_PAGES_PROJECT_PREFIX=leadgen-      # Prefijo para los proyectos en CF Pages
GOOGLE_PLACES_API_KEY=                # Si no está en config/settings.py
```

---

## ORDEN DE EJECUCIÓN RECOMENDADO

```
[ ] Fase 1.1 — Fix NameError agents.py
[ ] Fase 1.2 — WAL mode SQLite (app.py + tools.py)
[ ] Fase 1.3 — Fix webhook MP (app.py)
[ ] Fase 2   — Crear cloudflare_deployer.py + conectar con app.py
[ ] Fase 3   — Botón agente en dashboard + endpoint async
[ ] Fase 4   — Preview landing en dashboard
[ ] Fase 5   — Tests end-to-end (requiere API keys reales en .env)
```

**Criterio de "sistema funcionando":** Un lead entra como `nuevo`, el crew lo procesa, genera landing + email + link de pago, se sube la landing a CF Pages, se envía el email por Brevo, y cuando el cliente paga, el webhook de MP cambia el status a `pagado`. Todo visible y trackeable desde el dashboard.

---

## NOTAS TÉCNICAS PARA CLAUDE CODE

- **No modificar** los archivos en `scrapers/` — están funcionando y tienen lógica frágil de regex.
- **No cambiar** el modelo LLM en `agents.py` — actualmente usa `claude-3-5-sonnet-20240620`. Si lo cambiás, notificar a Gabriel antes.
- **El `.env` tiene credenciales reales de Anthropic y Apify** — no commitear, ya está en `.gitignore`.
- **La DB `dashboard/leadgen.db` puede tener datos reales** — no hacer `DROP TABLE` ni `DELETE FROM leads` sin confirmación explícita.
- **Cloudflare Pages tiene límites en el plan gratis:** 500 deployments/mes, proyectos ilimitados. Con el volumen esperado (decenas de leads/mes) no hay problema.
- **El `external_reference` en MP preference es el `lead_id` como string** — así está implementado en `mercadopago_integration.py`, no cambiar esa convención.
