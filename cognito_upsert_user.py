
import os
import csv
import boto3
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Cargar variables de entorno desde el archivo .env
load_dotenv()

CSV_FILE_PATH = "usuarios.csv"

def get_env_variable(var_name, fallback_var_name=None):
    """Obtiene una variable de entorno, probando un nombre alternativo si el primero no existe."""
    value = os.getenv(var_name)
    if value is None and fallback_var_name:
        value = os.getenv(fallback_var_name)
    
    if isinstance(value, str):
        return value.strip()
    return value

def create_or_update_cognito_user(email, password, nombre, comunidad, unidad_nueva, rut, tipo_unidad_nuevo, usuario):
    """
    Crea un usuario o lo actualiza. El 'usuario' se usa como el Username de Cognito.
    Si el usuario existe, las nuevas unidades se añaden a las existentes.
    """
    user_pool_id = get_env_variable("COGNITO_USER_POOL_ID")
    aws_region = get_env_variable("AWS_REGION", "AWS_DEFAULT_REGION")

    if not all([user_pool_id, aws_region]):
        print("Error: Asegúrate de que COGNITO_USER_POOL_ID y (AWS_REGION o AWS_DEFAULT_REGION) estén configuradas.")
        return False

    cognito_client = boto3.client("cognito-idp", region_name=aws_region)

    try:
        # Intenta crear el usuario usando 'usuario' como el Username nativo
        new_user_attributes = [
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "custom:Nombre", "Value": nombre},
            {"Name": "custom:Comunidad", "Value": comunidad},
            {"Name": "custom:Unidad", "Value": unidad_nueva},
            {"Name": "custom:Rut", "Value": rut},
            {"Name": "custom:TipoUnidad", "Value": tipo_unidad_nuevo},
        ]
        cognito_client.admin_create_user(
            UserPoolId=user_pool_id, Username=usuario, UserAttributes=new_user_attributes, MessageAction="SUPPRESS"
        )
        print(f"Éxito (CREADO): Usuario '{usuario}' (email: {email}) creado.")

    except ClientError as e:
        if e.response["Error"]["Code"] == "UsernameExistsException":
            print(f"Info: El username '{usuario}' ya existe. Actualizando atributos...")
            try:
                # 1. Obtener los atributos actuales del usuario
                response = cognito_client.admin_get_user(UserPoolId=user_pool_id, Username=usuario)
                current_attributes = {attr['Name']: attr['Value'] for attr in response['UserAttributes']}

                # 2. Combinar unidades, evitando duplicados
                unidades_actuales = set(u.strip() for u in current_attributes.get('custom:Unidad', '').split(',') if u.strip())
                nuevas_unidades = set(u.strip() for u in unidad_nueva.split(',') if u.strip())
                unidades_finales = sorted(list(unidades_actuales.union(nuevas_unidades)))
                unidades_final_str = ",".join(unidades_finales)

                # 3. Combinar tipos de unidad, evitando duplicados
                tipos_actuales = set(t.strip() for t in current_attributes.get('custom:TipoUnidad', '').split(',') if t.strip())
                nuevos_tipos = set(t.strip() for t in tipo_unidad_nuevo.split(',') if t.strip())
                tipos_finales = sorted(list(tipos_actuales.union(nuevos_tipos)))
                tipos_final_str = ",".join(tipos_finales)

                # 4. Preparar atributos para la actualización (sobrescribiendo los demás)
                updated_attributes = [
                    {"Name": "email", "Value": email},
                    {"Name": "custom:Nombre", "Value": nombre},
                    {"Name": "custom:Comunidad", "Value": comunidad},
                    {"Name": "custom:Rut", "Value": rut},
                    {"Name": "custom:Unidad", "Value": unidades_final_str},
                    {"Name": "custom:TipoUnidad", "Value": tipos_final_str},
                ]
                cognito_client.admin_update_user_attributes(
                    UserPoolId=user_pool_id, Username=usuario, UserAttributes=updated_attributes
                )
                print(f"Éxito (ACTUALIZADO): Usuario '{usuario}'. Unidades finales: {unidades_final_str}")

            except ClientError as update_error:
                print(f"Error: No se pudieron actualizar los atributos para '{usuario}'. Causa: {update_error}")
                return False
        else:
            print(f"Error inesperado de Boto3 al procesar a '{usuario}': {e}")
            return False

    # Siempre establece/actualiza la contraseña si se proporciona una
    if password:
        try:
            cognito_client.admin_set_user_password(
                UserPoolId=user_pool_id, Username=usuario, Password=password, Permanent=True
            )
            print(f"Éxito: Contraseña establecida/actualizada para el usuario '{usuario}'.")
        except ClientError as password_error:
            print(f"Error: No se pudo establecer la contraseña para '{usuario}'. Causa: {password_error}")
            return False

    return True

if __name__ == "__main__":
    print("--- Iniciando proceso de carga masiva (Crear o Actualizar con Username) ---")
    if not os.path.exists(CSV_FILE_PATH):
        print(f"Error Crítico: No se encontró el archivo '{CSV_FILE_PATH}'. Asegúrate de que existe.")
    else:
        try:
            with open(CSV_FILE_PATH, mode='r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    print("\n------------------------------------------------------------")
                    print(f"Procesando usuario: {row['usuario']} (Email: {row['email']})")
                    create_or_update_cognito_user(
                        email=row['email'],
                        password=row['password'],
                        nombre=row['nombre'],
                        comunidad=row['comunidad'],
                        unidad_nueva=row['unidad'],
                        rut=row['rut'],
                        tipo_unidad_nuevo=row['tipo_unidad'],
                        usuario=row['usuario']
                    )
        except KeyError as e:
            print(f"Error Crítico: Falta la columna {e} en tu archivo '{CSV_FILE_PATH}'. Revisa la cabecera.")
        except Exception as e:
            print(f"Ocurrió un error inesperado durante la lectura del archivo CSV: {e}")
    print("\n--- Fin del proceso de carga masiva ---")
