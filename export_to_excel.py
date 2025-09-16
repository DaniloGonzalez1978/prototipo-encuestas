import os
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from openpyxl import Workbook
from openpyxl.drawing.image import Image as OpenpyxlImage
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage
from dotenv import load_dotenv
import io

# Cargar variables de entorno desde .env
load_dotenv()

# --- Configuraciones ---
OUTPUT_FILE = "participaciones_export.xlsx"
IMAGE_WIDTH = 240
IMAGE_HEIGHT = 150

def get_all_items_from_dynamodb(table_name, dynamodb_client):
    """
    Extrae todos los items de una tabla de DynamoDB usando paginación.
    """
    items = []
    try:
        paginator = dynamodb_client.get_paginator('scan')
        page_iterator = paginator.paginate(TableName=table_name, PaginationConfig={'PageSize': 100})
        for page in page_iterator:
            items.extend(page['Items'])
        print(f"Se encontraron {len(items)} registros en la tabla '{table_name}'.")
        return items
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"Error Crítico: La tabla '{table_name}' no fue encontrada en la región configurada.")
        else:
            print(f"Error de AWS al escanear la tabla: {e}")
        return None

def deserialize_dynamodb_item(item):
    """
    Convierte un item de DynamoDB (con tipos de datos) a un diccionario de Python simple.
    """
    deserialized = {}
    for key, value in item.items():
        data_type = list(value.keys())[0]
        val = value[data_type]
        
        if data_type == 'S':
            deserialized[key] = val
        elif data_type == 'N':
            try:
                deserialized[key] = int(val)
            except (ValueError, TypeError):
                try:
                    deserialized[key] = float(val)
                except (ValueError, TypeError):
                    deserialized[key] = val
        elif data_type == 'BOOL':
            deserialized[key] = val
        elif data_type == 'NULL':
            deserialized[key] = None
        else:
            deserialized[key] = str(val)
    return deserialized

def export_to_excel():
    """
    Extrae datos de DynamoDB y los exporta a un archivo Excel, incrustando imágenes.
    """
    print("Iniciando la exportación a Excel...")

    # 1. Conexión a DynamoDB
    try:
        dynamodb_client = boto3.client(
            'dynamodb',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION')
        )
        table_name = os.getenv('DYNAMODB_TABLE_NAME')
        if not table_name:
            print("Error: La variable de entorno DYNAMODB_TABLE_NAME no está definida.")
            return
    except (NoCredentialsError, PartialCredentialsError):
        print("Error de Autenticación: Credenciales de AWS no encontradas.")
        return

    # 2. Extracción y Procesamiento de Datos
    items_raw = get_all_items_from_dynamodb(table_name, dynamodb_client)
    if items_raw is None:
        print("La exportación ha fallado debido a un error con DynamoDB.")
        return
    if not items_raw:
        print("No se encontraron datos para exportar.")
        return

    processed_items = []
    for item_raw in items_raw:
        item = deserialize_dynamodb_item(item_raw)
        unidades_str = item.get('unidad', '')
        unidades_list = [unidad.strip() for unidad in unidades_str.split(',') if unidad.strip()]
        
        if not unidades_list:
            processed_items.append(item)
        else:
            for unidad in unidades_list:
                item_copy = item.copy()
                item_copy['unidad'] = unidad
                processed_items.append(item_copy)

    print(f"Total de filas a exportar después de procesar unidades: {len(processed_items)}")

    # 3. Creación del Libro de Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Participaciones"

    headers = [
        "RUT", "Nombre", "Email", "Comunidad", "Unidad", "Decisión", "Éxito de Match", 
        "RUT en Imagen", "Tiempo de Votación", "Tiempo de Login", "Intentos de Validación", 
        "Contador de Logins", "Tiempo de Validación (seg)", 
        "URL Imagen Frontal", "URL Imagen Trasera", "Imagen Frontal", "Imagen Trasera"
    ]
    ws.append(headers)

    column_widths = {'P': IMAGE_WIDTH / 7, 'Q': IMAGE_WIDTH / 7}
    for col_idx, header in enumerate(headers, 1):
        col_letter = get_column_letter(col_idx)
        if col_letter not in column_widths:
            ws.column_dimensions[col_letter].width = max(len(header) + 2, 15)

    # 4. Llenado de Filas y Imágenes
    for row_idx, item in enumerate(processed_items, start=2):
        ws.row_dimensions[row_idx].height = IMAGE_HEIGHT * 0.75
        
        ws.cell(row=row_idx, column=1, value=item.get("rut", "N/A"))
        ws.cell(row=row_idx, column=2, value=item.get("nombre", "N/A"))
        ws.cell(row=row_idx, column=3, value=item.get("email", "N/A"))
        ws.cell(row=row_idx, column=4, value=item.get("comunidad", "N/A"))
        ws.cell(row=row_idx, column=5, value=item.get("unidad", "N/A"))
        ws.cell(row=row_idx, column=6, value=item.get("decision_reglamento", "N/A"))
        ws.cell(row=row_idx, column=7, value="Sí" if item.get("rut_match_success") else "No")
        ws.cell(row=row_idx, column=8, value=item.get("rut_detectado_imagen", "N/A"))
        ws.cell(row=row_idx, column=9, value=item.get("timestamp_votacion", "N/A"))
        ws.cell(row=row_idx, column=10, value=item.get("timestamp_login", "N/A"))
        ws.cell(row=row_idx, column=11, value=item.get("intentos_validacion_rut", 0))
        ws.cell(row=row_idx, column=12, value=item.get("contador_logins", 0))
        ws.cell(row=row_idx, column=13, value=item.get("tiempo_validacion_seg", 0))
        ws.cell(row=row_idx, column=14, value=item.get("url_img_frontal", "N/A"))
        ws.cell(row=row_idx, column=15, value=item.get("url_img_trasera", "N/A"))

        image_urls = {16: item.get("url_img_frontal"), 17: item.get("url_img_trasera")}

        for col_num, img_url in image_urls.items():
            cell_coordinate = get_column_letter(col_num) + str(row_idx)
            if not img_url or img_url == "N/A":
                ws[cell_coordinate] = "URL no disponible"
                continue

            img_path = img_url.lstrip('/')
            if os.path.exists(img_path):
                try:
                    with PILImage.open(img_path) as pil_img:
                        # CORRECCIÓN: Rotar 90 grados en sentido horario
                        if pil_img.height > pil_img.width:
                            pil_img = pil_img.rotate(90, expand=True)

                        pil_img.thumbnail((IMAGE_WIDTH, IMAGE_HEIGHT))
                        
                        img_byte_arr = io.BytesIO()
                        pil_img.save(img_byte_arr, format='PNG')
                        img_byte_arr.seek(0)
                        
                        img_to_add = OpenpyxlImage(img_byte_arr)
                        ws.add_image(img_to_add, cell_coordinate)
                except Exception as e:
                    print(f"Error al procesar la imagen {img_path}: {e}")
                    ws[cell_coordinate] = "Error al procesar"
            else:
                ws[cell_coordinate] = "Imagen no encontrada"

    # 5. Guardado del Archivo
    try:
        wb.save(OUTPUT_FILE)
        print(f"¡Éxito! Los datos han sido exportados a '{OUTPUT_FILE}'.")
    except Exception as e:
        print(f"Error al guardar el archivo Excel: {e}")

if __name__ == "__main__":
    export_to_excel()
