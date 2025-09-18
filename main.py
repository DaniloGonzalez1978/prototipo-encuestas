
import os
import re
import boto3
import json
import requests
import base64
import logging
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from dotenv import load_dotenv
from datetime import datetime
from werkzeug.utils import secure_filename
from botocore.exceptions import ClientError

# --- Librerías de Procesamiento de Imagen ---
import cv2
import pytesseract
from PIL import Image
import numpy as np

# --- Configuración del Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.jinja_env.add_extension('jinja2.ext.do')

# --- Función para obtener y limpiar variables de entorno ---
def get_env_variable(var_name, default=None):
    value = os.getenv(var_name, default)
    if isinstance(value, str):
        return value.strip()
    return value

# --- Clave Secreta ---
app.secret_key = get_env_variable('SECRET_KEY')
if not app.secret_key:
    raise ValueError("No se ha configurado la SECRET_KEY en las variables de entorno.")

# --- Configuraciones ---
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Clientes de Servicios AWS ---
dynamodb_client = boto3.client(
    'dynamodb',
    region_name=get_env_variable('AWS_DEFAULT_REGION')
)

# --- Variables de Entorno Limpias ---
CLIENT_ID = get_env_variable('COGNITO_CLIENT_ID')
CLIENT_SECRET = get_env_variable('COGNITO_CLIENT_SECRET')
COGNITO_DOMAIN = get_env_variable('COGNITO_DOMAIN')
REDIRECT_URI = get_env_variable('COGNITO_REDIRECT_URI')
TABLE_NAME = get_env_variable('DYNAMODB_TABLE_NAME', 'user_participations')

# --- MIDDLEWARE ANTI-CACHÉ ---
@app.after_request
def add_cache_control_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# --- Funciones de Utilidad y Lógica de Negocio ---
def get_user_from_session():
    id_token = session.get('id_token')
    if not id_token: return None
    try:
        _, payload_b64, _ = id_token.split('.')
        payload_b64 += '=' * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception: return None

def normalize_rut(rut):
    if not rut:
        return ""
    return re.sub(r'[^0-9kK]', '', str(rut)).upper()

def extract_rut_from_image(image_path):
    try:
        logging.info(f"Iniciando extracción de RUT desde: {image_path}")
        original_image = cv2.imread(image_path)

        target_height = 1200
        scale_ratio = target_height / original_image.shape[0]
        width = int(original_image.shape[1] * scale_ratio)
        height = int(original_image.shape[0] * scale_ratio)
        resized_image = cv2.resize(original_image, (width, height), interpolation=cv2.INTER_LANCZOS4)

        for angle in [0, 90, 180, 270]:
            logging.info(f"Probando con rotación de {angle} grados...")
            
            if angle == 90:
                rotated_image = cv2.rotate(resized_image, cv2.ROTATE_90_CLOCKWISE)
            elif angle == 180:
                rotated_image = cv2.rotate(resized_image, cv2.ROTATE_180)
            elif angle == 270:
                rotated_image = cv2.rotate(resized_image, cv2.ROTATE_90_COUNTERCLOCKWISE)
            else:
                rotated_image = resized_image

            gray_image = cv2.cvtColor(rotated_image, cv2.COLOR_BGR2GRAY)
            denoised_image = cv2.medianBlur(gray_image, 3)
            thresh_image = cv2.adaptiveThreshold(denoised_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 4)

            custom_config = r'--oem 3 --psm 11'
            text = pytesseract.image_to_string(thresh_image, config=custom_config, lang='spa')
            logging.info(f"Texto extraído (rotación {angle}°): \"{text[:200].replace('\n', ' ')}...\"")

            anchor_match = re.search(r'R[Uu][Nn]|RUT|C[eé]dula|C[Ii]v[Ii][Ll]', text, re.IGNORECASE)
            text_to_search = text

            if anchor_match:
                logging.info(f"Ancla encontrada ('{anchor_match.group(0)}'). Buscando RUT cerca.")
                text_to_search = text[anchor_match.start():anchor_match.start() + 200]

            rut_pattern = r'(\d{1,2}[-., ]?\d{3}[-., ]?\d{3}[-., ]?[dkK\d])'
            matches = re.findall(rut_pattern, text_to_search)

            if matches:
                for potential_rut in matches:
                    normalized = normalize_rut(potential_rut)
                    if 8 <= len(normalized) <= 9:
                        logging.info(f"RUT válido encontrado: '{normalized}' (extraído de '{potential_rut}')")
                        return normalized

        logging.warning("No se encontró un RUT procesable en ninguna orientación.")
        return None

    except Exception as e:
        logging.error(f"Error catastrófico durante el pipeline de OCR: {e}", exc_info=True)
        return None
def save_and_get_url(file, user_sub):
    if not file or not file.filename:
        logging.warning("Llamada a save_and_get_url sin archivo.")
        return None, "No se proporcionó ningún archivo o el archivo no tiene nombre"
    
    filename = secure_filename(f"{user_sub}_{datetime.utcnow().timestamp()}_{file.filename}")
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    logging.info(f"Intentando guardar el archivo en: {path}")
    
    try:
        file.save(path)
        url = url_for('static', filename=f'uploads/{filename}')
        logging.info(f"Archivo guardado con éxito. URL: {url}, Path: {path}")
        return url, path
    except Exception as e:
        logging.error(f"Error al guardar el archivo en '{path}': {e}", exc_info=True)
        return None, f"Error interno al intentar guardar el archivo."
def get_pending_units(user_attributes):
    if not user_attributes or 'sub' not in user_attributes:
        return [], [], []

    cognito_units_str = user_attributes.get('custom:Unidad', '')
    cognito_types_str = user_attributes.get('custom:TipoUnidad', '')
    
    unit_numbers = [u.strip() for u in cognito_units_str.split(',') if u.strip()]
    unit_types = [t.strip() for t in cognito_types_str.split(',') if t.strip()]

    if len(unit_numbers) > 1 and len(unit_types) == 1:
        unit_types = unit_types * len(unit_numbers)

    if len(unit_numbers) != len(unit_types):
        logging.error(f"Discordancia irreparable en datos de Cognito para usuario {user_attributes.get('sub')}: Unidades: {len(unit_numbers)}, Tipos: {len(unit_types)}")
        return [], [], []

    all_units_structured = [{'tipo_unidad': type, 'unidad': num} for type, num in zip(unit_types, unit_numbers)]
    
    if not all_units_structured:
        return [], [], []

    voted_units_keys = set()
    try:
        paginator = dynamodb_client.get_paginator('query')
        pages = paginator.paginate(
            TableName=TABLE_NAME,
            KeyConditionExpression='cognito_sub = :sub',
            ExpressionAttributeValues={":sub": {'S': user_attributes.get('sub')}},
            ConsistentRead=True
        )
        for page in pages:
            for item in page.get('Items', []):
                if 'unidad' in item and 'S' in item['unidad']:
                    voted_units_keys.add(item['unidad']['S'])
    except ClientError as e:
        logging.error(f"Error de DynamoDB al obtener unidades votadas: {e}")
        return all_units_structured, [], all_units_structured

    pending_structured = [u for u in all_units_structured if u['unidad'] not in voted_units_keys]
    pending_structured.sort(key=lambda x: (x['tipo_unidad'], x['unidad']))
    
    voted_structured = [u for u in all_units_structured if u['unidad'] in voted_units_keys]
    voted_structured.sort(key=lambda x: (x['tipo_unidad'], x['unidad']))
    
    return pending_structured, voted_structured, all_units_structured

# --- Rutas de Flask ---
@app.route('/')
def index():
    user = get_user_from_session()
    if not user:
        return render_template('index.html', user=None)

    pending_units, voted_units, all_units = get_pending_units(user)

    if not all_units:
        return render_template('index.html', user=user, has_no_units=True)

    if not pending_units:
        return render_template('index.html', user=user, user_has_voted=True, voted_units=voted_units)
    
    else:
        return redirect(url_for('form'))

@app.route('/login')
def login():
    scopes = "openid+email+profile"
    cognito_login_url = f"https://{COGNITO_DOMAIN}/login?client_id={CLIENT_ID}&response_type=code&scope={scopes}&redirect_uri={REDIRECT_URI}&ui_locales=es&lang=es"
    return redirect(cognito_login_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        error = request.args.get('error')
        error_description = request.args.get('error_description')
        if error:
            flash(f"Error de Cognito: {error} - {error_description}", "danger")
        return redirect(url_for('index'))

    token_url = f"https://{COGNITO_DOMAIN}/oauth2/token"

    auth_str = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_b64 = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {auth_b64}'
    }

    payload = {
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI,
        'code': code,
        'client_id': CLIENT_ID
    }

    try:
        response = requests.post(token_url, headers=headers, data=payload)
        response.raise_for_status()
        tokens = response.json()
        session['id_token'] = tokens['id_token']
        session['access_token'] = tokens['access_token']
    except requests.exceptions.RequestException as e:
        error_details = ""
        if e.response is not None:
            error_details = e.response.text
        flash(f"Error de comunicación con el servicio de autenticación. Detalles: {error_details}", "danger")
        
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    logout_uri = url_for('callback', _external=True)
    cognito_logout_url = f"https://{COGNITO_DOMAIN}/logout?client_id={CLIENT_ID}&logout_uri={logout_uri}"
    return redirect(cognito_logout_url)

@app.route('/form')
def form():
    user = get_user_from_session()
    if not user:
        return redirect(url_for('login'))

    pending_units, voted_units, all_units = get_pending_units(user)

    if not all_units: 
        flash("No tiene unidades asignadas para votar. Por favor, contacte al administrador.", "warning")
        return redirect(url_for('index'))

    if not pending_units:
        flash("Ya has completado tu votación para todas tus unidades.", "info")
        return redirect(url_for('index'))

    return render_template('form.html', user=user, pending_units=pending_units, voted_units=voted_units)

@app.route('/validate_rut', methods=['POST'])
def validate_rut():
    try:
        logging.info("Iniciando /validate_rut.")
        user = get_user_from_session()
        if not user:
            logging.warning("Acceso no autorizado a /validate_rut (sin sesión).")
            return jsonify({'error': 'No autorizado'}), 401

        user_sub = user.get('sub')
        logging.info(f"Petición de validación para el usuario: {user_sub}")

        if 'id_frontal' not in request.files:
            logging.error("Petición a /validate_rut no contiene 'id_frontal' en request.files.")
            return jsonify({'error': 'Falta la imagen frontal del carnet (campo id_frontal).'}), 400

        img_frontal_file = request.files['id_frontal']
        img_trasera_file = request.files.get('id_trasera')
        logging.info(f"Archivo frontal recibido: '{img_frontal_file.filename}', Trasera: '{img_trasera_file.filename if img_trasera_file else 'N/A'}'")

        user_rut_cognito = normalize_rut(user.get('custom:Rut'))
        logging.info(f"RUT del usuario en Cognito: {user_rut_cognito}")

        url_frontal, result_frontal = save_and_get_url(img_frontal_file, user_sub)
        if not url_frontal:
            logging.error(f"Falló el guardado de la imagen frontal. Motivo: {result_frontal}")
            return jsonify({'error': result_frontal}), 500
        path_frontal = result_frontal

        url_trasera, _ = save_and_get_url(img_trasera_file, user_sub)

        extracted_rut = extract_rut_from_image(path_frontal)
        
        rut_match_success = bool(extracted_rut and extracted_rut == user_rut_cognito)
        logging.info(f"Resultado de la comparación de RUT: {rut_match_success} (Extraído: {extracted_rut}, Cognito: {user_rut_cognito})")

        session['validation_data'] = {
            'rut_match_success': rut_match_success,
            'rut_detectado_imagen': extracted_rut or 'No detectado',
            'url_img_frontal': url_frontal,
            'url_img_trasera': url_trasera or 'N/A'
        }
        session.modified = True
        logging.info(f"Datos de validación guardados en la sesión: {session['validation_data']}")
        
        return jsonify({
            'success': True,
            'rut_match': rut_match_success,
            'extracted_rut': extracted_rut or 'No se pudo extraer el RUT.',
            'user_rut': user_rut_cognito
        })
    except Exception as e:
        logging.error(f"Error no controlado en /validate_rut: {e}", exc_info=True)
        return jsonify({'error': 'Ocurrió un error inesperado en el servidor.'}), 500

@app.route('/save_data', methods=['POST'])
def save_data():
    user = get_user_from_session()
    if not user: return jsonify({'error': 'No autorizado'}), 401

    pending_units, _, _ = get_pending_units(user) 
    if not pending_units:
        return jsonify({'success': True, 'message': 'Tu voto ya ha sido registrado para todas las unidades.'})

    data = request.json
    validation_data = session.pop('validation_data', {})
    try:
        transaction_items = []
        for unit_data in pending_units:
            item = {
                'cognito_sub': {'S': user.get('sub')},
                'username': {'S': user.get('cognito:username', 'N/A')},
                'nombre': {'S': user.get('custom:Nombre', 'N/A')},
                'rut': {'S': user.get('custom:Rut', 'N/A')},
                'email': {'S': user.get('email', 'N/A')},
                
                'unidad': {'S': unit_data['unidad']},
                'tipo_unidad': {'S': unit_data['tipo_unidad']},
                'comunidad': {'S': user.get('custom:Comunidad', 'N/A')},
                'decision_reglamento': {'S': data.get('final_answer', 'N/A').title()},
                'timestamp_votacion': {'S': datetime.utcnow().isoformat()},
                
                'rut_match_success': {'BOOL': validation_data.get('rut_match_success', False)},
                'rut_detectado_imagen': {'S': validation_data.get('rut_detectado_imagen', 'N/A')},
                'url_img_frontal': {'S': validation_data.get('url_img_frontal', 'N/A')},
                'url_img_trasera': {'S': validation_data.get('url_img_trasera', 'N/A')}
            }
            transaction_items.append({
                'Put': {
                    'TableName': TABLE_NAME,
                    'Item': item,
                    'ConditionExpression': 'attribute_not_exists(cognito_sub) AND attribute_not_exists(unidad)'
                }
            })

        if transaction_items:
            dynamodb_client.transact_write_items(TransactItems=transaction_items)
        
        voted_units_list = [f"- {unit['tipo_unidad']} {unit['unidad']}" for unit in pending_units]
        voted_units_str = "\n".join(voted_units_list)
        
        success_message = (
            "¡Gracias por participar! Tu voto ha sido guardado con éxito para las siguientes unidades:\n\n"
            f"{voted_units_str}"
        )
        
        return jsonify({'success': True, 'message': success_message})

    except ClientError as e:
        if 'TransactionCanceledException' in str(e):
            return jsonify({'success': True, 'message': 'Tu voto ya ha sido registrado.'})
        else:
            logging.error(f"Error de AWS al guardar: {e}", exc_info=True)
            return jsonify({'error': f'Error de base de datos: {e.response["Error"]["Message"]}'}), 500
    except Exception as e:
        logging.error(f"Error inesperado al guardar: {e}", exc_info=True)
        return jsonify({'error': f'Ha ocurrido un error inesperado: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
