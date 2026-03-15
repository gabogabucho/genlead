# Deploy en VPS — LeadGen Gabriel Urrutia
**Fecha:** 2026-03-15 | Ejecutar en orden, una fase a la vez.

---

## FASE A — Diagnóstico inicial

```bash
# 1. Ver cómo corre Flask actualmente
systemctl status leadgen 2>/dev/null || \
systemctl status flask 2>/dev/null || \
ps aux | grep -E "gunicorn|flask|python" | grep -v grep

# 2. Encontrar el directorio del proyecto
find /home /root /opt /srv -name "app.py" -path "*/dashboard/*" 2>/dev/null | head -5

# 3. Ver el .env actual
cat $(find /home /root /opt /srv -name ".env" -path "*/LeadGen*" 2>/dev/null | head -1)

# 4. Verificar Docker
docker --version 2>/dev/null && echo "✓ Docker OK" || echo "✗ Docker NO instalado"

# 5. Verificar Python y pip
python3 --version && pip3 --version
```

---

## FASE B — Actualizar código

```bash
# Ir al directorio del proyecto (reemplazar <DIR> con lo que encontró la Fase A)
cd <DIR>

# Hacer backup del .env actual por si acaso
cp .env .env.backup.$(date +%Y%m%d)

# Traer los últimos cambios
git pull origin main   # o: git pull origin master
git log --oneline -5   # verificar que trajo cambios nuevos
```

---

## FASE C — Instalar dependencias Python

```bash
# Opción A — si usan pip global
pip3 install apscheduler==3.10.4 requests python-dotenv "anthropic>=0.40.0"

# Opción B — si usan virtualenv
source venv/bin/activate
pip install -r dashboard/requirements.txt

# Verificar
python3 -c "import apscheduler; print('✓ apscheduler OK')"
python3 -c "import anthropic; print('✓ anthropic OK')"
```

---

## FASE D — Actualizar .env

```bash
# Agregar las nuevas variables al .env (sin borrar las existentes)
cat >> .env << 'EOF'

# ── Evolution API (WhatsApp) ──────────────────
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=leadgen_evo_2026_cambiar_esto
EVOLUTION_INSTANCE_NAME=vendedor

# ── Notificaciones ────────────────────────────
GABRIEL_EMAIL=gabriel@gabrielurrutia.com.ar
BACK_URL_BASE=https://gabrielurrutia.com.ar

# ── Test WhatsApp ─────────────────────────────
TEST_PHONE=549XXXXXXXXXX
EOF

# Verificar que quedó bien
tail -15 .env
```

> ⚠️ **Cambiar `leadgen_evo_2026_cambiar_esto`** por una clave segura (ej: generada con `openssl rand -hex 20`)
> ⚠️ **Cambiar `TEST_PHONE`** por tu número en formato 549XXXXXXXXXX

---

## FASE E — Instalar Docker (si no está)

```bash
# Verificar si ya está
docker --version && echo "Ya instalado, saltar esta fase" && exit 0

# Instalar
curl -fsSL https://get.docker.com | sh

# Agregar usuario al grupo docker (para no usar sudo)
sudo usermod -aG docker $USER
newgrp docker

# Verificar
docker run hello-world
```

---

## FASE F — Levantar Evolution API

```bash
# Obtener la API key del .env
EVOLUTION_KEY=$(grep EVOLUTION_API_KEY .env | cut -d'=' -f2)
echo "Usando key: $EVOLUTION_KEY"

# Crear y arrancar el contenedor
docker run -d \
  --name evolution-api \
  --restart always \
  -p 8080:8080 \
  -e AUTHENTICATION_API_KEY="$EVOLUTION_KEY" \
  -e QRCODE_LIMIT=30 \
  -v evolution_data:/evolution/instances \
  atendai/evolution-api:latest

# Esperar 10 segundos y ver los logs
sleep 10
docker logs evolution-api --tail 30

# Verificar que responde
curl -s http://localhost:8080 | head -5
```

---

## FASE G — Tunnel SSH para configurar Evolution API desde tu PC

> **El VPS no tiene browser.** Hay que hacer un tunnel SSH para acceder al panel de Evolution API
> desde tu computadora local y escanear el QR.

**Desde tu terminal LOCAL (no en el VPS):**

```bash
# Reemplazar <IP_VPS> con la IP de tu servidor
ssh -L 8080:localhost:8080 usuario@<IP_VPS> -N
```

Mientras ese comando esté corriendo (no cierra), abrís en tu browser local:

```
http://localhost:8080/manager
```

**Pasos en el panel de Evolution API:**

1. Autenticarse con la `EVOLUTION_API_KEY` del .env
2. Hacer click en **"New Instance"** → nombre: `vendedor`
3. Aparece el QR → **escanearlo con el WhatsApp del número vendedor**
4. Esperar que diga "Connected"
5. Ir a **Webhooks** de la instancia `vendedor`
6. Configurar:
   - URL: `http://localhost:5000/api/whatsapp/webhook`
   - Eventos: activar **`MESSAGES_UPSERT`** (los demás pueden quedar desactivados)
   - Guardar
7. Cerrar el tunnel SSH (Ctrl+C en la terminal local)

---

## FASE H — Reiniciar Flask

```bash
# Opción A — si es systemd:
sudo systemctl restart leadgen
sudo systemctl status leadgen

# Opción B — si es gunicorn en screen/tmux:
# Encontrar el proceso
ps aux | grep gunicorn | grep -v grep
# Matar y relanzar
kill <PID>
cd <DIR>/dashboard && gunicorn -w 1 -b 0.0.0.0:5000 app:app --daemon

# Verificar que Flask arrancó y las migraciones corrieron
sleep 3
curl -s http://localhost:5000/api/stats | python3 -m json.tool | head -10
```

---

## FASE I — Test de integración WhatsApp

```bash
cd <DIR>

# Poner tu número en TEST_PHONE si no lo pusiste en la Fase D
export TEST_PHONE=549XXXXXXXXXX

# Correr el test
python3 tests/test_whatsapp_sender.py
```

Resultado esperado:
```
=== Test normalización de teléfonos ===
  '011-4123-4567'    → '5491141234567'   ✓
  '+54 9 11 4123 4567' → '5491141234567' ✓
  ...

=== Test de envío real a 549XXXXXXXXXX ===
[WA Sender] Mensaje enviado a 549XXXXXXXXXX. ID: xxxx
✓ Envío exitoso!
```

---

## FASE J — Test del bot (respuesta automática)

```bash
# Desde otro teléfono, enviar un WhatsApp al número vendedor con:
#   "cuánto sale"
# → El bot debería responder automáticamente en segundos

# Ver el log de Flask para confirmar
journalctl -u leadgen -f --no-pager | grep -E "WA Bot|WA Sender|PostProcessor"
# o si es gunicorn en background:
tail -f /tmp/gunicorn.log 2>/dev/null || tail -f <DIR>/dashboard/app.log 2>/dev/null
```

---

## FASE K — Verificar en el dashboard

1. Abrir `https://<dominio-del-vps>` en el browser
2. Buscar un lead con status `whatsapp_enviado`
3. Abrir el lead → Tab **💬 WA**
4. Verificar que se ven las burbujas de conversación
5. Probar enviar un mensaje manual desde el dashboard

---

## Comandos útiles post-deploy

```bash
# Ver logs de Evolution API en tiempo real
docker logs evolution-api -f

# Ver si la instancia WA sigue conectada
curl -s -H "apikey: $EVOLUTION_KEY" \
  http://localhost:8080/instance/fetchInstances | python3 -m json.tool

# Reiniciar Evolution API (si se desconecta el QR)
docker restart evolution-api

# Ver espacio en disco
df -h

# Ver RAM usada
free -h

# Ver logs de Flask
journalctl -u leadgen -n 50 --no-pager
```

---

## Notas importantes

| Tema | Detalle |
|------|---------|
| **nic.ar** | Solo Gabriel puede hacerlo manualmente. Al pagar → email automático con el dominio sugerido |
| **MP en producción** | Cambiar `MP_ACCESS_TOKEN` de TEST a token real antes de cobrar |
| **QR de WA** | Si se desconecta, hacer tunnel SSH de nuevo y re-escanear en el panel |
| **Número dedicado** | Usar un número de WhatsApp solo para el bot, no el personal |
| **Servicio 2 (Premium)** | No implementado, segunda etapa |
