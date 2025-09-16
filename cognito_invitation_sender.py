import os
import boto3
from dotenv import load_dotenv
from botocore.exceptions import ClientError, NoCredentialsError

# --- Email Content ---
# Personaliza el asunto y el cuerpo de tu correo de invitación aquí.
# Puedes usar {name} como marcador de posición para el nombre del usuario.
EMAIL_SUBJECT = "¡Es hora de votar! Tu participación es importante."
EMAIL_HTML_BODY = """
<html>
<head></head>
<body>
  <h1>Hola {name},</h1>
  <p>Te invitamos a participar en el proceso de votación de nuestra comunidad.</p>
  <p>La votación estará abierta durante 7 días. Para emitir tu voto, por favor sigue el enlace a continuación:</p>
  <p><a href="https://app.mi-comunidad-genial.cl">Ir a la Aplicación de Votación</a></p>
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
https://app.mi-comunidad-genial.cl

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

def send_invitation_emails():
    """
    Obtiene todos los usuarios de un User Pool de Cognito y les envía un email de invitación usando SES.
    
    Requiere que las siguientes variables de entorno estén configuradas:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - AWS_DEFAULT_REGION
    - COGNITO_USER_POOL_ID
    - SES_FROM_EMAIL_ADDRESS: La dirección de email verificada en SES para usar como remitente.
    """
    print("--- Iniciando el script de envío de invitaciones ---")
    
    load_dotenv()
    
    aws_region = get_env_variable("AWS_DEFAULT_REGION")
    user_pool_id = get_env_variable("COGNITO_USER_POOL_ID")
    from_email = get_env_variable("SES_FROM_EMAIL_ADDRESS")
    
    if not all([aws_region, user_pool_id, from_email]):
        print("\033[91mError: Faltan una o más variables de entorno requeridas (AWS_DEFAULT_REGION, COGNITO_USER_POOL_ID, SES_FROM_EMAIL_ADDRESS).\033[0m")
        return

    print(f"Región de AWS: {aws_region}")
    print(f"Cognito User Pool ID: {user_pool_id}")
    print(f"Email de remitente (SES): {from_email}")

    try:
        cognito_client = boto3.client('cognito-idp', region_name=aws_region)
        ses_client = boto3.client('ses', region_name=aws_region)
    except NoCredentialsError:
        print("\033[91mError: No se encontraron las credenciales de AWS. Asegúrate de que AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY estén configuradas.\033[0m")
        return

    all_users = []
    try:
        print("\nObteniendo la lista de usuarios de Cognito...")
        paginator = cognito_client.get_paginator('list_users')
        pages = paginator.paginate(UserPoolId=user_pool_id)
        
        for page in pages:
            all_users.extend(page['Users'])
        
        print(f"Se encontraron {len(all_users)} usuarios en total.")
    
    except ClientError as e:
        print(f"\033[91mError al obtener usuarios de Cognito: {e}\033[0m")
        return

    if not all_users:
        print("No hay usuarios a los que enviar correos. Finalizando script.")
        return

    print("\nEnviando correos de invitación...")
    success_count = 0
    failure_count = 0

    for user in all_users:
        user_email = None
        user_name = user.get('Username', 'miembro de la comunidad')
        
        for attr in user.get('Attributes', []):
            if attr['Name'] == 'email':
                user_email = attr['Value']
            if attr['Name'] == 'name':
                user_name = attr['Value']

        if user_email:
            try:
                personalized_html_body = EMAIL_HTML_BODY.format(name=user_name)
                personalized_text_body = EMAIL_TEXT_BODY.format(name=user_name)

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
            print(f"  \033[93m- Usuario {user_name} no tiene un email registrado. Omitiendo.\033[0m")
            failure_count += 1
            
    print("\n--- Proceso de envío finalizado ---")
    print(f"\033[92mEnvíos exitosos: {success_count}\033[0m")
    print(f"\033[91mEnvíos fallidos u omitidos: {failure_count}\033[0m")
    print("-------------------------------------")


if __name__ == "__main__":
    confirm = input("\nEste script enviará un correo de invitación a TODOS los usuarios del User Pool configurado.\n¿Estás seguro de que quieres continuar? (escribe 'enviar' para confirmar): ")
    if confirm.lower() == 'enviar':
        send_invitation_emails()
    else:
        print("\nOperación cancelada por el usuario.")
        print("--- Script finalizado ---")
