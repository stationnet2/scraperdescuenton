# Imagen oficial de Playwright: ya incluye Chromium + todas las
# dependencias del sistema correctas. Evita los errores de paquetes
# faltantes (ttf-unifont, ttf-ubuntu-font-family) que aparecen al usar
# python:3.11-slim, cuyo Debian base (Trixie) todavía no está soportado
# por Playwright.
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chromium y sus dependencias ya vienen instalados en la imagen base,
# pero lo dejamos por si el requirements.txt fija otra versión de Playwright.
RUN playwright install chromium

COPY . .

CMD ["python", "scheduler.py"]
