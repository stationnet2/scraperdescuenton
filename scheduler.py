"""
scheduler.py — Corre el scraper automáticamente cada 24 horas
Deployar en Railway como servicio siempre activo
Controlado por variable de entorno RUN_SCHEDULER
"""
import asyncio
import os
from scraper import main as run_scraper

INTERVALO_HORAS = 24

async def loop():
    while True:
        print(f'\n🕐 Ejecutando scraper...')
        try:
            await run_scraper()
        except Exception as e:
            print(f'❌ Error en el scraper: {e}')
        
        print(f'💤 Esperando {INTERVALO_HORAS} horas hasta la próxima ejecución...')
        await asyncio.sleep(INTERVALO_HORAS * 3600)

if __name__ == '__main__':
    run_flag = os.getenv("RUN_SCHEDULER", "false").lower()
    if run_flag == "true":
        asyncio.run(loop())
    else:
        print("⏸️ Scheduler pausado por configuración (RUN_SCHEDULER=false).")
