import os
import csv
import boto3
from dotenv import load_dotenv
from botocore.exceptions import ClientError, NoCredentialsError

# --- Email Content ---
# Personaliza el asunto y el cuerpo de tu correo de invitación aquí.
# Puedes usar {name} y {app_url} como marcadores de posición.
EMAIL_SUBJECT = "¡Es hora de votar! Tu participación es importante."
EMAIL_HTML_BODY = """
<html>
<head></head>
<body>
  <h1>Hola {name},</h1>
  <p>Te invitamos a participar en el proceso de votación de nuestra comunidad.</p>
  <p>La votación estará abierta durante 7 días. Para emitir tu voto, por favor sigue el enlace a continuación:</p>
  <p><a href="{app_url}">Ir a la Aplicación de Votación</a></p>
  <p>Tu voz es fundamental para tomar las mejores decisiones para todos.</p>
  <p>¡Gracias por tu participación!</p>
  <br>
  <p>Saludos,</p>
  <p>El Equipo de la Comunidad</p>
</body>
</html>
"""
EMAIL_TEXT_BODY = """
Hola {name},

Te invitamos a participar en el proceso de votación de nuestra comunidad.

La votación estará abierta durante 7 días. Para emitir tu voto, por favor copia y pega el siguiente enlace en tu navegador:
{app_url}

Tu voz es fundamental para tomar las mejores decisiones para todos.

¡Gracias por tu participación!

Saludos,
El Equipo de la Comunidad
"""
# --- End of Email Content ---


def get_env_variable(var_name):
    """Obtiene una variable de entorno, eliminando espacios en blanco."""
    value = os.getenv(var_name)
    if isinstance(value, str):
        return value.strip()
    return value

def send_invitation_emails_from_csv(csv_file_path):
    """
    Lee un archivo CSV y envía un email de invitación a cada usuario listado usando SES.
    
    Requiere que las siguientes variables de entorno estén configuradas:
    - AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
    - SES_FROM_EMAIL_ADDRESS: La dirección de email verificada en SES para usar como remitente.
    - APP_URL: La URL de la aplicación de votación (ej. https://app.tu-dominio.com)
    
    El archivo CSV debe contener al menos las columnas 'name' y 'email'.
    """
    print(f"--- Iniciando el script de envío desde '{csv_file_path}' ---")
    
    load_dotenv()
    
    aws_region = get_env_variable("AWS_DEFAULT_REGION")
    from_email = get_env_variable("SES_FROM_EMAIL_ADDRESS")
    app_url = get_env_variable("APP_URL")
    
    if not all([aws_region, from_email, app_url]):
        print("\033[91mError: Faltan una o más variables de entorno requeridas (AWS_DEFAULT_REGION, SES_FROM_EMAIL_ADDRESS, APP_URL).\033[0m")
        return

    print(f"Región de AWS: {aws_region}")
    print(f"Email de remitente (SES): {from_email}")
    print(f"URL de la Aplicación: {app_url}")

    try:
        ses_client = boto3.client('ses', region_name=aws_region)
    except NoCredentialsError:
        print("\033[91mError: No se encontraron las credenciales de AWS. Asegúrate de que AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY estén configuradas.\033[0m")
        return

    try:
        with open(csv_file_path, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            users_to_email = list(reader)
    except FileNotFoundError:
        print(f"\033[91mError: No se encontró el archivo CSV en la ruta: {csv_file_path}\033[0m")
        return
    except Exception as e:
        print(f"\033[91mError al leer el archivo CSV: {e}\033[0m")
        return

    if not users_to_email:
        print("El archivo CSV está vacío o no contiene datos. Finalizando script.")
        return

    print(f"\nSe encontraron {len(users_to_email)} usuarios en el archivo CSV.")
    print("Enviando correos de invitación...")
    success_count = 0
    failure_count = 0

    for user in users_to_email:
        user_email = user.get('email')
        user_name = user.get('name', 'miembro de la comunidad')

        if user_email and '@' in user_email:
            try:
                personalized_html_body = EMAIL_HTML_BODY.format(name=user_name, app_url=app_url)
                personalized_text_body = EMAIL_TEXT_BODY.format(name=user_name, app_url=app_url)

                ses_client.send_email(
                    Destination={'ToAddresses': [user_email]},
                    Message={
                        'Body': {
                            'Html': {'Charset': 'UTF-8', 'Data': personalized_html_body},
                            'Text': {'Charset': 'UTF-8', 'Data': personalized_text_body},
                        },
                        'Subject': {'Charset': 'UTF-8', 'Data': EMAIL_SUBJECT},
                    },
                    Source=from_email,
                )
                print(f"  \033[92m✓ Email enviado exitosamente a {user_email}\033[0m")
                success_count += 1
            except ClientError as e:
                print(f"  \033[91m✗ Error al enviar email a {user_email}: {e.response['Error']['Message']}\033[0m")
                failure_count += 1
        else:
            print(f"  \033[93m- Fila inválida o email faltante para '{user_name}'. Omitiendo.\033[0m")
            failure_count += 1
            
    print("\n--- Proceso de envío finalizado ---")
    print(f"\033[92mEnvíos exitosos: {success_count}\033[0m")
    print(f"\033[91mEnvíos fallidos u omitidos: {failure_count}\033[0m")
    print("-------------------------------------")


if __name__ == "__main__":
    csv_filename = "invitaciones.csv"
    send_invitation_emails_from_csv(csv_filename)
