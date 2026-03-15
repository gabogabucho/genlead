from crewai import Task

def task_analyze_and_qualify(agent):
    return Task(
        description=(
            "1. Usa 'Fetch Pending Leads Tool' para obtener 1 lead pendiente.\n"
            "2. Extrae sus datos básicos (nombre, URL, ciudad).\n"
            "3. Ejecuta el 'Site Analyzer Tool' usando el nombre, URL y ciudad de ese lead.\n"
            "4. Evalúa los resultados devueltos:\n"
            "   - Si no tiene URL propia (web_propia false) o la Score es < 4 y NO tiene Ads, el tipo de servicio es 'simple'.\n"
            "   - Si la Score es < 8 pero SÍ tiene Ads, el tipo de servicio es 'pro'.\n"
            "   - Si la web es excelente (score 9-10) y tiene buen ecosistema, podría ser 'ninguno' (descartar).\n"
            "5. Construye un JSON string conteniendo la evaluación y la decisión, y usa 'Update Lead Database Tool' "
            "con los campos: 'status': 'analizado', 'tipo_servicio', 'score_calidad' (number), y 'dolores' (string).\n"
            "6. Devuelve al equipo final la información detallada del lead, incluyendo el ID del lead, el Dict de análisis y el 'tipo_servicio' final."
        ),
        expected_output="Un diccionario final consolidado con 'lead_id', 'empresa', 'url', 'tipo_servicio', y el resultado completo en 'analysis_json'.",
        agent=agent
    )

def task_generate_landing(agent):
    return Task(
        description=(
            "Basado en el resultado de la tarea anterior:\n"
            "1. Extrae el nombre de la empresa, el rubro y si aplica ('simple' o 'pro').\n"
            "   - Si 'tipo_servicio' es 'ninguno', no hagas nada y devuelve vacio.\n"
            "2. Escribe una Landing Page COMPLETA en HTML crudo (con `<!DOCTYPE html>`).\n"
            "3. Incluye `<script src=\"https://cdn.tailwindcss.com\"></script>` en el <head>.\n"
            "4. El diseno debe ser atractivo y usar datos reales del lead cuando esten disponibles, incluyendo colores de marca si aparecen en el analisis.\n"
            "   - Menciona empresa, rubro y ciudad.\n"
            "   - Si hay dolores detectados, conviertelos en beneficios o promesas.\n"
            "   - Si hay colores de marca en el analisis (brand_colors), usalos como paleta principal en Tailwind.\n"
            "   - Si hay instagram_bio, usalo para inspirar el slogan o subtitulo.\n"
            "   - Si hay instagram_images, incluilas como galeria o seccion visual.\n"
            "   - Si hay telefono o WhatsApp, agregalos como CTA principal.\n"
            "   - Incluye un Header (Logo texto), un Hero prominente, una seccion de 3 beneficios, testimonios simples, y un Footer.\n"
            "5. NO insertes bloques de markdown (```html) en la salida final. Necesitamos el HTML string absolutamente limpio."
        ),
        expected_output="Un string conteniendo UNICAMENTE codigo HTML valido e indentado para la landing, sin markdown blocks surrounding it.",
        agent=agent
    )

def task_finalize_assets(agent):
    return Task(
        description=(
            "Con la información recopilada de las tareas anteriores:\n"
            "1. Obtén el Link de Pago usando 'Generate Payment Link Tool' (pasale el ID del lead y su tipo_servicio).\n"
            "2. Genera el Email de Pitch invocando 'Generate Pitch Email Tool' usando el JSON de análisis de la primera tarea.\n"
            "3. Si el tipo_servicio es 'simple', genera un mensaje de WhatsApp con 'Generate WhatsApp Pitch Tool' usando el JSON de análisis.\n"
            "4. Recibe la Landing Page HTML de la segunda tarea.\n"
            "5. Manda todo a la base de datos armando un JSON para 'Update Lead Database Tool'. "
            "El JSON debe tener: 'landing_html': (tu html),\n 'email_asunto': (del pitch tool),\n 'email_html': (del pitch tool),\n 'mp_payment_link': (link),\n 'whatsapp_text': (si aplica),\n 'status': 'landing_lista'.\n"
            "6. Valida que el Update haya sido exitoso y retorna un resumen."
        ),
        expected_output="Resumen confirmando que todos los assets se crearon y se subieron a SQLite exitosamente.",
        agent=agent
    )







