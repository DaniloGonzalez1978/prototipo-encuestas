
import os
import re
import boto3
import json
import requests
import base64
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from dotenv import load_dotenv
from datetime import datetime
from werkzeug.utils import secure_filename

# --- Nuevas librerías para procesamiento de imagen local ---
import cv2
import pytesseract
from PIL import Image
import numpy as np

load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Habilitar la extensión 'do' para poder usar {% do ... %} en las plantillas
app.jinja_env.add_extension('jinja2.ext.do')

app.secret_key = os.urandom(24)

# --- Configuraciones ---
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- AWS Client para DynamoDB ---
dynamodb_client = boto3.client(
    'dynamodb',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_DEFAULT_REGION')
)

# --- Environment Variables ---
CLIENT_ID = os.getenv('COGNITO_CLIENT_ID')
CLIENT_SECRET = os.getenv('COGNITO_CLIENT_SECRET')
COGNITO_DOMAIN = os.getenv('COGNITO_DOMAIN')
REDIRECT_URI = os.getenv('COGNITO_REDIRECT_URI')
DYNAMODB_TABLE_NAME = os.getenv('DYNAMODB_TABLE_NAME', 'user_participations')

# --- Utility Functions ---
def normalize_rut(rut_string):
    return rut_string.replace(".", "").upper() if rut_string else ""

def get_user_from_session():
    id_token = session.get('id_token')
    if not id_token: return None
    try:
        _, payload_b64, _ = id_token.split('.')
        payload_b64 += '=' * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception: return None

def find_rut_in_text(text_lines):
    rut_pattern = re.compile(r'\b(\d{1,2}[.]?\d{3}[.]?\d{3}-?[\dkK])\b')
    for line in text_lines:
        match = rut_pattern.search(line)
        if match: return match.group(1)
    return None

# --- Nueva Función de Procesamiento de Imagen ---
def crop_id_card(image_path, output_path):
    try:
        img = cv2.imread(image_path)
        if img is None:
            return None, "No se pudo cargar la imagen. Verifique que el archivo no esté corrupto y sea un formato de imagen válido."

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 75, 200)

        contours, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

        screenCnt = None
        for c in contours:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4:
                screenCnt = approx
                break

        if screenCnt is not None:
            x, y, w, h = cv2.boundingRect(screenCnt)
            cropped_img = img[y:y+h, x:x+w]
        else:
            if len(contours) > 0:
                c = contours[0] # Tomar el contorno más grande
                x, y, w, h = cv2.boundingRect(c)
                padding = 10
                x = max(0, x - padding)
                y = max(0, y - padding)
                w = min(img.shape[1] - x, w + 2 * padding)
                h = min(img.shape[0] - y, h + 2 * padding)
                cropped_img = img[y:y+h, x:x+w]
            else:
                cropped_img = img # Si no hay contornos, usar la imagen original

        cv2.imwrite(output_path, cropped_img)
        return output_path, None
    except Exception as e:
        return None, f"Ocurrió un error técnico al intentar recortar la imagen: {e}"

# --- Flask Routes ---
@app.route('/')
def index():
    return redirect(url_for('form')) if 'id_token' in session else render_template('index.html')

@app.route('/login')
def login():
    scopes = "openid+email+profile"
    cognito_login_url = f"https://{COGNITO_DOMAIN}/login?client_id={CLIENT_ID}&response_type=code&scope={scopes}&redirect_uri={REDIRECT_URI}"
    return redirect(cognito_login_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code: return redirect(url_for('index'))

    token_url = f"https://{COGNITO_DOMAIN}/oauth2/token"
    payload = {
        'grant_type': 'authorization_code', 'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET, 'redirect_uri': REDIRECT_URI, 'code': code
    }
    try:
        response = requests.post(token_url, data=payload)
        response.raise_for_status()
        tokens = response.json()
        session['id_token'] = tokens['id_token']
        session['access_token'] = tokens['access_token']

        session['login_timestamp'] = datetime.utcnow().isoformat()
        session['login_count'] = session.get('login_count', 0) + 1
        session['validation_attempts'] = 0

        return redirect(url_for('form'))
    except requests.exceptions.RequestException as e:
        return f"Error de comunicación con Cognito: {e}", 500

@app.route('/logout')
def logout():
    logout_uri = REDIRECT_URI.split('/callback')[0]
    cognito_logout_url = f"https://{COGNITO_DOMAIN}/logout?client_id={CLIENT_ID}&logout_uri={logout_uri}"
    session.clear()
    return redirect(cognito_logout_url)

@app.route('/signout')
def signout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/form')
def form():
    if 'id_token' not in session:
        return redirect(url_for('login'))
    user_attributes = get_user_from_session()
    if not user_attributes:
        return "Error de Sesión.", 500
    return render_template('form.html', user=user_attributes)

@app.route('/upload', methods=['POST'])
def upload():
    if 'id_token' not in session: return jsonify({'error': 'No autorizado'}), 401
    if 'file_front' not in request.files or 'file_back' not in request.files:
        return jsonify({'error': 'Faltan archivos.'})

    file_front = request.files['file_front']
    file_back = request.files['file_back']
    user = get_user_from_session()
    if not user: return jsonify({'error': 'Sesión expirada.', 'redirect': url_for('login')})

    rut_plain = normalize_rut(user.get('custom:Rut', 'unknown'))
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    filename_front = secure_filename(f"{rut_plain}_{timestamp}_front.jpg")
    filename_back = secure_filename(f"{rut_plain}_{timestamp}_back.jpg")
    filename_front_cropped = secure_filename(f"{rut_plain}_{timestamp}_front_cropped.jpg")

    path_front = os.path.join(app.config['UPLOAD_FOLDER'], filename_front)
    path_back = os.path.join(app.config['UPLOAD_FOLDER'], filename_back)
    path_front_cropped = os.path.join(app.config['UPLOAD_FOLDER'], filename_front_cropped)

    file_front.save(path_front)
    file_back.save(path_back)

    session['validation_attempts'] = session.get('validation_attempts', 0) + 1

    try:
        cropped_image_path, crop_error = crop_id_card(path_front, path_front_cropped)
        if crop_error:
             return jsonify({'error': crop_error, 'success': False})

        if not cropped_image_path:
             return jsonify({'error': 'La ruta de la imagen recortada no se generó por una razón desconocida.', 'success': False})

        try:
            text_from_image = pytesseract.image_to_string(Image.open(cropped_image_path), lang='spa')
        except pytesseract.TesseractNotFoundError:
            return jsonify({'error': 'Error de configuración del servidor: Tesseract no fue encontrado. Contacte a soporte.', 'success': False})
        except Exception as e:
            return jsonify({'error': f'No se pudo leer el texto de la imagen procesada: {e}', 'success': False})

        text_lines = text_from_image.split('\n')
        rut_from_image = find_rut_in_text(text_lines)

        if not rut_from_image:
            return jsonify({
                'success': False, 'match': False,
                'error': 'No se pudo encontrar un RUT válido en la imagen. Intente con una foto mejor iluminada y enfocada.',
                'image_front_url': url_for('static', filename=f'uploads/{filename_front_cropped}'),
                'image_back_url': url_for('static', filename=f'uploads/{filename_back}')
            })

        is_match = normalize_rut(rut_from_image) == rut_plain
        message = 'El RUT del documento coincide.' if is_match else 'El RUT del documento NO coincide.'

        return jsonify({
            'success': True, 'message': message, 'match': is_match,
            'rut_from_image': rut_from_image, 'rut_from_cognito': user.get('custom:Rut'),
            'image_front_url': url_for('static', filename=f'uploads/{filename_front_cropped}'),
            'image_back_url': url_for('static', filename=f'uploads/{filename_back}')
        })

    except Exception as e:
        return jsonify({'error': f'Error general en el proceso de carga: {e}', 'success': False})

@app.route('/save_data', methods=['POST'])
def save_data():
    if 'id_token' not in session: return jsonify({'error': 'No autorizado'}), 401

    data = request.json
    user = get_user_from_session()
    if not user: return jsonify({'error': 'Sesión expirada.'}), 401

    try:
        item_to_save = {
            'cognito_sub': {'S': user.get('sub')},
            'timestamp_votacion': {'S': datetime.utcnow().isoformat()},
            'nombre': {'S': user.get('custom:Nombre', 'N/A')},
            'rut': {'S': user.get('custom:Rut', 'N/A')},
            'email': {'S': user.get('email', 'N/A')},
            'comunidad': {'S': user.get('custom:Comunidad', 'N/A')},
            'unidad': {'S': user.get('custom:Unidad', 'N/A')},
            'decision_reglamento': {'S': data.get('final_answer', 'N/A')},
            'rut_match_success': {'BOOL': data.get('match', False)},
            'rut_detectado_imagen': {'S': data.get('rut_from_image', 'N/A')},
            'tiempo_validacion_seg': {'N': str(data.get('validation_duration', 0))},
            'url_img_frontal': {'S': data.get('image_front_url', 'N/A')},
            'url_img_trasera': {'S': data.get('image_back_url', 'N/A')},
            'timestamp_login': {'S': session.get('login_timestamp', 'N/A')},
            'contador_logins': {'N': str(session.get('login_count', 0))},
            'intentos_validacion_rut': {'N': str(session.get('validation_attempts', 0))}
        }

        dynamodb_client.put_item(TableName=DYNAMODB_TABLE_NAME, Item=item_to_save)
        return jsonify({'success': True, 'message': 'Participación guardada.'})

    except Exception as e:
        return jsonify({'error': f'No se pudo guardar la participación: {e}'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
