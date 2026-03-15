import os
from dotenv import load_dotenv

# Cargar .env del root y fallback en config/.env si existe
project_root = os.path.dirname(os.path.dirname(__file__))
load_dotenv(os.path.join(project_root, ".env"), override=True)
load_dotenv(os.path.join(project_root, "config", ".env"), override=True)

from crewai import Crew, Process
try:
    from .agents import create_lead_analyst, create_landing_developer, create_sales_closer
    from .tasks import task_analyze_and_qualify, task_generate_landing, task_finalize_assets
except Exception:
    from agents import create_lead_analyst, create_landing_developer, create_sales_closer
    from tasks import task_analyze_and_qualify, task_generate_landing, task_finalize_assets

def run_leadgen_crew():
    print("🚀 Inicializando LeadGen AI Crew...")
    
    # Init Agents
    analyst = create_lead_analyst()
    developer = create_landing_developer()
    closer = create_sales_closer()
    
    # Init Tasks
    t_analyze = task_analyze_and_qualify(analyst)
    t_landing = task_generate_landing(developer)
    t_close = task_finalize_assets(closer)
    
    # Create Crew
    lead_crew = Crew(
        agents=[analyst, developer, closer],
        tasks=[t_analyze, t_landing, t_close],
        process=Process.sequential,
        verbose=True
    )
    
    print("\n[🎯] Arrancando ejecución de CrewAI...")
    resultado = lead_crew.kickoff()
    
    print("\n==============================================")
    print("✅ EJECUCIÓN DEL CREW COMPLETADA")
    print("==============================================")
    print(resultado)
    return resultado

if __name__ == "__main__":
    run_leadgen_crew()

