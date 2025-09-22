# Etapa 1: Imagen base con Python y dependencias del sistema
# Usamos una imagen oficial de Python 3, delgada y optimizada (slim).
FROM python:3.11-slim

# Instalar las dependencias del sistema operativo necesarias para Tesseract OCR y OpenCV.
# - tesseract-ocr: El motor de OCR.
# - tesseract-ocr-spa: El paquete de idioma español para Tesseract.
# - libgl1: Una librería de gráficos necesaria para OpenCV, incluso en modo headless.
# Usamos --no-install-recommends para mantener la imagen lo más pequeña posible.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    libgl1 \
    # Limpiar el caché de apt para reducir el tamaño final de la imagen.
    && rm -rf /var/lib/apt/lists/*

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Actualizar pip y las herramientas de empaquetado
RUN pip install --no-cache-dir --upgrade pip

# Copiar solo el archivo de requerimientos primero para aprovechar el caché de Docker
# Esto evita tener que reinstalar todo si solo cambia el código de la app.
COPY requirements.txt .

# Instalar las dependencias de Python
# --no-cache-dir reduce el tamaño de la imagen
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código de la aplicación al directorio de trabajo
COPY . .

# Variable de entorno para indicar que la app corre en producción
# Nuestro config.py usará esta variable para cargar secretos desde AWS
ENV FLASK_ENV=production

# Exponer el puerto en el que Gunicorn se ejecutará.
# App Runner usará este puerto para dirigir el tráfico.
EXPOSE 8080

# Comando para ejecutar la aplicación usando Gunicorn
# Escucha en todas las interfaces (0.0.0.0) en el puerto 8080.
# 'main:app' le dice a Gunicorn que busque el objeto 'app' en el archivo 'main.py'.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "main:app"]
