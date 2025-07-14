from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.conf import settings
import os
import requests
from io import BytesIO
from inmobiliaria.models import ImagenPropiedad
from storages.backends.s3boto3 import S3Boto3Storage
import re

class Command(BaseCommand):
    help = 'Migra las imágenes existentes al bucket de S3'

    def handle(self, *args, **options):
        self.stdout.write('Iniciando migración de imágenes a S3...')
        
        # Obtener todas las imágenes
        imagenes = ImagenPropiedad.objects.all()
        total = imagenes.count()
        
        self.stdout.write(f'Se encontraron {total} imágenes para migrar')
        
        for idx, imagen in enumerate(imagenes, 1):
            try:
                # Obtener el nombre original del archivo
                original_name = str(imagen.imagen).split('/')[-1]
                self.stdout.write(f'Procesando imagen {idx}/{total}: {original_name}')
                
                # Intentar diferentes URLs posibles
                urls_to_try = [
                    f'https://gonnet-interno.herokuapp.com/media/propiedades/{original_name}',
                    f'http://gonnet-interno.herokuapp.com/media/propiedades/{original_name}',
                    f'/media/propiedades/{original_name}'
                ]
                
                success = False
                for url in urls_to_try:
                    try:
                        self.stdout.write(f'Intentando URL: {url}')
                        response = requests.get(url)
                        if response.status_code == 200:
                            # Crear un archivo temporal con el contenido de la imagen
                            img_temp = BytesIO(response.content)
                            
                            # Construir la ruta en S3
                            s3_path = f'media/propiedades/{original_name}'
                            self.stdout.write(f'Subiendo a S3: {s3_path}')
                            
                            # Subir a S3
                            default_storage.save(s3_path, img_temp)
                            
                            # Actualizar el campo imagen
                            imagen.imagen = s3_path
                            imagen.save()
                            
                            self.stdout.write(self.style.SUCCESS(f'Imagen {idx} migrada exitosamente'))
                            success = True
                            break
                    except Exception as e:
                        self.stdout.write(f'Error con URL {url}: {str(e)}')
                        continue
                
                if not success:
                    self.stdout.write(self.style.ERROR(f'No se pudo migrar la imagen {idx} después de intentar todas las URLs'))
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error general al procesar imagen {idx}: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS('Migración completada')) 