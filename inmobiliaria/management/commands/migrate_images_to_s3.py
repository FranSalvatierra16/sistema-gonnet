from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.conf import settings
import os
import requests
from io import BytesIO
from inmobiliaria.models import ImagenPropiedad

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
                # Obtener la URL actual de la imagen
                url_actual = imagen.imagen.url
                
                # Si la URL ya es de S3, saltamos esta imagen
                if 's3.amazonaws.com' in url_actual:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[{idx}/{total}] La imagen ya está en S3: {url_actual}'
                        )
                    )
                    continue
                
                # Descargar la imagen de la URL actual
                response = requests.get(url_actual)
                if response.status_code == 200:
                    # Crear un objeto BytesIO con el contenido de la imagen
                    imagen_bytes = BytesIO(response.content)
                    
                    # Construir la ruta en S3
                    nombre_archivo = os.path.basename(str(imagen.imagen))
                    s3_path = f'propiedades/{nombre_archivo}'
                    
                    # Subir a S3
                    default_storage.save(s3_path, imagen_bytes)
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[{idx}/{total}] Migrada imagen {s3_path}'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'[{idx}/{total}] No se pudo descargar la imagen: {url_actual} (Status: {response.status_code})'
                        )
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'[{idx}/{total}] Error al migrar imagen {imagen.imagen}: {str(e)}'
                    )
                )
        
        self.stdout.write(self.style.SUCCESS('Migración completada')) 