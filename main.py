
import os
import re
import boto3
import json
import requests
import base64
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

load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.jinja_env.add_extension('jinja2.ext.do')
app.secret_key = os.urandom(24)

# --- Configuraciones ---
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Función para obtener y limpiar variables de entorno ---
def get_env_variable(var_name, default=None):
    value = os.getenv(var_name, default)
    if isinstance(value, str):
        return value.strip()
    return value

# --- Clientes de Servicios AWS ---
dynamodb_client = boto3.client(
    'dynamodb',
    aws_access_key_id=get_env_variable('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=get_env_variable('AWS_SECRET_ACCESS_KEY'),
    region_name=get_env_variable('AWS_DEFAULT_REGION')
)

# --- Variables de Entorno Limpias ---
CLIENT_ID = get_env_variable('COGNITO_CLIENT_ID')
CLIENT_SECRET = get_env_variable('COGNITO_CLIENT_SECRET')
COGNITO_DOMAIN = get_env_variable('COGNITO_DOMAIN')
REDIRECT_URI = get_env_variable('COGNITO_REDIRECT_URI')
TABLE_NAME = get_env_variable('DYNAMODB_TABLE_NAME', 'user_participations')
APP_BASE_URL = get_env_variable('APP_BASE_URL')


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

def get_pending_units(user_attributes):
    if not user_attributes or 'sub' not in user_attributes:
        return []

    cognito_units_str = user_attributes.get('custom:Unidad', '')
    cognito_types_str = user_attributes.get('custom:TipoUnidad', '')
    
    unit_numbers = [u.strip() for u in cognito_units_str.split(',') if u.strip()]
    unit_types = [t.strip() for t in cognito_types_str.split(',') if t.strip()]

    if len(unit_numbers) != len(unit_types):
        print("Error: La cantidad de unidades y tipos de unidad no coincide.")
        return []

    all_units_structured = [{'tipo_unidad': type, 'unidad': num} for type, num in zip(unit_types, unit_numbers)]
    
    if not all_units_structured:
        return []

    voted_units = set()
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
                    voted_units.add(item['unidad']['S'])
    except ClientError as e:
        print(f"Error de DynamoDB al obtener unidades votadas: {e}")
        return []

    pending_structured = [u for u in all_units_structured if u['unidad'] not in voted_units]
    pending_structured.sort(key=lambda x: (x['tipo_unidad'], x['unidad']))
    return pending_structured

# --- Rutas de Flask ---
@app.route('/')
def index():
    user = get_user_from_session()
    if not user:
        return render_template('index.html', user=None, user_has_voted=False)

    pending_units = get_pending_units(user)
    if not pending_units:
        return render_template('index.html', user=user, user_has_voted=True)
    else:
        return redirect(url_for('form'))

@app.route('/login')
def login():
    scopes = "openid+email+profile"
    cognito_login_url = f"https://{COGNITO_DOMAIN}/login?client_id={CLIENT_ID}&response_type=code&scope={scopes}&redirect_uri={REDIRECT_URI}"
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
    logout_uri = APP_BASE_URL
    cognito_logout_url = f"https://{COGNITO_DOMAIN}/logout?client_id={CLIENT_ID}&logout_uri={logout_uri}"
    return redirect(cognito_logout_url)

@app.route('/form')
def form():
    user = get_user_from_session()
    if not user:
        return redirect(url_for('login'))

    pending_units = get_pending_units(user)
    if not pending_units:
        flash("Ya has completado tu votación para todas tus unidades.", "info")
        return redirect(url_for('index'))

    return render_template('form.html', user=user, pending_units=pending_units)

@app.route('/save_data', methods=['POST'])
def save_data():
    user = get_user_from_session()
    if not user: return jsonify({'error': 'No autorizado'}), 401

    pending_units = get_pending_units(user)
    if not pending_units:
        return jsonify({'success': True, 'message': 'Tu voto ya ha sido registrado para todas las unidades.'})

    data = request.json
    try:
        transaction_items = []
        for unit_data in pending_units:
            item = {
                'cognito_sub': {'S': user.get('sub')},
                'unidad': {'S': unit_data['unidad']},
                'tipo_unidad': {'S': unit_data['tipo_unidad']},
                'timestamp_votacion': {'S': datetime.utcnow().isoformat()},
                'nombre': {'S': user.get('custom:Nombre', 'N/A')},
                'rut': {'S': user.get('custom:Rut', 'N/A')},
                'email': {'S': user.get('email', 'N/A')},
                'comunidad': {'S': user.get('custom:Comunidad', 'N/A')},
                'decision_reglamento': {'S': data.get('final_answer', 'N/A')}
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
        
        return jsonify({'success': True, 'message': '¡Gracias por participar! Tu voto ha sido guardado con éxito.'})

    except ClientError as e:
        if 'TransactionCanceledException' in str(e):
            return jsonify({'success': True, 'message': 'Tu voto ya ha sido registrado.'})
        else:
            return jsonify({'error': f'Error de base de datos: {e.response["Error"]["Message"]}'}), 500
    except Exception as e:
        return jsonify({'error': f'Ha ocurrido un error inesperado: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
