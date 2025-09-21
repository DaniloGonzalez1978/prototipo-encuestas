
import os
import re
import boto3
import json
import requests
import base64
import logging
import time
import tempfile
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from dotenv import load_dotenv
from datetime import datetime
from werkzeug.utils import secure_filename
from botocore.exceptions import ClientError

# --- Librerías de Procesamiento de Imagen ---
import cv2
import pytesseract
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

# --- Variables de AWS ---
S3_BUCKET_NAME = get_env_variable('S3_BUCKET_NAME')
AWS_REGION = get_env_variable('AWS_DEFAULT_REGION', 'us-east-1')
SENDER_EMAIL = get_env_variable('SENDER_EMAIL')

if not S3_BUCKET_NAME or not SENDER_EMAIL:
    raise ValueError("Se deben configurar S3_BUCKET_NAME y SENDER_EMAIL en las variables de entorno.")

# --- Clientes de Servicios AWS ---
dynamodb_client = boto3.client('dynamodb', region_name=AWS_REGION)
s3_client = boto3.client('s3', region_name=AWS_REGION)
ses_client = boto3.client('ses', region_name=AWS_REGION)

# --- Variables de Entorno Limpias ---
CLIENT_ID = get_env_variable('COGNITO_CLIENT_ID')
CLIENT_SECRET = get_env_variable('COGNITO_CLIENT_SECRET')
COGNITO_DOMAIN = get_env_variable('COGNITO_DOMAIN')
REDIRECT_URI = get_env_variable('COGNITO_REDIRECT_URI')
TABLE_NAME = get_env_variable('DYNAMODB_TABLE_NAME', 'user_participations')

# --- MIDDLEWARE ---
@app.after_request
def add_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    response.headers['Accept-CH'] = 'Sec-CH-UA, Sec-CH-UA-Mobile, Sec-CH-UA-Platform, Sec-CH-UA-Arch, Sec-CH-UA-Model'
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
    if not rut: return ""
    return re.sub(r'[^0-9kK]', '', str(rut)).upper()

def save_and_get_url(file, base_filename):
    if not file or not file.filename: return None, "No se proporcionó ningún archivo"
    _, extension = os.path.splitext(file.filename)
    filename = secure_filename(f"{base_filename}_{int(datetime.utcnow().timestamp())}{extension}")
    s3_key = f"uploads/{filename}"
    try:
        s3_client.upload_fileobj(file, S3_BUCKET_NAME, s3_key, ExtraArgs={'ContentType': file.content_type})
        url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
        logging.info(f"Archivo subido a S3 como '{s3_key}'. URL: {url}")
        return url, s3_key
    except ClientError as e:
        logging.error(f"Error al subir a S3: {e}", exc_info=True)
        return None, "Error interno al guardar el archivo en S3."

def _find_rut_from_text_block(text_block):
    rut_pattern = r'(\d{1,2}[., ]?\d{3}[., ]?\d{3}[- ]?[dkK\d])'
    matches = re.findall(rut_pattern, text_block)
    for potential_rut in matches:
        normalized = normalize_rut(potential_rut)
        if 8 <= len(normalized) <= 9: return normalized
    return None

def extract_rut_from_image(s3_key):
    with tempfile.TemporaryDirectory() as temp_dir:
        local_path = os.path.join(temp_dir, os.path.basename(s3_key))
        try:
            s3_client.download_file(S3_BUCKET_NAME, s3_key, local_path)
            image = cv2.imread(local_path)
            if image is None: return None
            for angle in [0, 90, 180, 270]:
                rotated = image if angle == 0 else cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE if angle == 90 else (cv2.ROTATE_180 if angle == 180 else cv2.ROTATE_90_COUNTERCLOCKWISE))
                gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)
                resized = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                _, processed = cv2.threshold(cv2.GaussianBlur(resized, (5, 5), 0), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                text = pytesseract.image_to_string(processed, lang='spa', config='--oem 3 --psm 3')
                if (rut := _find_rut_from_text_block(text)): return rut
            return None
        except Exception as e:
            logging.error(f"Error en pipeline de OCR: {e}", exc_info=True)
            return None

def send_vote_confirmation_email(user_info, vote_details):
    recipient_email = user_info.get('email')
    if not recipient_email: return
    comunidad = user_info.get('custom:Comunidad', 'Comunidad')
    nombre = user_info.get('custom:Nombre', 'vecino/a')
    decision = vote_details['decision'].title()
    unidades = ", ".join([u['unidad'] for u in vote_details['units']])
    subject = f"Confirmación de tu Voto - {comunidad}"
    body_html = f"""<html><body><h2>¡Gracias por tu participación, {nombre}!</h2>
      <p>Hemos registrado tu voto para la comunidad <b>{comunidad}</b>.</p>
      <p><b>Detalles:</b></p><ul><li><b>Unidades:</b> {unidades}</li><li><b>Decisión:</b> {decision}</li>
        <li><b>Fecha/Hora:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</li></ul></body></html>"""
    try:
        ses_client.send_email(Source=SENDER_EMAIL, Destination={'ToAddresses': [recipient_email]},
                              Message={'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                                       'Body': {'Html': {'Data': body_html, 'Charset': 'UTF-8'}}})
        logging.info(f"Correo de confirmación enviado a {recipient_email}")
    except ClientError as e: logging.error(f"Error con SES: {e}", exc_info=True)

def get_pending_units(user_attrs, consistent_read=False):
    if not user_attrs: return [], [], []
    units = [u.strip() for u in user_attrs.get('custom:Unidad', '').split(',') if u.strip()]
    types = [t.strip() for t in user_attrs.get('custom:TipoUnidad', '').split(',') if t.strip()]
    if len(units) > 1 and len(types) == 1: types *= len(units)
    all_units = [{'tipo_unidad': t, 'unidad': u} for t, u in zip(types, units)]
    voted_keys = set()
    try:
        paginator = dynamodb_client.get_paginator('query')
        for page in paginator.paginate(TableName=TABLE_NAME, KeyConditionExpression='cognito_sub = :sub',
                                     ExpressionAttributeValues={":sub": {'S': user_attrs.get('sub')}}, ConsistentRead=consistent_read):
            voted_keys.update(item['unidad']['S'] for item in page.get('Items', []) if 'unidad' in item)
    except ClientError as e: logging.error(f"Error de DynamoDB: {e}")
    pending = sorted([u for u in all_units if u['unidad'] not in voted_keys], key=lambda x: x['unidad'])
    voted = sorted([u for u in all_units if u['unidad'] in voted_keys], key=lambda x: x['unidad'])
    return pending, voted, all_units

@app.route('/')
def index():
    user = get_user_from_session()
    if not user: return render_template('index.html', user=None)
    if 'voto_recien_emitido' in session:
        return render_template('index.html', user=user, user_has_voted=True, voted_units=session.pop('voto_recien_emitido'))
    pending, voted, all_units = get_pending_units(user, consistent_read=True)
    if not all_units: return render_template('index.html', user=user, has_no_units=True)
    if not pending: return render_template('index.html', user=user, user_has_voted=True, voted_units=voted)
    return redirect(url_for('form'))

@app.route('/login')
def login():
    return redirect(f"https://{COGNITO_DOMAIN}/login?client_id={CLIENT_ID}&response_type=code&scope=openid+email+profile&redirect_uri={REDIRECT_URI}&ui_locales=es")

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code: return redirect(url_for('index'))
    auth_b64 = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode('utf-8')).decode('utf-8')
    try:
        res = requests.post(f"https://{COGNITO_DOMAIN}/oauth2/token", headers={'Authorization': f'Basic {auth_b64}', 'Content-Type': 'application/x-www-form-urlencoded'}, data={'grant_type': 'authorization_code', 'redirect_uri': REDIRECT_URI, 'code': code})
        res.raise_for_status()
        tokens = res.json()
        session.update(id_token=tokens['id_token'], access_token=tokens['access_token'], timestamp_login=datetime.utcnow().isoformat())
    except requests.RequestException as e: logging.error(f"Error con Cognito: {e}", exc_info=True)
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(f"https://{COGNITO_DOMAIN}/logout?client_id={CLIENT_ID}&logout_uri={url_for('callback', _external=True)}")

@app.route('/form')
def form():
    user = get_user_from_session()
    if not user: return redirect(url_for('login'))
    pending, voted, _ = get_pending_units(user, consistent_read=True)
    if not pending: return redirect(url_for('index'))
    return render_template('form.html', user=user, pending_units=pending, voted_units=voted)

# --- RUTA CORREGIDA ---    
@app.route('/validate_rut', methods=['POST'])
def validate_rut():
    user = get_user_from_session()
    # 1. AMBAS IMÁGENES SON OBLIGATORIAS
    if not user or 'id_frontal' not in request.files or 'id_trasera' not in request.files:
        return jsonify({'error': 'No autorizado o faltan imágenes (frontal o trasera).'}), 400
    
    start_time = time.time()
    user_rut_norm = normalize_rut(user.get('custom:Rut'))
    rut_filename = re.sub(r'[^0-9]', '', user_rut_norm)

    # Subir imagen frontal
    url_frontal, s3_key_frontal = save_and_get_url(request.files['id_frontal'], f"{rut_filename}_frontal")
    if not url_frontal: return jsonify({'error': s3_key_frontal}), 500

    # Subir imagen trasera
    url_trasera, _ = save_and_get_url(request.files['id_trasera'], f"{rut_filename}_trasera")
    if not url_trasera: return jsonify({'error': 'Error al guardar la imagen trasera.'}), 500

    # Extraer RUT y comparar
    extracted_rut = extract_rut_from_image(s3_key_frontal)
    rut_match = bool(extracted_rut and extracted_rut == user_rut_norm)
    
    # Guardar estadísticas de validación en sesión
    rut_stats = session.get('rut_validation_stats', {})
    rut_stats['cantidad_intentos_rut'] = rut_stats.get('cantidad_intentos_rut', 0) + 1
    rut_stats['timestamp_validacion'] = datetime.utcnow().isoformat()
    rut_stats['tiempo_deteccion_rut'] = time.time() - start_time
    session['rut_validation_stats'] = rut_stats

    # Guardar datos de validación en sesión
    session['validation_data'] = {
        'rut_match_success': rut_match,
        'rut_detectado_imagen': extracted_rut or 'No detectado',
        'url_img_frontal': url_frontal,
        'url_img_trasera': url_trasera
    }
    session.modified = True

    # 2. RESPUESTA JSON CORREGIDA PARA EL FRONTEND
    return jsonify({
        'success': True, 
        'rut_match': rut_match,
        'extracted_rut': extracted_rut or 'No detectado',
        'user_rut': user_rut_norm
    })


@app.route('/save_data', methods=['POST'])
def save_data():
    user = get_user_from_session()
    if not user: return jsonify({'error': 'No autorizado'}), 401
    
    pending, _, _ = get_pending_units(user, consistent_read=True)
    if not pending: return jsonify({'success': True, 'message': 'Voto ya registrado.'})

    data = request.json
    validation_data = session.pop('validation_data', {})
    rut_stats = session.pop('rut_validation_stats', {})
    
    sec_ch_ua_mobile = request.headers.get('Sec-CH-UA-Mobile', '')
    device_type = "Mobile" if sec_ch_ua_mobile == "?1" else "Desktop"

    try:
        items = []
        for unit in pending:
            item = {
                'cognito_sub': {'S': user.get('sub')},
                'username': {'S': user.get('cognito:username', 'N/A')},
                'nombre': {'S': user.get('custom:Nombre', 'N/A')},
                'rut': {'S': user.get('custom:Rut', 'N/A')},
                'email': {'S': user.get('email', 'N/A')},
                'unidad': {'S': unit['unidad']},
                'tipo_unidad': {'S': unit['tipo_unidad']},
                'comunidad': {'S': user.get('custom:Comunidad', 'N/A')},
                'decision_reglamento': {'S': data.get('final_answer', 'N/A').title()},
                'timestamp_votacion': {'S': datetime.utcnow().isoformat()},
                'rut_match_success': {'BOOL': validation_data.get('rut_match_success', False)},
                'rut_detectado_imagen': {'S': validation_data.get('rut_detectado_imagen', 'N/A')},
                'url_img_frontal': {'S': validation_data.get('url_img_frontal', 'N/A')},
                'url_img_trasera': {'S': validation_data.get('url_img_trasera', 'N/A')},
                'timestamp_login': {'S': session.get('timestamp_login', 'N/A')},
                'timestamp_validacion': {'S': rut_stats.get('timestamp_validacion', 'N/A')},
                'cantidad_intentos_rut': {'N': str(rut_stats.get('cantidad_intentos_rut', 1))},
                'tiempo_deteccion_rut': {'N': str(round(rut_stats.get('tiempo_deteccion_rut', 0), 2))},
                'ip_address': {'S': request.headers.get('X-Forwarded-For', request.remote_addr)},
                'user_agent': {'S': request.user_agent.string},
                'accept_language': {'S': request.headers.get('Accept-Language', 'N/A')},
                'device_type': {'S': device_type},
                'sec_ch_ua': {'S': request.headers.get('Sec-CH-UA', 'N/A')},
                'sec_ch_ua_arch': {'S': request.headers.get('Sec-CH-UA-Arch', 'N/A')},
                'sec_ch_ua_model': {'S': request.headers.get('Sec-CH-UA-Model', 'N/A')},
                'sec_ch_ua_platform': {'S': request.headers.get('Sec-CH-UA-Platform', 'N/A')}
            }
            items.append({'Put': {'TableName': TABLE_NAME, 'Item': item, 'ConditionExpression': 'attribute_not_exists(cognito_sub) AND attribute_not_exists(unidad)'}})

        if items:
            dynamodb_client.transact_write_items(TransactItems=items)
            send_vote_confirmation_email(user, {'decision': data.get('final_answer', 'N/A'), 'units': pending})

        session['voto_recien_emitido'] = pending
        return jsonify({'success': True, 'message': '¡Voto guardado con éxito!'})

    except ClientError as e:
        if 'TransactionCanceledException' in str(e):
            _, voted, _ = get_pending_units(user, consistent_read=True)
            session['voto_recien_emitido'] = voted
            return jsonify({'success': True, 'message': 'Tu voto ya ha sido registrado.'})
        logging.error(f"Error de AWS: {e}", exc_info=True)
        return jsonify({'error': 'Error de base de datos.'}), 500
    except Exception as e:
        logging.error(f"Error inesperado: {e}", exc_info=True)
        return jsonify({'error': 'Error inesperado.'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
