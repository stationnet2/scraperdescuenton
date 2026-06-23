"""
scheduler.py — Corre el scraper automáticamente cada 24 horas
Deployar en Railway como servicio siempre activo
"""
import asyncio
import time
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
    asyncio.run(loop())
