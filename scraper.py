"""
DescuMap — Scraper automático de promociones bancarias argentinas
Corre en Railway/Render, se ejecuta cada 24hs
Extrae promos de: Mercado Pago, Ualá, Naranja X, Banco Nación,
                  BBVA, Santander, Galicia, Cuenta DNI, MODO, Personal Pay,
                  Macro, HSBC, Ciudad, Provincia, Supervielle, ICBC, Brubank,
                  Cabal, Comafi
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
COMERCIO_BANCO_ID = os.environ.get('COMERCIO_BANCO_ID', '')  # ID del comercio genérico en tu BD

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Categoría por defecto para promos bancarias ───────────
CATEGORIA_DEFAULT = 'supermercados'
FECHA_FIN_DEFAULT = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

# ════════════════════════════════════════════════════════════
# UTILIDADES MEJORADAS
# ════════════════════════════════════════════════════════════

async def cerrar_popups(page):
    """Cierra popups comunes de cookies, avisos y modales"""
    try:
        selectors = [
            'button:has-text("Aceptar")',
            'button:has-text("Aceptar todas")',
            'button:has-text("Acepto")',
            'button:has-text("Entendido")',
            'button:has-text("Cerrar")',
            '.cookie-banner button',
            '[data-testid="accept-cookies"]',
            '[aria-label="Cerrar"]',
        ]
        for selector in selectors:
            btn = await page.query_selector(selector)
            if btn:
                try:
                    await btn.click(timeout=2000)
                    await page.wait_for_timeout(800)
                except:
                    pass
    except:
        pass

def extract_percent(text: str) -> float:
    """Extrae el porcentaje de un texto - versión mejorada con múltiples patrones"""
    if not text:
        return 10.0
    
    # Buscar patrones como "20%", "20 %", "20 por ciento"
    matches = re.findall(r'(\d+)\s*(?:%|por\s*ciento)', text, re.IGNORECASE)
    if matches:
        return float(matches[0])
    
    # Buscar patrones como "descuento del 20" o "20 de descuento"
    matches = re.findall(r'descuento\s+(?:del\s+)?(\d+)', text, re.IGNORECASE)
    if matches:
        return float(matches[0])
    
    # Buscar patrones como "ahorro 20" o "20 de ahorro"
    matches = re.findall(r'ahorro\s+(\d+)', text, re.IGNORECASE)
    if matches:
        return float(matches[0])
    
    # Buscar cualquier número seguido de % (incluso con espacios)
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
    try:
        result = sb.from_('descuentos').select('id').eq('titulo', titulo[:200]).execute()
        return len(result.data) > 0
    except Exception as e:
        print(f'  Error verificando existencia: {e}')
        return False

# ════════════════════════════════════════════════════════════
# SCRAPERS POR ENTIDAD (TODOS CON MANEJO DE POPUPS)
# ════════════════════════════════════════════════════════════

async def scrape_mercadopago(page) -> list[dict]:
    """Scrapea beneficios de Mercado Pago"""
    promos = []
    try:
        await page.goto('https://promociones.mercadopago.com.ar/', timeout=30000)
        await cerrar_popups(page)
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
        await page.goto('https://www.uala.com.ar/promociones', timeout=30000)
        await cerrar_popups(page)
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

# ════════════════════════════════════════════════════════════
# 🆕 SCRAPER ESPECÍFICO PARA CUENTA DNI
# ════════════════════════════════════════════════════════════

async def scrape_cuentadni(page) -> list[dict]:
    """Scrapea beneficios específicos de Cuenta DNI (billetera virtual)"""
    promos = []
    try:
        print('  → Navegando a Cuenta DNI...')
        
        # Cuenta DNI tiene su propia página de beneficios
        await page.goto('https://www.cuentadni.com.ar/beneficios', timeout=30000)
        await cerrar_popups(page)
        await page.wait_for_timeout(5000)
        
        # Screenshot de debug (opcional - descomentar para ver qué ve el scraper)
        # await page.screenshot(path='debug_cuentadni.png', full_page=True)
        # print('  → Screenshot guardado en debug_cuentadni.png')
        
        # Selectores específicos para Cuenta DNI
        items = await page.query_selector_all(
            '.benefit-card, .promo-card, [data-testid*="benefit"], '
            'article.beneficio, .card-beneficio, [class*="benefit"], '
            '[class*="promo"], .card, article'
        )
        
        print(f'  → Elementos encontrados en Cuenta DNI: {len(items)}')
        
        for item in items[:25]:
            try:
                # Intentar extraer título y descripción por separado
                title_elem = await item.query_selector('h2, h3, h4, .title, .benefit-title, strong')
                desc_elem = await item.query_selector('p, .description, .benefit-desc, span')
                
                if title_elem:
                    title = await title_elem.inner_text()
                else:
                    title = await item.inner_text()
                
                title = title.strip()[:200]
                
                if desc_elem:
                    desc = await desc_elem.inner_text()
                else:
                    desc = title
                
                desc = desc.strip()[:500]
                
                # Solo agregar si tiene contenido relevante
                if len(title) > 10 and (any(c.isdigit() for c in title) or 'descuento' in title.lower() or '%' in title):
                    promos.append({
                        'titulo':      f'Cuenta DNI: {title[:80]}',
                        'descripcion': desc,
                        'wallets':     ['cuenta_dni'],
                        'tipo':        'porcentaje',
                        'valor':       extract_percent(title + ' ' + desc),
                    })
            except Exception as e:
                print(f'  Error parsing item Cuenta DNI: {e}')
                pass
        
        # Si no encontró nada con selectores específicos, intentar extracción general
        if len(promos) == 0:
            print('  → No se encontraron elementos específicos, intentando extracción general...')
            try:
                body_text = await page.inner_text('body')
                # Buscar patrones de porcentaje en el texto
                percent_matches = re.findall(r'(\d+)\s*%', body_text)
                for match in percent_matches[:10]:
                    promos.append({
                        'titulo':      f'Cuenta DNI: {match}% de descuento',
                        'descripcion': f'Promoción encontrada en cuentadni.com.ar',
                        'wallets':     ['cuenta_dni'],
                        'tipo':        'porcentaje',
                        'valor':       float(match),
                    })
            except Exception as e:
                print(f'  Error en extracción general: {e}')
                
    except Exception as e:
        print(f'Cuenta DNI scrape error: {e}')
    return promos

# ════════════════════════════════════════════════════════════
# RESTO DE SCRAPERS (CON MANEJO DE POPUPS)
# ════════════════════════════════════════════════════════════

async def scrape_naranja(page) -> list[dict]:
    """Scrapea beneficios de Naranja X"""
    promos = []
    try:
        await page.goto('https://www.naranjax.com/promociones/', timeout=30000)
        await cerrar_popups(page)
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
        await page.goto('https://semananacion.com.ar/semananacion', timeout=30000)
        await cerrar_popups(page)
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
        await cerrar_popups(page)
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
        await page.goto('https://www.santander.com.ar/personas/beneficios', timeout=30000)
        await cerrar_popups(page)
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
        await page.goto('https://www.galicia.ar/personas/promociones', timeout=30000)
        await cerrar_popups(page)
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
        await page.goto('https://www.modo.com.ar/promos', timeout=30000)
        await cerrar_popups(page)
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
        await page.goto('https://www.personal.com.ar/pay/beneficios', timeout=30000)
        await cerrar_popups(page)
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
        await cerrar_popups(page)
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
        await page.goto('https://www.beneficios.icbc.com.ar/', timeout=30000)
        await cerrar_popups(page)
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
        await page.goto('https://www.bancociudad.com.ar/beneficios/', timeout=30000)
        await cerrar_popups(page)
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
    """Scrapea beneficios del Banco Provincia (NO Cuenta DNI, eso va aparte)"""
    promos = []
    try:
        await page.goto('https://www.bancoprovincia.com.ar/beneficios', timeout=30000)
        await cerrar_popups(page)
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
                        'wallets':     ['provincia', 'visa', 'mastercard'],
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
        await page.goto('https://www.supervielle.com.ar/personas/beneficios/descuentos', timeout=30000)
        await cerrar_popups(page)
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
        await page.goto('https://www.beneficios.icbc.com.ar/', timeout=30000)
        await cerrar_popups(page)
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
        await cerrar_popups(page)
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
        await cerrar_popups(page)
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
    """Scrapea beneficios de Banco Comafi (portal Te Va Bien)"""
    promos = []
    try:
        await page.goto('https://www.tevabien.com/beneficios.aspx', timeout=30000)
        await cerrar_popups(page)
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
# MAIN
# ════════════════════════════════════════════════════════════

async def main():
    print(f'🤖 Iniciando scraper — {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    
    # Obtener o crear comercio "Banco/Billetera Virtual"
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
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
        )
        page = await context.new_page()
        
        # Ejecutar scrapers — 🆕 Cuenta DNI agregado
        scrapers = [
            ('Mercado Pago',    scrape_mercadopago),
            ('Ualá',            scrape_uala),
            ('Cuenta DNI',      scrape_cuentadni),      # ← 🆕 NUEVO
            ('MODO',            scrape_modo),
            ('Personal Pay',    scrape_personal_pay),
            ('Naranja X',       scrape_naranja),
            ('Banco Nación',    scrape_bna),
            ('BBVA',            scrape_bbva),
            ('Santander',       scrape_santander),
            ('Galicia',         scrape_galicia),
            ('Banco Macro',     scrape_macro),
            ('HSBC',            scrape_hsbc),
            ('Banco Ciudad',    scrape_ciudad),
            ('Banco Provincia', scrape_provincia),
            ('Supervielle',     scrape_supervielle),
            ('ICBC',            scrape_icbc),
            ('Brubank',         scrape_brubank),
            ('Cabal',           scrape_cabal),
            ('Comafi',          scrape_comafi),
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
    errores = 0
    for promo in all_promos:
        if promo.get('titulo') and not ya_existe(promo['titulo']):
            record = promo_to_supabase(promo, comercio_id)
            try:
                sb.from_('descuentos').insert(record).execute()
                nuevas += 1
            except Exception as e:
                errores += 1
                print(f'  Error insertando "{promo.get("titulo", "")[:50]}": {e}')
    
    print(f'\n✅ Scraper terminado:')
    print(f'   📊 Total encontradas: {len(all_promos)}')
    print(f'   🆕 Nuevas subidas: {nuevas}')
    print(f'   ⚠️  Errores: {errores}')
    print('📋 Las nuevas promos están en estado "pendiente" para revisión del admin')

if __name__ == '__main__':
    asyncio.run(main())