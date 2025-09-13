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


# --- Funciones de Utilidad ---
def find_rut_in_text(text):
    """Busca un patrón de RUT chileno en un texto."""
    rut_pattern = r'\b(\d{1,2}(?:\.?\d{3}){2}-[\dkK])\b'
    match = re.search(rut_pattern, text)
    if match:
        return match.group(1)
    return None

def normalize_rut(rut_string):
    """Elimina puntos y convierte a mayúsculas para una comparación consistente."""
    if not rut_string:
        return ""
    return rut_string.replace(".", "").upper()

# --- Rutas de la Aplicación ---

@app.route("/")
def index():
    if 'username' in session:
        return render_template('form.html')
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
    session.clear()
    flash("Has cerrado sesión.", "info")
    return redirect(url_for('login'))

@app.route("/upload", methods=['POST'])
def upload_file():
    if 'username' not in session:
        flash("Por favor, inicia sesión para continuar.", "warning")
        return redirect(url_for('login'))

    if 'file' not in request.files or file.filename == '':
        flash("No se seleccionó ningún archivo válido.", "warning")
        return redirect(url_for('index'))

    file = request.files['file']
    image_bytes = file.read()
    
    try:
        # 1. Extraer texto con Textract
        response = textract_client.detect_document_text(Document={'Bytes': image_bytes})
        detected_text = " ".join([item["Text"] for item in response["Blocks"] if item["BlockType"] == "LINE"])
        
        # 2. Buscar RUT en el texto extraído
        rut_encontrado = find_rut_in_text(detected_text)
        
        if rut_encontrado:
            # 3. Si se encuentra un RUT, obtener datos del usuario de Cognito
            user_response = cognito_client.get_user(AccessToken=session['access_token'])
            rut_del_perfil = None
            # Corregido: Usar el nombre de atributo exacto 'custom:Rut'
            for attribute in user_response['UserAttributes']:
                if attribute['Name'] == 'custom:Rut':
                    rut_del_perfil = attribute['Value']
                    break
            
            if not rut_del_perfil:
                flash("No se encontró el atributo 'RUT' en tu perfil de usuario de Cognito.", "danger")
                return redirect(url_for('index'))

            # 4. Normalizar y comparar los RUTs
            rut_normalizado_imagen = normalize_rut(rut_encontrado)
            rut_normalizado_perfil = normalize_rut(rut_del_perfil)

            if rut_normalizado_imagen == rut_normalizado_perfil:
                flash(f"¡Validación exitosa! El RUT de la imagen ({rut_encontrado}) coincide con tu perfil.", "success")
            else:
                flash(f"Error de validación: El RUT de la imagen ({rut_encontrado}) no coincide con el de tu perfil ({rut_del_perfil}).", "danger")
        else:
            flash("No se pudo encontrar un RUT con formato válido en la imagen.", "danger")

    except Exception as e:
        flash(f"Ocurrió un error inesperado durante la validación: {e}", "danger")

    return redirect(url_for('index'))

def main():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    main()
