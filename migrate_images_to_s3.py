import os
import django
from django.core.files.storage import default_storage
from django.core.files import File
import boto3
from botocore.exceptions import ClientError
import logging
from tqdm import tqdm

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
            # Construir la ruta local de la imagen
            local_path = os.path.join(settings.MEDIA_ROOT, str(imagen.imagen))
            
            # Verificar si el archivo existe localmente
            if not os.path.exists(local_path):
                logger.warning(f"Imagen no encontrada localmente: {local_path}")
                continue

            # Construir la ruta en S3
            s3_path = f"{settings.MEDIA_LOCATION}/{str(imagen.imagen)}"

            # Verificar si la imagen ya existe en S3
            try:
                s3.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=s3_path)
                logger.info(f"La imagen ya existe en S3: {s3_path}")
                continue
            except ClientError:
                # La imagen no existe en S3, procedemos a subirla
                pass

            # Subir archivo a S3
            with open(local_path, 'rb') as file:
                s3.upload_fileobj(
                    file,
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