
import os
import boto3
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Cargar variables de entorno desde el archivo .env
load_dotenv()

def get_env_variable(var_name):
    """Obtiene una variable de entorno, eliminando espacios en blanco."""
    value = os.getenv(var_name)
    if isinstance(value, str):
        return value.strip()
    return value

def create_cognito_user(email, password, nombre, comunidad, unidad, rut, tipo_unidad):
    """
    Crea un nuevo usuario en el User Pool de Amazon Cognito con atributos personalizados y contraseña permanente.

    Args:
        email (str): El correo electrónico del usuario. Será su nombre de usuario.
        password (str): La contraseña permanente para el nuevo usuario.
        nombre (str): El nombre completo del usuario (custom:Nombre).
        comunidad (str): La comunidad a la que pertenece el usuario (custom:Comunidad).
        unidad (str): Una o más unidades del usuario, separadas por comas (custom:Unidad).
        rut (str): El RUT del usuario (custom:Rut).
        tipo_unidad (str): Uno o más tipos de unidad, separados por comas (custom:TipoUnidad).

    Returns:
        bool: True si el usuario fue creado exitosamente, False en caso contrario.
    """
    user_pool_id = get_env_variable("COGNITO_USER_POOL_ID")
    aws_region = get_env_variable("AWS_REGION")

    if not all([user_pool_id, aws_region, password]):
        print("Error: Asegúrate de que las variables de entorno COGNITO_USER_POOL_ID, AWS_REGION y la contraseña estén configuradas.")
        return False

    cognito_client = boto3.client("cognito-idp", region_name=aws_region)

    try:
        print(f"Intentando crear usuario con email: {email}...")

        # Paso 1: Crear el usuario con todos los atributos personalizados
        response = cognito_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:Nombre", "Value": nombre},
                {"Name": "custom:Comunidad", "Value": comunidad},
                {"Name": "custom:Unidad", "Value": unidad}, # Puede contener múltiples valores separados por coma
                {"Name": "custom:Rut", "Value": rut},
                {"Name": "custom:TipoUnidad", "Value": tipo_unidad}, # Puede contener múltiples valores separados por coma
            ],
            MessageAction="SUPPRESS",
        )

        user_sub = response['User']['Username']
        print(f"Usuario base creado exitosamente para {user_sub}.")

        # Paso 2: Establecer la contraseña del usuario como permanente
        cognito_client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=email,
            Password=password,
            Permanent=True # Hace que la contraseña no expire
        )

        print(f"Éxito: Contraseña permanente establecida para el usuario {email}.")
        return True

    except ClientError as e:
        if e.response["Error"]["Code"] == "UsernameExistsException":
            print(f"Error: El usuario con el email '{email}' ya existe en el User Pool.")
        else:
            print(f"Error inesperado de Boto3 al crear el usuario: {e}")
        return False
    except Exception as e:
        print(f"Un error desconocido ocurrió: {e}")
        return False

if __name__ == "__main__":
    # --- Ejemplo de Uso ---
    # Para un usuario con múltiples unidades, simplemente sepáralas por comas en un solo string.

    # Activa el entorno virtual antes de ejecutar este script:
    # source .venv/bin/activate
    #
    # Asegúrate de tener un archivo .env con tus credenciales y configuración.

    print("--- Creando un nuevo usuario de ejemplo en Cognito con múltiples unidades ---")

    # Datos del usuario de ejemplo
    user_email = "maria.lopez@test.com"
    user_password = "PasswordSeguro456!"
    user_nombre = "Maria Lopez"
    user_comunidad = "Condominio Los Alerces"
    user_rut = "22333444-5"
    
    # Ejemplo con múltiples unidades y tipos de unidad
    user_unidad = "D-205,E-110,F-301"  # Las unidades se separan por comas
    user_tipo_unidad = "Departamento,Bodega,Estacionamiento" # Los tipos también, en el mismo orden

    # Llamada a la función para crear el usuario
    create_cognito_user(
        email=user_email,
        password=user_password,
        nombre=user_nombre,
        comunidad=user_comunidad,
        unidad=user_unidad,
        rut=user_rut,
        tipo_unidad=user_tipo_unidad
    )

    print("--- Fin del script ---")
