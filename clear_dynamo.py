
import os
import boto3
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Carga la configuración de AWS desde el archivo .env
load_dotenv()

# Obtiene el nombre de la tabla y la región desde las variables de entorno
table_name = os.getenv('DYNAMODB_TABLE_NAME', 'user_participations')
region_name = os.getenv('AWS_DEFAULT_REGION')

# Inicializa los clientes de AWS
dynamodb_client = boto3.client('dynamodb', region_name=region_name)
dynamodb_resource = boto3.resource('dynamodb', region_name=region_name)

def clean_dynamo_table():
    """
    Obtiene el esquema de clave de la tabla, luego escanea y elimina todos los ítems.
    """
    try:
        print(f"Iniciando la limpieza de la tabla '{table_name}'...")

        # 1. Obtener el esquema de la clave primaria de la tabla
        print("Obteniendo el esquema de la clave de la tabla...")
        table_description = dynamodb_client.describe_table(TableName=table_name)
        key_schema = table_description['Table']['KeySchema']
        key_names = [key['AttributeName'] for key in key_schema]
        print(f"Esquema de clave detectado: {key_names}")

        # 2. Escanear la tabla para obtener las claves de todos los ítems
        table = dynamodb_resource.Table(table_name)
        scan_kwargs = {
            'ProjectionExpression': ", ".join(key_names)
        }
        items_to_delete = []
        
        done = False
        start_key = None
        while not done:
            if start_key:
                scan_kwargs['ExclusiveStartKey'] = start_key
            response = table.scan(**scan_kwargs)
            items_to_delete.extend(response.get('Items', []))
            start_key = response.get('LastEvaluatedKey', None)
            done = start_key is None

        if not items_to_delete:
            print("La tabla ya está vacía. No se requiere ninguna acción.")
            return

        print(f"Se encontraron {len(items_to_delete)} ítems. Procediendo a la eliminación en lotes...")

        # 3. Eliminar los ítems en lotes de 25
        with table.batch_writer() as batch:
            for item in items_to_delete:
                batch.delete_item(Key=item)
        
        print(f"¡Limpieza completada! Se han eliminado {len(items_to_delete)} ítems de la tabla '{table_name}'.")

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"Error: La tabla '{table_name}' no fue encontrada en la región '{region_name}'. Verifica la configuración.")
        else:
            print(f"Error de AWS al acceder a DynamoDB: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"Ha ocurrido un error inesperado durante la limpieza: {e}")

if __name__ == '__main__':
    clean_dynamo_table()
