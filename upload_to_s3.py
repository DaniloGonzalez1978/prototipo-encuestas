
import boto3
import os
import mimetypes
from dotenv import load_dotenv

# --- Configuration ---
BUCKET_NAME = "www.encuestaescrita.cl"
LOCAL_FOLDER = "promo_site"
# La región se leerá desde las variables de entorno, con un valor por defecto.
# ---------------------

def get_content_type(filename):
    """Guesses the content type based on the file extension."""
    content_type, _ = mimetypes.guess_type(filename)
    return content_type or 'application/octet-stream'

def main():
    """
    Connects to S3 and uploads files from a local directory to a specified bucket,
    using credentials from a .env file.
    """
    # Carga las variables de entorno desde el archivo .env
    load_dotenv()
    print("INFO: Loaded environment variables from .env file.")

    # Lee las credenciales y la región desde las variables de entorno
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1") # Usa us-east-1 si no está definida

    if not aws_access_key_id or not aws_secret_access_key:
        print("!! ERROR: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set in your .env file.")
        return

    print(f"--> Connecting to S3 in region {aws_region}...")
    try:
        # Boto3 usará las credenciales pasadas explícitamente
        s3_client = boto3.client(
            "s3",
            region_name=aws_region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
    except Exception as e:
        print(f"!! ERROR: Could not connect to AWS. Are your credentials in .env valid?")
        print(f"   Details: {e}")
        return

    print(f"--> Uploading files from '{LOCAL_FOLDER}' to bucket '{BUCKET_NAME}'...")
    
    # Walk through the local folder
    for root, _, files in os.walk(LOCAL_FOLDER):
        for filename in files:
            local_path = os.path.join(root, filename)
            relative_path = os.path.relpath(local_path, LOCAL_FOLDER)
            s3_key = relative_path.replace("\\", "/")

            if s3_key == '.':
                s3_key = filename

            content_type = get_content_type(filename)

            try:
                print(f"  + Uploading {local_path} to s3://{BUCKET_NAME}/{s3_key}...")
                s3_client.upload_file(
                    local_path,
                    BUCKET_NAME,
                    s3_key,
                    ExtraArgs={'ContentType': content_type}
                )
            except Exception as e:
                print(f"  !! FAILED to upload {local_path}. Error: {e}")

    print("\n--> Upload process finished.")
    
    website_url = f"http://{BUCKET_NAME}.s3-website-{aws_region}.amazonaws.com"
    print("\n----------------------------------------------------")
    print(f"Your website should now be live at:")
    print(website_url)
    print("----------------------------------------------------")

if __name__ == "__main__":
    if not os.path.exists(LOCAL_FOLDER):
        print(f"!! ERROR: The local folder '{LOCAL_FOLDER}' was not found.")
    else:
        main()
