import os
import re # Importar el módulo de expresiones regulares
import boto3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from dotenv import load_dotenv

load_dotenv() # Carga las variables de entorno desde .env

app = Flask(__name__)
# Es crucial tener una SECRET_KEY para que las sesiones de Flask funcionen
app.secret_key = os.urandom(24)

# --- Configuración de Clientes de AWS ---
# Cliente de Cognito para autenticación
cognito_client = boto3.client(
    'cognito-idp',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_DEFAULT_REGION')
)
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
CLIENT_ID = os.getenv('COGNITO_CLIENT_ID')

# Cliente de Textract para OCR
textract_client = boto3.client(
    'textract',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_DEFAULT_REGION')
)


# --- Función para validar RUT ---
def find_rut_in_text(text):
    """
    Busca un patrón de RUT chileno en un texto.
    Ej: 12.345.678-9, 12345678-9, 12.345.678-K
    """
    # Expresión regular para encontrar el RUT
    # Soporta formatos con y sin puntos, con guión y con dígito verificador (número o K)
    rut_pattern = r'\b(\d{1,2}(?:\.?\d{3}){2}-[\dkK])\b'
    match = re.search(rut_pattern, text)
    if match:
        return match.group(1)
    return None

# --- Rutas de la Aplicación ---

@app.route("/")
def index():
    if 'username' in session:
        # Si el usuario está en sesión, muestra la encuesta
        return render_template('form.html')
    # Si no, redirige al login
    return redirect(url_for('login'))

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            response = cognito_client.initiate_auth(
                ClientId=CLIENT_ID,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': username,
                    'PASSWORD': password
                }
            )
            # Si la autenticación es exitosa, guardamos el usuario en la sesión
            session['username'] = username
            session['access_token'] = response['AuthenticationResult']['AccessToken']
            flash("Inicio de sesión exitoso!", "success")
            return redirect(url_for('index'))
        except cognito_client.exceptions.NotAuthorizedException:
            return render_template('login.html', error="Usuario o contraseña incorrectos.")
        except Exception as e:
            return render_template('login.html', error=f"Ocurrió un error: {e}")
            
    return render_template('login.html')

@app.route("/logout")
def logout():
    session.clear() # Limpia la sesión
    flash("Has cerrado sesión.", "info")
    return redirect(url_for('login'))

@app.route("/upload", methods=['POST'])
def upload_file():
    if 'username' not in session:
        flash("Por favor, inicia sesión para continuar.", "warning")
        return redirect(url_for('login'))

    if 'file' not in request.files:
        flash("No se encontró el archivo en la solicitud.", "danger")
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        flash("No se seleccionó ningún archivo.", "warning")
        return redirect(request.url)

    if file:
        # Leer los bytes de la imagen para enviarlos a Textract
        image_bytes = file.read()
        
        try:
            # Llamar a la API de Textract
            response = textract_client.detect_document_text(
                Document={'Bytes': image_bytes}
            )
            
            # Unir todo el texto detectado en una sola cadena
            detected_text = ""
            for item in response["Blocks"]:
                if item["BlockType"] == "LINE":
                    detected_text += item["Text"] + " "
            
            # Buscar el RUT en el texto extraído
            rut_encontrado = find_rut_in_text(detected_text)
            
            if rut_encontrado:
                flash(f"RUT encontrado en la imagen: {rut_encontrado}", "success")
                # Aquí podrías añadir la lógica para comparar con el RUT del usuario
                # Por ahora, solo lo mostramos.
            else:
                flash("No se pudo encontrar un RUT en la imagen.", "danger")
                # Para depuración, podríamos mostrar el texto detectado:
                # flash(f"Texto detectado: {detected_text}", "info")

        except Exception as e:
            flash(f"Error al procesar la imagen con Amazon Textract: {e}", "danger")

        return redirect(url_for('index'))

    return redirect(url_for('index'))


def main():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    main()
