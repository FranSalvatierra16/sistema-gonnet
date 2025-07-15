import os
import django
from django.core.files.storage import default_storage
from django.core.files import File
import boto3
from botocore.exceptions import ClientError
import logging
from tqdm import tqdm
import requests
from django.db import connection
import io
import base64

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')
django.setup()

from inmobiliaria.models import ImagenPropiedad
from django.conf import settings

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_s3_client():
    """Crear y retornar un cliente de S3"""
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )

def check_s3_connection():
    """Verificar la conexión a S3"""
    try:
        s3 = get_s3_client()
        s3.head_bucket(Bucket=settings.AWS_STORAGE_BUCKET_NAME)
        logger.info("Conexión a S3 exitosa")
        return True
    except ClientError as e:
        logger.error(f"Error al conectar con S3: {str(e)}")
        return False

def get_image_from_db(imagen_path):
    """Intentar obtener la imagen directamente de la base de datos MySQL"""
    try:
        with connection.cursor() as cursor:
            # Intentar diferentes tablas donde podría estar almacenada la imagen
            tables_to_try = [
                'django_content_type_imagenpropiedad',
                'inmobiliaria_imagenpropiedad',
                'imagenpropiedad'
            ]
            
            for table in tables_to_try:
                try:
                    cursor.execute(f"""
                        SELECT imagen 
                        FROM {table} 
                        WHERE imagen = %s
                    """, [str(imagen_path)])
                    row = cursor.fetchone()
                    if row and row[0]:
                        return io.BytesIO(row[0])
                except:
                    continue
        return None
    except Exception as e:
        logger.error(f"Error al obtener imagen de la base de datos: {str(e)}")
        return None

def try_get_image_content(imagen):
    """Intentar obtener el contenido de la imagen de diferentes fuentes"""
    
    # 1. Intentar obtener la imagen localmente
    local_path = os.path.join(settings.MEDIA_ROOT, str(imagen.imagen))
    if os.path.exists(local_path):
        logger.info(f"Imagen encontrada localmente: {local_path}")
        return open(local_path, 'rb')

    # 2. Intentar obtener la imagen de la URL completa
    try:
        url = f"https://gonnet-interno-052a6cec3da9.herokuapp.com/media/{str(imagen.imagen)}"
        response = requests.get(url)
        if response.status_code == 200:
            logger.info(f"Imagen obtenida de URL: {url}")
            return io.BytesIO(response.content)
    except Exception as e:
        logger.warning(f"No se pudo obtener la imagen de la URL: {str(e)}")

    # 3. Intentar obtener la imagen de la base de datos
    db_image = get_image_from_db(str(imagen.imagen))
    if db_image:
        logger.info(f"Imagen obtenida de la base de datos")
        return db_image

    # 4. Intentar obtener la imagen de una URL alternativa
    try:
        alt_url = f"https://gonnet-interno.herokuapp.com/media/{str(imagen.imagen)}"
        response = requests.get(alt_url)
        if response.status_code == 200:
            logger.info(f"Imagen obtenida de URL alternativa: {alt_url}")
            return io.BytesIO(response.content)
    except Exception as e:
        logger.warning(f"No se pudo obtener la imagen de la URL alternativa: {str(e)}")

    return None

def migrate_images():
    """Migrar imágenes a S3"""
    if not check_s3_connection():
        logger.error("No se pudo establecer conexión con S3. Abortando migración.")
        return

    # Obtener todas las imágenes
    imagenes = ImagenPropiedad.objects.all()
    logger.info(f"Encontradas {len(imagenes)} imágenes para migrar")

    # Crear cliente S3
    s3 = get_s3_client()

    # Migrar cada imagen
    for imagen in tqdm(imagenes, desc="Migrando imágenes"):
        try:
            # Construir la ruta en S3
            s3_path = f"{settings.MEDIA_LOCATION}/{str(imagen.imagen)}"

            # Verificar si la imagen ya existe en S3
            try:
                s3.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=s3_path)
                logger.info(f"La imagen ya existe en S3: {s3_path}")
                continue
            except ClientError:
                # La imagen no existe en S3, procedemos a obtenerla
                pass

            # Intentar obtener el contenido de la imagen
            image_content = try_get_image_content(imagen)
            
            if not image_content:
                logger.warning(f"No se pudo obtener la imagen: {str(imagen.imagen)}")
                continue

            # Subir archivo a S3
            s3.upload_fileobj(
                image_content,
                settings.AWS_STORAGE_BUCKET_NAME,
                s3_path,
                ExtraArgs={'ACL': 'public-read'}
            )
            
            logger.info(f"Imagen migrada exitosamente: {s3_path}")

        except Exception as e:
            logger.error(f"Error al migrar imagen {str(imagen.imagen)}: {str(e)}")

if __name__ == "__main__":
    logger.info("Iniciando migración de imágenes a S3")
    migrate_images()
    logger.info("Proceso de migración completado") 