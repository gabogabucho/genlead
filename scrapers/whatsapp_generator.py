def generar_whatsapp(analysis: dict, client) -> dict:
    """
    Genera un mensaje corto de WhatsApp para servicios basicos.
    Enfocado en beneficio y posicionamiento, sin venta dura ni precios.
    """
    empresa = analysis.get("empresa", "").strip()
    ciudad = analysis.get("ciudad", "").strip()
    rubro = analysis.get("rubro", "") or analysis.get("rubro_slug", "")
    dolores = analysis.get("dolores", "")
    titulo = analysis.get("titulo", "")
    bio = analysis.get("instagram_bio", "")

    prompt = f"""Redacta un mensaje de WhatsApp corto y directo para un negocio local.
Objetivo: invitar a ver una demo de landing y explicar como ayuda al negocio.
Reglas:
- Maximo 420 caracteres.
- NO mencionar precios, pagos ni condiciones.
- Enfocarse en mejoras concretas (presencia, posicionamiento, clientes).
- Si hay dolores, convertirlos en beneficios.

Datos:
Empresa: {empresa}
Ciudad: {ciudad}
Rubro: {rubro}
Dolores: {dolores}
Titulo web: {titulo}
Bio IG: {bio}

Devuelve SOLO el texto del mensaje, sin comillas ni etiquetas."""

    resp = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=240,
        temperature=0.5,
        messages=[{"role": "user", "content": prompt}],
    )

    text = ""
    for block in resp.content:
        if getattr(block, "type", "") == "text":
            text = block.text.strip()
            break
    return {"whatsapp_text": text}
