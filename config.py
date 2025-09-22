
import os
import boto3
import json
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# --- Entorno de la Aplicación ---
# Usamos FLASK_ENV. Si no existe, asumimos 'development' (local).
ENVIRONMENT = os.getenv('FLASK_ENV', 'development')

# --- Variables de Configuración (inicializadas a None) ---
SECRET_KEY = None
S3_BUCKET_NAME = None
AWS_DEFAULT_REGION = None
COGNITO_USER_POOL_ID = None
APP_URL = None
SES_FROM_EMAIL_ADDRESS = None
COGNITO_CLIENT_ID = None
COGNITO_CLIENT_SECRET = None
COGNITO_DOMAIN = None
COGNITO_REDIRECT_URI = None
DYNAMODB_TABLE_NAME = None

# --- Lógica de Carga de Configuración ---

if ENVIRONMENT == 'production':
    # --- MODO PRODUCCIÓN: Cargar desde AWS Secrets Manager ---
    print("INFO: Running in PRODUCTION mode. Loading config from AWS Secrets Manager.")
    secret_name = "PrototipoEncuestasSecret" 
    region_name = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=region_name)

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        secret_string = get_secret_value_response['SecretString']
        secrets = json.loads(secret_string)

        # Carga de todas las variables desde el secreto de AWS
        SECRET_KEY = secrets.get('SECRET_KEY')
        S3_BUCKET_NAME = secrets.get('S3_BUCKET_NAME')
        AWS_DEFAULT_REGION = secrets.get('AWS_DEFAULT_REGION', region_name)
        COGNITO_USER_POOL_ID = secrets.get('COGNITO_USER_POOL_ID')
        APP_URL = secrets.get('APP_URL')
        SES_FROM_EMAIL_ADDRESS = secrets.get('SES_FROM_EMAIL_ADDRESS')
        COGNITO_CLIENT_ID = secrets.get('COGNITO_CLIENT_ID')
        COGNITO_CLIENT_SECRET = secrets.get('COGNITO_CLIENT_SECRET')
        COGNITO_DOMAIN = secrets.get('COGNITO_DOMAIN')
        COGNITO_REDIRECT_URI = secrets.get('COGNITO_REDIRECT_URI')
        DYNAMODB_TABLE_NAME = secrets.get('DYNAMODB_TABLE_NAME')
        
        print("INFO: Successfully loaded secrets from AWS Secrets Manager.")

    except ClientError as e:
        print(f"ERROR: Could not retrieve secrets from AWS. Error: {e}")
        raise e
else:
    # --- MODO DESARROLLO: Cargar desde archivo .env ---
    print("INFO: Running in DEVELOPMENT mode. Loading config from .env file.")
    load_dotenv()

    # Cargamos las variables del archivo .env
    SECRET_KEY = os.getenv('SECRET_KEY')
    S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
    AWS_DEFAULT_REGION = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
    COGNITO_USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
    APP_URL = os.getenv('APP_URL', 'http://127.0.0.1:5000')
    SES_FROM_EMAIL_ADDRESS = os.getenv('SENDER_EMAIL') or os.getenv('SES_FROM_EMAIL_ADDRESS')
    COGNITO_CLIENT_ID = os.getenv('COGNITO_CLIENT_ID')
    COGNITO_CLIENT_SECRET = os.getenv('COGNITO_CLIENT_SECRET')
    COGNITO_DOMAIN = os.getenv('COGNITO_DOMAIN')
    COGNITO_REDIRECT_URI = os.getenv('COGNITO_REDIRECT_URI')
    DYNAMODB_TABLE_NAME = os.getenv('DYNAMODB_TABLE_NAME')

# --- Verificación Final ---
# Aseguramos que todas las variables críticas existan después de la carga.
_CRITICAL_VARS = {
    "SECRET_KEY": SECRET_KEY,
    "S3_BUCKET_NAME": S3_BUCKET_NAME,
    "COGNITO_USER_POOL_ID": COGNITO_USER_POOL_ID,
    "SES_FROM_EMAIL_ADDRESS": SES_FROM_EMAIL_ADDRESS,
    "COGNITO_CLIENT_ID": COGNITO_CLIENT_ID,
    "COGNITO_CLIENT_SECRET": COGNITO_CLIENT_SECRET,
    "COGNITO_DOMAIN": COGNITO_DOMAIN,
    "COGNITO_REDIRECT_URI": COGNITO_REDIRECT_URI,
    "DYNAMODB_TABLE_NAME": DYNAMODB_TABLE_NAME
}

missing_vars = [key for key, value in _CRITICAL_VARS.items() if value is None]

if missing_vars:
    raise ValueError(f"CRITICAL ERROR: Missing essential configuration variables: {', '.join(missing_vars)}. Check your .env file or AWS Secrets Manager.")

print("INFO: Application configuration loaded successfully.")
