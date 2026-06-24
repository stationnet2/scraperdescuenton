"""
Descuenton — Scraper automático de promociones bancarias argentinas
Corre en Railway, se ejecuta cada 24hs (ver scheduler.py)

Entidades:
- Mercado Pago, Ualá, Naranja X, Banco Nación, BBVA, Santander, Galicia
- MODO, Personal Pay, Banco Macro, HSBC, Banco Ciudad, Banco Provincia,
  Supervielle, ICBC, Brubank, Cabal, Comafi
- Cuenta DNI (vía API real, no scraping — ver scrape_cuentadni_comercios)

Las promos genéricas (sin cadena ni comercio real detectado) se suben al
comercio "Promos Bancarias". Las promos de cadenas conocidas (Changomas,
Dia, Carrefour, etc.) se replican por cada sucursal cargada en
`sucursales_cadenas`. Las de Cuenta DNI crean comercios reales con
coordenadas verdaderas, sacadas directo de la API del Banco Provincia.

Todas las promos nuevas quedan en estado 'pendiente' para revisión del admin.
"""

import asyncio
import os
import re
import httpx
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from supabase import create_client, Client

# ── Config desde variables de entorno ────────────────────
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://TU-PROYECTO.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'TU_SERVICE_ROLE_KEY')  # service_role, no anon
COMERCIO_BANCO_ID = os.environ.get('COMERCIO_BANCO_ID', '')

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

CATEGORIA_DEFAULT = 'supermercados'
FECHA_FIN_DEFAULT = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')


# ════════════════════════════════════════════════════════════
# UTILIDADES
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
    """Extrae el porcentaje de un texto - múltiples patrones"""
    if not text:
        return 10.0
    matches = re.findall(r'(\d+)\s*(?:%|por\s*ciento)', text, re.IGNORECASE)
    if matches:
        return float(matches[0])
    matches = re.findall(r'descuento\s+(?:del\s+)?(\d+)', text, re.IGNORECASE)
    if matches:
        return float(matches[0])
    matches = re.findall(r'ahorro\s+(\d+)', text, re.IGNORECASE)
    if matches:
        return float(matches[0])
    matches = re.findall(r'(\d+)\s*%', text)
    if matches:
        return float(matches[0])
    return 10.0


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
        'estado':       'pendiente',
        'dias_semana':  [0, 1, 2, 3, 4, 5, 6],
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
# DETECCIÓN DE CADENAS Y SUCURSALES
# (para promos de cadenas tipo Changomas, sin coordenadas propias)
# ════════════════════════════════════════════════════════════

CADENAS_CONOCIDAS = {
    'changomas':  ['changomas', 'chango mas'],
    'dia':        [' dia ', 'supermercados dia', 'dia%'],
    'carrefour':  ['carrefour'],
    'coto':       ['coto '],
    'jumbo':      ['jumbo'],
    'vea':        [' vea '],
    'farmacity':  ['farmacity'],
    'easy':       ['easy '],
    'sodimac':    ['sodimac'],
}


def detectar_cadena(texto: str) -> str | None:
    """Busca si el texto de la promo menciona alguna cadena conocida"""
    texto_lower = f' {texto.lower()} '
    for cadena, variantes in CADENAS_CONOCIDAS.items():
        for variante in variantes:
            if variante in texto_lower:
                return cadena
    return None


def obtener_sucursales(cadena: str) -> list[dict]:
    """Trae las sucursales conocidas de una cadena desde sucursales_cadenas"""
    result = sb.from_('sucursales_cadenas').select('*').eq('cadena', cadena).execute()
    return result.data or []


def obtener_o_crear_comercio_sucursal(sucursal: dict) -> str | None:
    """
    Si la sucursal ya tiene comercio_id vinculado, lo devuelve.
    Si no, crea el comercio, lo vincula en sucursales_cadenas, y devuelve el id.
    """
    if sucursal.get('comercio_id'):
        return sucursal['comercio_id']

    nuevo = sb.from_('comercios').insert({
        'nombre':     sucursal['nombre_sucursal'],
        'categoria':  sucursal.get('categoria', 'supermercados'),
        'direccion':  sucursal['direccion'],
        'ciudad':     sucursal.get('ciudad', 'La Plata'),
        'provincia':  sucursal.get('provincia', 'Buenos Aires'),
        'latitud':    sucursal['latitud'],
        'longitud':   sucursal['longitud'],
        'estado':     'aprobado',
        'verificado': True,
    }).execute()

    comercio_id = nuevo.data[0]['id'] if nuevo.data else None

    if comercio_id:
        sb.from_('sucursales_cadenas').update({
            'comercio_id': comercio_id
        }).eq('id', sucursal['id']).execute()

    return comercio_id


# ════════════════════════════════════════════════════════════
# CUENTA DNI — vía API real (sin Playwright)
# ════════════════════════════════════════════════════════════

# idBuscador=8 → "Comercios de barrio" (20% lunes a viernes). Si la campaña
# vigente cambia de id, revisar la pestaña Network del buscador
# correspondiente en bancoprovincia.com.ar/cuentadni/buscadores/...
IDS_BUSCADOR_CUENTADNI = [8]
LOCALIDADES_CUENTADNI = ['LA PLATA']

RUBRO_A_CATEGORIA = {
    'ALMACENES/ DIETÉTICAS Y MÁS':              'supermercados',
    'CARNICERÍAS/ GRANJAS Y MÁS':                'supermercados',
    'VERDULERÍAS/ FRUTERÍAS':                    'verdulerias',
    'FARMACIAS/ PERFUMERÍAS Y MÁS':              'farmacias',
    'KIOSKO/ TABAQUERÍA/ POLIRUBRO':             'supermercados',
    'COMBUSTIBLE':                                'combustible',
    'INDUMENTARIA/ BOUTIQUE':                     'indumentaria',
    'CALZADOS':                                   'indumentaria',
    'LENCERÍA':                                   'indumentaria',
    'ARTÍCULOS DE INFORMÁTICA':                   'electronica',
    'CELULARES':                                  'electronica',
    'ARTÍCULOS ELÉCTRICOS':                       'electronica',
    'ELECTRODOMÉSTICOS':                          'electronica',
    'FERRETERÍAS':                                'ferreterias',
    'BAR/ PUB':                                   'cafeterias',
    'HELADERÍA':                                  'cafeterias',
    'HELADERIA':                                  'cafeterias',
    'FAST FOOD/ PARA LLEVAR':                     'restaurantes',
    'RESTAURANTES/ CONFITERÍAS':                  'restaurantes',
    'FÁBRICA DE PASTAS/ ROTISERÍAS':              'restaurantes',
    'CINES':                                      'entretenimiento',
    'ENTRETENIMIENTO':                            'entretenimiento',
    'CLUBES/ CAMPINGS/ BALNEARIOS':               'entretenimiento',
    'PANADERÍA':                                  'supermercados',
}

DESCRIPCION_PROMO_CUENTADNI = (
    'Ahorrá pagando con Cuenta DNI en este comercio adherido. '
    'Promo "Comercios de barrio" de Banco Provincia — consultá vigencia y tope de reintegro en la app Cuenta DNI.'
)


def mapear_categoria(rubro: str) -> str:
    """Mapea un rubro de Banco Provincia a una categoría de la app"""
    if not rubro:
        return CATEGORIA_DEFAULT
    return RUBRO_A_CATEGORIA.get(rubro.upper().strip(), CATEGORIA_DEFAULT)


async def fetch_comercios_cuentadni(id_buscador: int, localidad: str) -> list[dict]:
    """Llama directo a la API de Banco Provincia y trae los comercios de una localidad"""
    url = f'https://www.bancoprovincia.com.ar/cuentadni/Home/GetLocalesListadoByIdBuscador?idBuscador={id_buscador}'
    payload = {'localidad': localidad}

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            resp = await client.post(url, data=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get('data', [])
        except Exception as e:
            print(f'  Cuenta DNI API error ({localidad}, buscador {id_buscador}): {e}')
            return []


def comercio_cuentadni_valido(c: dict) -> bool:
    """Filtra comercios sin coordenadas válidas"""
    return c.get('latitud') is not None and c.get('longitud') is not None


async def scrape_cuentadni_comercios() -> list[dict]:
    """Trae los comercios reales de Cuenta DNI en las localidades configuradas"""
    todos = []
    for id_buscador in IDS_BUSCADOR_CUENTADNI:
        for localidad in LOCALIDADES_CUENTADNI:
            comercios = await fetch_comercios_cuentadni(id_buscador, localidad)
            validos = [c for c in comercios if comercio_cuentadni_valido(c)]
            print(f'  Cuenta DNI ({localidad}, buscador {id_buscador}): {len(comercios)} comercios, {len(validos)} con coordenadas')
            todos.extend(validos)
    return todos


def obtener_o_crear_comercio_cuentadni(item: dict) -> str | None:
    """Busca el comercio por nombre+dirección; si no existe, lo crea con coordenadas reales"""
    nombre = item['empresa'].strip()[:200]
    direccion = item['direccion'].strip()[:200]

    existente = sb.from_('comercios') \
        .select('id') \
        .eq('nombre', nombre) \
        .eq('direccion', direccion) \
        .maybe_single() \
        .execute()

    if existente and existente.data:
        return existente.data['id']

    nuevo = sb.from_('comercios').insert({
        'nombre':     nombre,
        'categoria':  mapear_categoria(item.get('rubro', '')),
        'direccion':  direccion,
        'ciudad':     item.get('localidad', 'La Plata').title(),
        'provincia':  'Buenos Aires',
        'latitud':    item['latitud'],
        'longitud':   item['longitud'],
        'estado':     'aprobado',
        'verificado': False,
    }).execute()

    return nuevo.data[0]['id'] if nuevo.data else None


async def procesar_comercios_cuentadni():
    """Crea/reutiliza comercios reales de Cuenta DNI y les agrega la promo"""
    comercios_cdni = await scrape_cuentadni_comercios()

    creados = 0
    promos_nuevas = 0

    for item in comercios_cdni:
        comercio_id = obtener_o_crear_comercio_cuentadni(item)
        if not comercio_id:
            continue
        creados += 1

        titulo_promo = f"Cuenta DNI — {item['empresa'].strip()[:150]}"
        if ya_existe(titulo_promo):
            continue

        record = {
            'comercio_id':  comercio_id,
            'titulo':       titulo_promo[:200],
            'descripcion':  DESCRIPCION_PROMO_CUENTADNI[:500],
            'tipo':         'porcentaje',
            'valor':        20,
            'wallets':      ['cuenta_dni'],
            'fecha_inicio': datetime.now().strftime('%Y-%m-%d'),
            'fecha_fin':    FECHA_FIN_DEFAULT,
            'estado':       'pendiente',
            'dias_semana':  [1, 2, 3, 4, 5],
        }
        try:
            sb.from_('descuentos').insert(record).execute()
            promos_nuevas += 1
        except Exception as e:
            print(f'  Error insertando promo Cuenta DNI de "{item["empresa"]}": {e}')

    print(f'  ✅ Cuenta DNI: {creados} comercios procesados, {promos_nuevas} promos nuevas')


# ════════════════════════════════════════════════════════════
# SCRAPERS POR ENTIDAD (Playwright)
# ════════════════════════════════════════════════════════════

async def scrape_mercadopago(page) -> list[dict]:
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
                        'titulo': f'Mercado Pago: {title[:80]}',
                        'descripcion': title,
                        'wallets': ['mercadopago'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(title),
                    })
            except:
                pass
    except Exception as e:
        print(f'MercadoPago scrape error: {e}')
    return promos


async def scrape_uala(page) -> list[dict]:
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
                        'titulo': f'Ualá: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['uala'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Ualá scrape error: {e}')
    return promos


async def scrape_naranja(page) -> list[dict]:
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
                        'titulo': f'Naranja X: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['naranja'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Naranja X scrape error: {e}')
    return promos


async def scrape_bna(page) -> list[dict]:
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
                        'titulo': f'Banco Nación: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['bna'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'BNA scrape error: {e}')
    return promos


async def scrape_bbva(page) -> list[dict]:
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
                        'titulo': f'BBVA: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['bbva', 'visa', 'mastercard'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'BBVA scrape error: {e}')
    return promos


async def scrape_santander(page) -> list[dict]:
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
                        'titulo': f'Santander: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['santander', 'visa', 'mastercard'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Santander scrape error: {e}')
    return promos


async def scrape_galicia(page) -> list[dict]:
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
                        'titulo': f'Galicia: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['galicia', 'visa', 'mastercard'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Galicia scrape error: {e}')
    return promos


async def scrape_modo(page) -> list[dict]:
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
                        'titulo': f'MODO: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['modo'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'MODO scrape error: {e}')
    return promos


async def scrape_personal_pay(page) -> list[dict]:
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
                        'titulo': f'Personal Pay: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['personal_pay'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Personal Pay scrape error: {e}')
    return promos


async def scrape_macro(page) -> list[dict]:
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
                        'titulo': f'Macro: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['macro', 'visa', 'mastercard'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Macro scrape error: {e}')
    return promos


async def scrape_hsbc(page) -> list[dict]:
    promos = []
    try:
        await page.goto('https://www.hsbc.com.ar/beneficios/', timeout=30000)
        await cerrar_popups(page)
        await page.wait_for_timeout(5000)
        items = await page.query_selector_all('[class*="benefit"], [class*="promo"], article, .card')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo': f'HSBC: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['hsbc', 'visa', 'mastercard'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'HSBC scrape error: {e}')
    return promos


async def scrape_ciudad(page) -> list[dict]:
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
                        'titulo': f'Banco Ciudad: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['ciudad', 'visa', 'mastercard'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Banco Ciudad scrape error: {e}')
    return promos


async def scrape_provincia(page) -> list[dict]:
    """Promos generales del Banco Provincia (no Cuenta DNI, eso va aparte vía API)"""
    promos = []
    try:
        await page.goto('https://www.bancoprovincia.com.ar/cuentadni/contenidos/cdniBeneficios/', timeout=30000)
        await cerrar_popups(page)
        await page.wait_for_timeout(5000)
        items = await page.query_selector_all('[class*="benefit"], [class*="beneficio"], [class*="promo"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo': f'Banco Provincia: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['provincia', 'cuenta_dni', 'visa', 'mastercard'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Banco Provincia scrape error: {e}')
    return promos


async def scrape_supervielle(page) -> list[dict]:
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
                        'titulo': f'Supervielle: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['supervielle', 'visa', 'mastercard'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Supervielle scrape error: {e}')
    return promos


async def scrape_icbc(page) -> list[dict]:
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
                        'titulo': f'ICBC: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['icbc', 'visa', 'mastercard'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'ICBC scrape error: {e}')
    return promos


async def scrape_brubank(page) -> list[dict]:
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
                        'titulo': f'Brubank: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['brubank'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Brubank scrape error: {e}')
    return promos


async def scrape_cabal(page) -> list[dict]:
    promos = []
    try:
        await page.goto('https://www.cabal.coop/personas/promociones', timeout=30000)
        await cerrar_popups(page)
        await page.wait_for_timeout(4000)
        items = await page.query_selector_all('[class*="benefit"], [class*="beneficio"], [class*="promo"], article')
        for item in items[:20]:
            try:
                text = await item.inner_text()
                text = text.strip()[:200]
                if len(text) > 15:
                    promos.append({
                        'titulo': f'Cabal: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['cabal', 'cabal_cred'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
                    })
            except:
                pass
    except Exception as e:
        print(f'Cabal scrape error: {e}')
    return promos


async def scrape_comafi(page) -> list[dict]:
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
                        'titulo': f'Comafi: {text[:80]}',
                        'descripcion': text,
                        'wallets': ['comafi', 'visa', 'mastercard'],
                        'tipo': 'porcentaje',
                        'valor': extract_percent(text),
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

    # Comercio genérico "Promos Bancarias" (para promos sin cadena/comercio real detectado)
    comercio_id = COMERCIO_BANCO_ID
    if not comercio_id:
        result = sb.from_('comercios').select('id').eq('nombre', 'Promos Bancarias').execute()
        if result.data:
            comercio_id = result.data[0]['id']
        else:
            new = sb.from_('comercios').insert({
                'nombre': 'Promos Bancarias',
                'categoria': 'supermercados',
                'direccion': 'Todo el país',
                'ciudad': 'Buenos Aires',
                'provincia': 'Buenos Aires',
                'latitud': -34.6037,
                'longitud': -58.3816,
                'estado': 'aprobado',
                'verificado': True,
            }).execute()
            comercio_id = new.data[0]['id'] if new.data else None

    if not comercio_id:
        print('❌ No se pudo obtener comercio_id genérico')
        return

    # ── 1) Cuenta DNI vía API real (comercios reales georreferenciados) ──
    print('  Procesando Cuenta DNI (vía API)...')
    try:
        await procesar_comercios_cuentadni()
    except Exception as e:
        print(f'  ❌ Cuenta DNI: {e}')

    # ── 2) Scrapers con Playwright para el resto de entidades ───────────
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

        scrapers = [
            ('Mercado Pago',    scrape_mercadopago),
            ('Ualá',            scrape_uala),
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

    # ── 3) Subir a Supabase: cadenas conocidas → sucursales reales ──────
    #      promos genéricas → comercio "Promos Bancarias"
    nuevas = 0
    errores = 0

    for promo in all_promos:
        titulo = promo.get('titulo', '')
        if not titulo:
            continue

        texto_completo = f"{titulo} {promo.get('descripcion', '')}"
        cadena = detectar_cadena(texto_completo)

        if cadena:
            sucursales = obtener_sucursales(cadena)
            if not sucursales:
                print(f'  ⚠️  Promo de "{cadena}" detectada pero sin sucursales cargadas en sucursales_cadenas. Se omite.')
                continue

            for sucursal in sucursales:
                titulo_sucursal = f"{titulo} — {sucursal['nombre_sucursal']}"
                if ya_existe(titulo_sucursal):
                    continue

                comercio_id_sucursal = obtener_o_crear_comercio_sucursal(sucursal)
                if not comercio_id_sucursal:
                    print(f'  ❌ No se pudo crear/obtener comercio para {sucursal["nombre_sucursal"]}')
                    continue

                record = promo_to_supabase(promo, comercio_id_sucursal)
                record['titulo'] = titulo_sucursal[:200]
                try:
                    sb.from_('descuentos').insert(record).execute()
                    nuevas += 1
                except Exception as e:
                    errores += 1
                    print(f'  Error insertando promo de sucursal: {e}')
        else:
            if ya_existe(titulo):
                continue
            record = promo_to_supabase(promo, comercio_id)
            try:
                sb.from_('descuentos').insert(record).execute()
                nuevas += 1
            except Exception as e:
                errores += 1
                print(f'  Error insertando: {e}')

    print(f'\n✅ Scraper terminado:')
    print(f'   📊 Total encontradas (Playwright): {len(all_promos)}')
    print(f'   🆕 Nuevas subidas: {nuevas}')
    print(f'   ⚠️  Errores: {errores}')
    print('📋 Las nuevas promos están en estado "pendiente" para revisión del admin')


if __name__ == '__main__':
    asyncio.run(main())
