# Descuenton Scraper — Despliegue en Railway

## Qué hace
Extrae automáticamente las promociones de bancos y billeteras argentinas cada 24hs y las sube a Supabase como descuentos en estado `pendiente` para que el admin las revise y apruebe.

## Entidades que scrapea
- Mercado Pago
- Ualá
- MODO
- Personal Pay
- Naranja X
- Banco Nación (incluye Cuenta DNI)
- BBVA
- Santander
- Galicia
- Banco Macro
- HSBC
- Banco Ciudad
- Banco Provincia (incluye Cuenta DNI)
- Supervielle
- ICBC
- Brubank
- Cabal (crédito y débito)
- Banco Comafi (portal tevabien.com)

## ⚠️ Importante sobre las entidades nuevas

Los scrapers de **MODO, Personal Pay, Macro, HSBC, Banco Ciudad, Banco Provincia, Supervielle, ICBC, Brubank, Cabal y Comafi** usan selectores CSS genéricos (`[class*="benefit"]`, `[class*="promo"]`, etc.) porque no pude verificar el HTML real de cada sitio en este momento, salvo Comafi donde sí confirmé la URL correcta (`tevabien.com/beneficios.aspx`).

**Antes de poner esto en producción, tenés que:**
1. Correr cada scraper individualmente en modo no-headless para ver qué trae
2. Si trae basura o nada, inspeccionar el HTML real del sitio (botón derecho → Inspeccionar en la página de beneficios) y ajustar el selector
3. Confirmar que la URL de beneficios de cada entidad sigue siendo la misma (las empresas cambian sus webs seguido)

## Entidades que probablemente no se puedan scrapear así

Estas no tienen una página de "beneficios" pública simple, o requieren login:
- **Wilobank, BIND** — bancos digitales chicos, probablemente no tengan página pública de beneficios estructurada. Si la tienen, hay que armarles el scraper a mano viendo su sitio
- **Diners Club, Lider** — sus beneficios suelen requerir login de cliente, no son scrapeables de la página pública
- **Visa, Mastercard, Amex, Maestro, Visa Débito, Efectivo** — estas no son entidades emisoras, son redes/marcas de tarjeta. No tienen beneficios propios — los beneficios son del banco que emite la tarjeta (ya cubiertos en los scrapers de bancos)

## Billeteras dadas de baja

**Yacaré, BIMO y TodoBien ya no existen** — fueron quitadas de los scrapers y deberían quitarse también de la lista de wallets en `mockData.ts` de la app, para no mostrarlas como opción a los usuarios.

Para billeteras/bancos chicos sin scraper automático, la alternativa más realista es cargarlos manualmente vos cuando veas una promo, usando el panel de comercios como "Promos Bancarias".

## Despliegue en Railway (gratis)

### Paso 1 — Crear cuenta en Railway
1. Entrá a **https://railway.app** → Sign up con GitHub
2. El plan gratuito incluye $5 USD/mes de créditos — suficiente para correr el scraper

### Paso 2 — Crear proyecto
1. New Project → Deploy from GitHub repo
2. O usá Railway CLI: `railway init`

### Paso 3 — Variables de entorno
En Railway → tu proyecto → Variables, agregá:

```
SUPABASE_URL=https://kcaxkqxuacrdplmlpfjh.supabase.co
SUPABASE_KEY=TU_SERVICE_ROLE_KEY  ← NO el anon key, el service_role
COMERCIO_BANCO_ID=               ← Opcional, dejar vacío la primera vez
```

**Cómo obtener el service_role key:**
Supabase Dashboard → Settings → API → `service_role` (la clave larga de abajo)

⚠️ El service_role key tiene acceso total — nunca lo expongas en código público.

### Paso 4 — Deploy
```bash
# Con Railway CLI
railway up

# O conectar el repo en el dashboard de Railway
```

### Paso 5 — Verificar
En Railway → Logs vas a ver:
```
🤖 Iniciando scraper — 2024-XX-XX XX:XX
  Scrapeando Mercado Pago...
  ✅ Mercado Pago: 8 promos encontradas
  Scrapeando Ualá...
  ...
✅ Scraper terminado: 45 encontradas, 12 nuevas subidas a Supabase
💤 Esperando 24 horas hasta la próxima ejecución...
```

## Qué pasa después del scrape

1. Las promos nuevas aparecen en Supabase con `estado = 'pendiente'`
2. En el Panel Admin → Descuentos → aparecen para revisión
3. El admin las revisa, corrige si hace falta, y aprueba
4. Aparecen en la app automáticamente

## Notas importantes

- El scraper puede fallar si los bancos cambian su HTML. En ese caso hay que actualizar los selectores CSS en `scraper.py`.
- Algunos bancos tienen anti-scraping agresivo (Galicia, Santander, BBVA). Si fallan seguido, se pueden deshabilitar comentando la línea en la lista `scrapers`.
- Las promos duplicadas (mismo título) se ignoran automáticamente.
- Recomendado: correr `python scraper.py` localmente primero y revisar la consola antes de confiar en el deploy automático.

## Correr localmente para probar

```bash
pip install -r requirements.txt
playwright install chromium

# Variables de entorno
export SUPABASE_URL=https://kcaxkqxuacrdplmlpfjh.supabase.co
export SUPABASE_KEY=TU_SERVICE_ROLE_KEY

# Correr una vez
python scraper.py

# Correr en loop cada 24hs
python scheduler.py
```

