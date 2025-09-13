
import sqlite3
from openpyxl import Workbook
from openpyxl.drawing.image import Image
from PIL import Image as PILImage
import os
import errno

DB_PATH = "instance/database.sqlite"
OUTPUT_FILE = "static/exported_data.xlsx"

def export_to_excel():
    """
    Connects to the SQLite database, fetches all data from the 'user_response' table,
    and exports it to an Excel file, including all device data and images.
    """
    temp_files_to_delete = []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # Access columns by name
        cursor = conn.cursor()
        
        # Select all columns from the table
        cursor.execute("SELECT * FROM user_response")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("No data found in the 'user_response' table.")
            return

        wb = Workbook()
        ws = wb.active
        ws.title = "User Responses"

        # Define headers including the new validation_attempts column
        headers = [
            "ID", "RUT", "Comunidad", "Unidad", "Email", "Respuesta", 
            "Fecha de Votación", "Fecha de Login", "Fecha de Validación", "Intentos de Validación",
            "IP Address", "User Agent", "Screen Resolution", "Available Screen Res",
            "Color Depth", "Timezone", "Platform", "Do Not Track", "CPU Cores",
            "Device Memory", "Battery Level", "Battery Status", "Connection Type",
            "Connection Quality", "Path Imagen Frontal", "Path Imagen Trasera",
            "Imagen Frontal", "Imagen Trasera"
        ]
        ws.append(headers)

        # Adjust column widths for better readability
        column_widths = {
            'A': 5, 'B': 15, 'C': 20, 'D': 20, 'E': 30, 'F': 40, 'G': 20, 'H': 20,
            'I': 20, 'J': 20, 'K': 15, 'L': 50, 'M': 20, 'N': 20, 'O': 15, 'P': 15, 
            'Q': 15, 'R': 15, 'S': 10, 'T': 15, 'U': 15, 'V': 15, 'W': 15, 'X': 15,
            'Y': 40, 'Z': 40, 'AA': 35, 'AB': 35
        }
        for col_letter, width in column_widths.items():
            ws.column_dimensions[col_letter].width = width

        for row_idx, row_data in enumerate(rows, start=2):
            # Set a fixed row height for image display
            ws.row_dimensions[row_idx].height = 115

            # Map data to cells, using column names for clarity
            ws.cell(row=row_idx, column=1, value=row_data['id'])
            ws.cell(row=row_idx, column=2, value=row_data['rut'])
            ws.cell(row=row_idx, column=3, value=row_data['comunidad'])
            ws.cell(row=row_idx, column=4, value=row_data['unidad'])
            ws.cell(row=row_idx, column=5, value=row_data['email'])
            ws.cell(row=row_idx, column=6, value=row_data['respuesta'])
            ws.cell(row=row_idx, column=7, value=row_data['submission_timestamp'])
            ws.cell(row=row_idx, column=8, value=row_data['login_timestamp'])
            ws.cell(row=row_idx, column=9, value=row_data['validation_timestamp'])
            ws.cell(row=row_idx, column=10, value=row_data['validation_attempts'])
            ws.cell(row=row_idx, column=11, value=row_data['ip_address'])
            ws.cell(row=row_idx, column=12, value=row_data['user_agent'])
            ws.cell(row=row_idx, column=13, value=row_data['screen_resolution'])
            ws.cell(row=row_idx, column=14, value=row_data['available_screen_resolution'])
            ws.cell(row=row_idx, column=15, value=row_data['color_depth'])
            ws.cell(row=row_idx, column=16, value=row_data['timezone'])
            ws.cell(row=row_idx, column=17, value=row_data['platform'])
            ws.cell(row=row_idx, column=18, value=row_data['do_not_track'])
            ws.cell(row=row_idx, column=19, value=row_data['cpu_cores'])
            ws.cell(row=row_idx, column=20, value=row_data['device_memory'])
            ws.cell(row=row_idx, column=21, value=row_data['battery_level'])
            ws.cell(row=row_idx, column=22, value=row_data['battery_status'])
            ws.cell(row=row_idx, column=23, value=row_data['connection_type'])
            ws.cell(row=row_idx, column=24, value=row_data['connection_quality'])
            ws.cell(row=row_idx, column=25, value=row_data['id_card_front_image'])
            ws.cell(row=row_idx, column=26, value=row_data['id_card_back_image'])
            
            # --- Process and insert front image ---
            front_img_path = row_data['id_card_front_image']
            if front_img_path and os.path.exists(front_img_path):
                try:
                    pil_img = PILImage.open(front_img_path)
                    if pil_img.height > pil_img.width:
                        pil_img = pil_img.rotate(90, expand=True)
                    pil_img = pil_img.resize((240, 150))
                    temp_img_path = f"temp_front_{os.path.basename(front_img_path)}"
                    pil_img.save(temp_img_path)
                    temp_files_to_delete.append(temp_img_path)
                    img = Image(temp_img_path)
                    ws.add_image(img, f"AA{row_idx}")
                except Exception as e:
                    print(f"Error processing image {front_img_path}: {e}")
                    ws.cell(row=row_idx, column=27, value="Error al procesar")
            else:
                ws.cell(row=row_idx, column=27, value="Imagen no encontrada")

            # --- Process and insert back image ---
            back_img_path = row_data['id_card_back_image']
            if back_img_path and os.path.exists(back_img_path):
                try:
                    pil_img = PILImage.open(back_img_path)
                    if pil_img.height > pil_img.width:
                        pil_img = pil_img.rotate(90, expand=True)
                    pil_img = pil_img.resize((240, 150))
                    temp_img_path = f"temp_back_{os.path.basename(back_img_path)}"
                    pil_img.save(temp_img_path)
                    temp_files_to_delete.append(temp_img_path)
                    img = Image(temp_img_path)
                    ws.add_image(img, f"AB{row_idx}")
                except Exception as e:
                    print(f"Error processing image {back_img_path}: {e}")
                    ws.cell(row=row_idx, column=28, value="Error al procesar")
            else:
                ws.cell(row=row_idx, column=28, value="Imagen no encontrada")

        wb.save(OUTPUT_FILE)
        print(f"Data successfully exported to {OUTPUT_FILE}")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        for temp_file in temp_files_to_delete:
            try:
                os.remove(temp_file)
            except OSError as e:
                if e.errno != errno.ENOENT:
                    print(f"Error deleting temp file {temp_file}: {e}")

if __name__ == "__main__":
    export_to_excel()
