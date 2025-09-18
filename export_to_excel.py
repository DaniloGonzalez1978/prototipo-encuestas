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
    Extrae todos los datos de DynamoDB dinámicamente y los exporta a un archivo Excel.
    """
    print("Iniciando la exportación dinámica a Excel...")

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

    # 2. Extracción y Deserialización de Datos
    items_raw = get_all_items_from_dynamodb(table_name, dynamodb_client)
    if items_raw is None:
        print("La exportación ha fallado debido a un error con DynamoDB.")
        return
    if not items_raw:
        print("No se encontraron datos para exportar.")
        return

    processed_items = [deserialize_dynamodb_item(item) for item in items_raw]
    print(f"Total de filas a exportar: {len(processed_items)}")

    # 3. Creación Dinámica de Encabezados
    all_keys = set()
    for item in processed_items:
        all_keys.update(item.keys())
    
    # Mover columnas de imágenes al final
    image_headers = ["Imagen Frontal", "Imagen Trasera"]
    url_headers = ["url_img_frontal", "url_img_trasera"]
    
    data_headers = sorted([key for key in all_keys if key not in url_headers])
    final_headers = data_headers + url_headers + image_headers

    # 4. Creación del Libro de Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Participaciones"
    ws.append(final_headers)

    header_to_col_idx = {header: i for i, header in enumerate(final_headers, 1)}

    # Ajustar ancho de columnas
    for col_idx, header in enumerate(final_headers, 1):
        col_letter = get_column_letter(col_idx)
        if header in image_headers:
             ws.column_dimensions[col_letter].width = IMAGE_WIDTH / 7
        else:
             ws.column_dimensions[col_letter].width = max(len(str(header)) + 2, 20)

    # 5. Llenado de Filas y Imágenes
    for row_idx, item in enumerate(processed_items, start=2):
        ws.row_dimensions[row_idx].height = IMAGE_HEIGHT * 0.75
        
        # Llenar datos dinámicamente
        for header, col_idx in header_to_col_idx.items():
            if header in item:
                value = item[header]
                # Formateo especial para booleanos
                if isinstance(value, bool):
                    value = "Sí" if value else "No"
                ws.cell(row=row_idx, column=col_idx, value=value)
            else:
                # Dejar en blanco si el item no tiene esa clave (excepto para las columnas de imagen)
                if header not in image_headers:
                    ws.cell(row=row_idx, column=col_idx, value="N/A")

        # Incrustar imágenes
        image_urls = {
            header_to_col_idx["Imagen Frontal"]: item.get("url_img_frontal"), 
            header_to_col_idx["Imagen Trasera"]: item.get("url_img_trasera")
        }

        for col_num, img_url in image_urls.items():
            cell_coordinate = get_column_letter(col_num) + str(row_idx)
            if not img_url or img_url == "N/A":
                ws[cell_coordinate] = "URL no disponible"
                continue

            img_path = img_url.lstrip('/')
            if os.path.exists(img_path):
                try:
                    with PILImage.open(img_path) as pil_img:
                        # Rotar si es necesario
                        if pil_img.height > pil_img.width:
                            pil_img = pil_img.rotate(-90, expand=True)

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

    # 6. Guardado del Archivo
    try:
        wb.save(OUTPUT_FILE)
        print(f"¡Éxito! Los datos han sido exportados dinámicamente a '{OUTPUT_FILE}'.")
    except Exception as e:
        print(f"Error al guardar el archivo Excel: {e}")

if __name__ == "__main__":
    export_to_excel()
