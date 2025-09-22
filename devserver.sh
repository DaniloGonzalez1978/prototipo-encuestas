#!/bin/bash
# Este script inicia la aplicación Flask usando el servidor de producción Gunicorn.

echo "Activando entorno virtual..."
source .venv/bin/activate

# Define el puerto 5000 por defecto si la variable de entorno PORT no está establecida.
PORT=${PORT:-5000}
echo "Usando el puerto: $PORT"

echo "Iniciando Gunicorn..."
# El punto de entrada es 'main:app' (el objeto 'app' dentro del archivo 'main.py').
gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 300 main:app
