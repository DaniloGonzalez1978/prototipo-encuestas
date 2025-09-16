
import os
import boto3
from dotenv import load_dotenv
from botocore.exceptions import ClientError, NoCredentialsError

def get_env_variable(var_name):
    """Obtiene una variable de entorno, eliminando espacios en blanco."""
    value = os.getenv(var_name)
    if isinstance(value, str):
        return value.strip()
    return value

def delete_all_cognito_users():
    """
    Elimina todos los usuarios de un User Pool de Amazon Cognito.
    
    Requiere que las siguientes variables de entorno estén configuradas:
    - AWS_ACCESS_KEY_ID: La clave de acceso de AWS.
    - AWS_SECRET_ACCESS_KEY: La clave de acceso secreta de AWS.
    - AWS_DEFAULT_REGION: La región de AWS (ej. 'us-east-1').
    - COGNITO_USER_POOL_ID: El ID del User Pool de Cognito del cual se eliminarán los usuarios.
    """
    print("--- Iniciando el script de limpieza de usuarios de Cognito ---")
    
    # Cargar variables de entorno desde el archivo .env
    load_dotenv()

    # --- 1. Obtener configuración ---
    user_pool_id = get_env_variable('COGNITO_USER_POOL_ID')
    aws_region = get_env_variable('AWS_DEFAULT_REGION')

    if not user_pool_id:
        print("\n\033[91mERROR: La variable de entorno COGNITO_USER_POOL_ID no está configurada.\033[0m")
        print("Por favor, añade COGNITO_USER_POOL_ID a tu archivo .env con el ID de tu User Pool de Cognito.")
        print("--- Script finalizado con errores ---")
        return

    print(f"User Pool ID de destino: {user_pool_id}")
    print(f"Región de AWS: {aws_region}")

    # --- 2. Conectar a Cognito ---
    try:
        cognito_client = boto3.client(
            'cognito-idp',
            aws_access_key_id=get_env_variable('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=get_env_variable('AWS_SECRET_ACCESS_KEY'),
            region_name=aws_region
        )
        # Probar la conexión
        cognito_client.describe_user_pool(UserPoolId=user_pool_id)
        print("\nConexión con AWS Cognito establecida con éxito.")
    except NoCredentialsError:
        print("\n\033[91mERROR: No se encontraron credenciales de AWS.\033[0m")
        print("Asegúrate de que AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY estén en tu archivo .env.")
        print("--- Script finalizado con errores ---")
        return
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"\n\033[91mERROR: El User Pool con ID '{user_pool_id}' no fue encontrado en la región '{aws_region}'.\033[0m")
        else:
            print(f"\n\033[91mERROR de AWS: {e.response['Error']['Message']}\033[0m")
        print("--- Script finalizado con errores ---")
        return
    except Exception as e:
        print(f"\n\033[91mERROR inesperado al conectar con Cognito: {str(e)}\033[0m")
        print("--- Script finalizado con errores ---")
        return

    # --- 3. Listar y eliminar usuarios ---
    try:
        print("\nObteniendo la lista de usuarios. Esto puede tardar unos segundos...")
        all_users = []
        paginator = cognito_client.get_paginator('list_users')
        pages = paginator.paginate(UserPoolId=user_pool_id)
        
        for page in pages:
            all_users.extend(page['Users'])

        if not all_users:
            print("\n\033[92mNo se encontraron usuarios en el User Pool. ¡No hay nada que hacer!\033[0m")
            print("--- Script finalizado con éxito ---")
            return

        print(f"Se encontraron {len(all_users)} usuarios. Procediendo a la eliminación.")
        
        for i, user in enumerate(all_users):
            username = user['Username']
            print(f"  ({i+1}/{len(all_users)}) Eliminando usuario: {username}...", end='')
            try:
                cognito_client.admin_delete_user(
                    UserPoolId=user_pool_id,
                    Username=username
                )
                print(" \033[92mHECHO\033[0m")
            except ClientError as e:
                print(f" \033[91mFALLÓ ({e.response['Error']['Message']})\033[0m")

        print("\n\033[92mProceso de eliminación completado.\033[0m")
        print("--- Script finalizado con éxito ---")

    except ClientError as e:
        print(f"\n\033[91mERROR durante la operación: {e.response['Error']['Message']}\033[0m")
        print("--- Script finalizado con errores ---")

if __name__ == "__main__":
    # Preguntar al usuario por una confirmación final antes de proceder.
    confirm = input("\n\033[93mADVERTENCIA: Este script eliminará PERMANENTEMENTE a TODOS los usuarios del User Pool configurado. Esta acción no se puede deshacer.\033[0m\n¿Estás absolutamente seguro de que quieres continuar? (escribe 'eliminar' para confirmar): ")
    if confirm.lower() == 'eliminar':
        delete_all_cognito_users()
    else:
        print("\nOperación cancelada por el usuario.")
        print("--- Script finalizado ---")
