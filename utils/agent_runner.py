import os
import logging
from typing import Any

from crew.main import run_leadgen_crew

logger = logging.getLogger(__name__)


def run_agent_for_lead(lead_id: int) -> Any:
    """
    Ejecuta el CrewAI para un lead puntual y luego dispara el post-procesamiento
    (deploy a CF Pages + envío de WhatsApp con el link de la demo).
    """
    os.environ["LEAD_ID"] = str(lead_id)
    try:
        result = run_leadgen_crew()
        # Post-procesar: deploy CF Pages → enviar WhatsApp
        try:
            from utils.post_processor import post_process_lead
            post_process_lead(lead_id)
        except Exception as e:
            logger.error(f"Error en post_process_lead para lead {lead_id}: {e}", exc_info=True)
        return result
    finally:
        os.environ.pop("LEAD_ID", None)
