"""
DescuMap — Scraper automático de promociones bancarias argentinas
Corre en Railway/Render, se ejecuta cada 24hs
Extrae promos de: Mercado Pago, Ualá, Naranja X, Banco Nación,
                  BBVA, Santander, Galicia, Cuenta DNI
Las sube automáticamente a Supabase como descuentos con estado 'pendiente'
para revisión del admin.
"""

import asyncio
import os
import json
import re
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from supabase import create_client, Client

# ── Config desde variables de entorno ────────────────────
SUPABASE_URL  = os.environ.get('SUPABASE_URL',  'https://TU-PROYECTO.supabase.co')
SUPABASE_KEY  = os.environ.get('SUPABASE_KEY',  'TU_SERVICE_ROLE_KEY')  # service_role, no anon
COMERCIO_BANCO_ID = os.environ.get('COMERCIO_BANCO_ID', '')  # ID del comercio "Banco Nación" en tu BD

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Categoría por defecto para promos bancarias ───────────
CATEGORIA_DEFAULT = 'supermercados'
FECHA_FIN_DEFAULT = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

# ════════════════════════════════════════════════════════════
# SCRAPERS POR ENTIDAD
# ════════════════════════════════════════════════════════════

async def scrape_mercadopago(page) -> list[dict]:
    """Scrapea beneficios de Mercado Pago"""
    promos = []
    try:
        await page.goto('https://www.mercadopago.com.ar/benefits', timeout=30000)
        await page.wait_for_selector('.benefits-card, [data-testid="benefit-card"], .benefit__title', timeout=15000)
        
        cards = await page.query_selector_all('.benefits-card, [class*="benefit"], [class*="promo"]')
        for card in cards[:20]:
            try:
                title = await card.inner_text()
                title = title.strip()[:200]
                if len(title) > 10 and any(c.isdigit() for c in title):
                    promos.append({
                        'titulo':      f'Mercado Pago: {title[:80]}',
                        'descripcion': title,
                        'wallets':     ['mercadopago'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(title),
                    })
            except:
                pass
    except Exception as e:
        print(f'MercadoPago scrape error: {e}')
    return promos

async def scrape_uala(page) -> list[dict]:
    """Scrapea beneficios de Ualá"""
    promos = []
    try:
        await page.goto('https://www.uala.com.ar/beneficios', timeout=30000)
        await page.wait_for_timeout(4000)
        
        cards = await page.query_selector_all('[class*="benefit"], [class*="promo"], [class*="card"]')
        for card in cards[:15]:
            try:
                text = await card.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'Ualá: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['uala'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Ualá scrape error: {e}')
    return promos

async def scrape_naranja(page) -> list[dict]:
    """Scrapea beneficios de Naranja X"""
    promos = []
    try:
        await page.goto('https://www.naranjax.com/beneficios', timeout=30000)
        await page.wait_for_timeout(4000)
        
        items = await page.query_selector_all('[class*="benefit"], [class*="promotion"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15 and any(c.isdigit() for c in text):
                    promos.append({
                        'titulo':      f'Naranja X: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['naranja'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Naranja X scrape error: {e}')
    return promos

async def scrape_bna(page) -> list[dict]:
    """Scrapea beneficios del Banco Nación"""
    promos = []
    try:
        await page.goto('https://www.bna.com.ar/Personas/Beneficios', timeout=30000)
        await page.wait_for_timeout(5000)
        
        items = await page.query_selector_all('.beneficio, [class*="benefit"], .card-beneficio, article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'Banco Nación: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['bna', 'cuenta_dni'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'BNA scrape error: {e}')
    return promos

async def scrape_bbva(page) -> list[dict]:
    """Scrapea beneficios de BBVA"""
    promos = []
    try:
        await page.goto('https://www.bbva.com.ar/personas/beneficios.html', timeout=30000)
        await page.wait_for_timeout(5000)
        
        items = await page.query_selector_all('[class*="benefit"], [class*="promo"], .card')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15 and any(c.isdigit() for c in text):
                    promos.append({
                        'titulo':      f'BBVA: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['bbva', 'visa', 'mastercard'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'BBVA scrape error: {e}')
    return promos

async def scrape_santander(page) -> list[dict]:
    """Scrapea beneficios de Santander"""
    promos = []
    try:
        await page.goto('https://www.santander.com.ar/banco/online/ofertas', timeout=30000)
        await page.wait_for_timeout(5000)
        
        items = await page.query_selector_all('[class*="oferta"], [class*="promo"], [class*="benefit"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'Santander: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['santander', 'visa', 'mastercard'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Santander scrape error: {e}')
    return promos

async def scrape_galicia(page) -> list[dict]:
    """Scrapea beneficios de Galicia"""
    promos = []
    try:
        await page.goto('https://www.galicia.ar/es/personas/beneficios', timeout=30000)
        await page.wait_for_timeout(5000)
        
        items = await page.query_selector_all('[class*="beneficio"], [class*="promo"], [class*="benefit"]')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'Galicia: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['galicia', 'visa', 'mastercard'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Galicia scrape error: {e}')
    return promos

async def scrape_modo(page) -> list[dict]:
    """Scrapea beneficios de MODO"""
    promos = []
    try:
        await page.goto('https://www.modo.com.ar/beneficios', timeout=30000)
        await page.wait_for_timeout(4000)

        items = await page.query_selector_all('[class*="benefit"], [class*="promo"], [class*="card"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'MODO: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['modo'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'MODO scrape error: {e}')
    return promos

async def scrape_personal_pay(page) -> list[dict]:
    """Scrapea beneficios de Personal Pay"""
    promos = []
    try:
        await page.goto('https://www.personalpay.com.ar/beneficios', timeout=30000)
        await page.wait_for_timeout(4000)

        items = await page.query_selector_all('[class*="benefit"], [class*="promo"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'Personal Pay: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['personal_pay'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Personal Pay scrape error: {e}')
    return promos

async def scrape_macro(page) -> list[dict]:
    """Scrapea beneficios del Banco Macro"""
    promos = []
    try:
        await page.goto('https://www.macro.com.ar/beneficios', timeout=30000)
        await page.wait_for_timeout(5000)

        items = await page.query_selector_all('[class*="benefit"], [class*="beneficio"], [class*="promo"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'Macro: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['macro', 'visa', 'mastercard'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Macro scrape error: {e}')
    return promos

async def scrape_hsbc(page) -> list[dict]:
    """Scrapea beneficios de HSBC Argentina"""
    promos = []
    try:
        await page.goto('https://www.hsbc.com.ar/beneficios/', timeout=30000)
        await page.wait_for_timeout(5000)

        items = await page.query_selector_all('[class*="benefit"], [class*="promo"], article, .card')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'HSBC: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['hsbc', 'visa', 'mastercard'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'HSBC scrape error: {e}')
    return promos

async def scrape_ciudad(page) -> list[dict]:
    """Scrapea beneficios del Banco Ciudad"""
    promos = []
    try:
        await page.goto('https://www.bancociudad.com.ar/beneficios', timeout=30000)
        await page.wait_for_timeout(5000)

        items = await page.query_selector_all('[class*="benefit"], [class*="beneficio"], [class*="promo"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'Banco Ciudad: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['ciudad', 'visa', 'mastercard'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Banco Ciudad scrape error: {e}')
    return promos

async def scrape_provincia(page) -> list[dict]:
    """Scrapea beneficios del Banco Provincia (Cuenta DNI también aplica)"""
    promos = []
    try:
        await page.goto('https://www.bancoprovincia.com.ar/Beneficios', timeout=30000)
        await page.wait_for_timeout(5000)

        items = await page.query_selector_all('[class*="benefit"], [class*="beneficio"], [class*="promo"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'Banco Provincia: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['provincia', 'cuenta_dni', 'visa', 'mastercard'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Banco Provincia scrape error: {e}')
    return promos

async def scrape_supervielle(page) -> list[dict]:
    """Scrapea beneficios de Supervielle"""
    promos = []
    try:
        await page.goto('https://www.supervielle.com.ar/beneficios', timeout=30000)
        await page.wait_for_timeout(5000)

        items = await page.query_selector_all('[class*="benefit"], [class*="beneficio"], [class*="promo"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'Supervielle: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['supervielle', 'visa', 'mastercard'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Supervielle scrape error: {e}')
    return promos

async def scrape_icbc(page) -> list[dict]:
    """Scrapea beneficios de ICBC Argentina"""
    promos = []
    try:
        await page.goto('https://www.icbc.com.ar/beneficios', timeout=30000)
        await page.wait_for_timeout(5000)

        items = await page.query_selector_all('[class*="benefit"], [class*="beneficio"], [class*="promo"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'ICBC: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['icbc', 'visa', 'mastercard'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'ICBC scrape error: {e}')
    return promos

async def scrape_brubank(page) -> list[dict]:
    """Scrapea beneficios de Brubank"""
    promos = []
    try:
        await page.goto('https://www.brubank.com/beneficios', timeout=30000)
        await page.wait_for_timeout(4000)

        items = await page.query_selector_all('[class*="benefit"], [class*="promo"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'Brubank: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['brubank'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Brubank scrape error: {e}')
    return promos

async def scrape_cabal(page) -> list[dict]:
    """Scrapea beneficios de Cabal (crédito y débito)"""
    promos = []
    try:
        await page.goto('https://www.cabal.coop.ar/beneficios', timeout=30000)
        await page.wait_for_timeout(4000)

        items = await page.query_selector_all('[class*="benefit"], [class*="beneficio"], [class*="promo"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'Cabal: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['cabal', 'cabal_cred'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Cabal scrape error: {e}')
    return promos

async def scrape_comafi(page) -> list[dict]:
    """Scrapea beneficios de Banco Comafi (portal Te Va Bien — tevabien.com)"""
    promos = []
    try:
        await page.goto('https://www.tevabien.com/beneficios.aspx', timeout=30000)
        await page.wait_for_timeout(4000)

        items = await page.query_selector_all('[class*="benefit"], [class*="promo"], [class*="card"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo':      f'Comafi: {text[:80]}',
                        'descripcion': text,
                        'wallets':     ['comafi', 'visa', 'mastercard'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Comafi scrape error: {e}')
    return promos

# ════════════════════════════════════════════════════════════
# UTILIDADES
# ════════════════════════════════════════════════════════════

def extract_percent(text: str) -> float:
    """Extrae el porcentaje de un texto"""
    matches = re.findall(r'(\d+)\s*%', text)
    if matches:
        return float(matches[0])
    return 10.0  # Default si no encuentra porcentaje

def promo_to_supabase(promo: dict, comercio_id: str) -> dict:
    """Convierte una promo scrapeada al formato de Supabase"""
    return {
        'comercio_id':  comercio_id,
        'titulo':       promo.get('titulo', '')[:200],
        'descripcion':  promo.get('descripcion', '')[:500],
        'tipo':         promo.get('tipo', 'porcentaje'),
        'valor':        promo.get('valor', 10),
        'wallets':      promo.get('wallets', []),
        'fecha_inicio': datetime.now().strftime('%Y-%m-%d'),
        'fecha_fin':    FECHA_FIN_DEFAULT,
        'estado':       'pendiente',  # Siempre pendiente para revisión del admin
        'dias_semana':  [0,1,2,3,4,5,6],
    }

def ya_existe(titulo: str) -> bool:
    """Verifica si una promo con ese título ya está en la BD"""
    result = sb.from_('descuentos').select('id').eq('titulo', titulo[:200]).execute()
    return len(result.data) > 0

# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

async def main():
    print(f'🤖 Iniciando scraper — {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    
    # Obtener o crear comercio "Banco/Billetera Virtual"
    # En producción deberías tener comercios separados por entidad
    comercio_id = COMERCIO_BANCO_ID
    if not comercio_id:
        # Buscar o crear un comercio genérico para promos bancarias
        result = sb.from_('comercios').select('id').eq('nombre', 'Promos Bancarias').execute()
        if result.data:
            comercio_id = result.data[0]['id']
        else:
            new = sb.from_('comercios').insert({
                'nombre':    'Promos Bancarias',
                'categoria': 'supermercados',
                'direccion': 'Todo el país',
                'ciudad':    'Buenos Aires',
                'provincia': 'Buenos Aires',
                'latitud':   -34.6037,
                'longitud':  -58.3816,
                'estado':    'aprobado',
                'verificado': True,
            }).execute()
            comercio_id = new.data[0]['id'] if new.data else None
    
    if not comercio_id:
        print('❌ No se pudo obtener comercio_id')
        return

    all_promos = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1280, 'height': 720},
        )
        page = await context.new_page()
        
        # Ejecutar scrapers
        scrapers = [
            ('Mercado Pago',   scrape_mercadopago),
            ('Ualá',           scrape_uala),
            ('MODO',           scrape_modo),
            ('Personal Pay',   scrape_personal_pay),
            ('Naranja X',      scrape_naranja),
            ('Banco Nación',   scrape_bna),
            ('BBVA',           scrape_bbva),
            ('Santander',      scrape_santander),
            ('Galicia',        scrape_galicia),
            ('Banco Macro',    scrape_macro),
            ('HSBC',           scrape_hsbc),
            ('Banco Ciudad',   scrape_ciudad),
            ('Banco Provincia',scrape_provincia),
            ('Supervielle',    scrape_supervielle),
            ('ICBC',           scrape_icbc),
            ('Brubank',        scrape_brubank),
            ('Cabal',          scrape_cabal),
            ('Comafi',         scrape_comafi),
        ]
        
        for nombre, scraper_fn in scrapers:
            print(f'  Scrapeando {nombre}...')
            try:
                promos = await scraper_fn(page)
                print(f'  ✅ {nombre}: {len(promos)} promos encontradas')
                all_promos.extend(promos)
            except Exception as e:
                print(f'  ❌ {nombre}: {e}')
        
        await browser.close()
    
    # Subir a Supabase (solo las que no existen)
    nuevas = 0
    for promo in all_promos:
        if promo.get('titulo') and not ya_existe(promo['titulo']):
            record = promo_to_supabase(promo, comercio_id)
            try:
                sb.from_('descuentos').insert(record).execute()
                nuevas += 1
            except Exception as e:
                print(f'  Error insertando: {e}')
    
    print(f'\n✅ Scraper terminado: {len(all_promos)} encontradas, {nuevas} nuevas subidas a Supabase')
    print('📋 Las nuevas promos están en estado "pendiente" para revisión del admin')

if __name__ == '__main__':
    asyncio.run(main())
