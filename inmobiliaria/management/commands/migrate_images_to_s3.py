from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.conf import settings
import os
import requests
from io import BytesIO
from inmobiliaria.models import ImagenPropiedad
from storages.backends.s3boto3 import S3Boto3Storage

class Command(BaseCommand):
    help = 'Migra las imágenes existentes al bucket de S3'

    def handle(self, *args, **options):
        self.stdout.write('Iniciando migración de imágenes a S3...')
        
        # Crear storage con ACL público
        storage = S3Boto3Storage(bucket_name=settings.AWS_STORAGE_BUCKET_NAME, default_acl='public-read')
        
        # Obtener todas las imágenes
        imagenes = ImagenPropiedad.objects.all()
        total = imagenes.count()
        
        self.stdout.write(f'Se encontraron {total} imágenes para migrar')
        
        for idx, imagen in enumerate(imagenes, 1):
            try:
                # Obtener la URL actual de la imagen
                current_url = imagen.imagen.url if imagen.imagen else None
                self.stdout.write(f'Procesando imagen {idx}/{total}: {current_url}')
                
                if not current_url:
                    self.stdout.write(self.style.WARNING(f'La imagen {idx} no tiene URL'))
                    continue
                
                # Intentar obtener la imagen
                try:
                    response = requests.get(current_url)
                    response.raise_for_status()
                    
                    # Crear un archivo temporal con el contenido de la imagen
                    img_temp = BytesIO(response.content)
                    
                    # Obtener el nombre del archivo de la URL
                    file_name = os.path.basename(current_url)
                    
                    # Construir la ruta en S3
                    s3_path = f'media/propiedades/{file_name}'
                    self.stdout.write(f'Subiendo a S3: {s3_path}')
                    
                    # Subir a S3 con ACL público
                    storage.save(s3_path, img_temp)
                    
                    # Actualizar el campo imagen con la nueva ubicación
                    imagen.imagen = s3_path
                    imagen.save()
                    
                    self.stdout.write(self.style.SUCCESS(f'Imagen {idx} migrada exitosamente a S3'))
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error al migrar imagen {idx}: {str(e)}'))
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error general al procesar imagen {idx}: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS('Migración completada')) 