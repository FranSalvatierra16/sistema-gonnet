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
                current_url = imagen.imagen.url if imagen.imagen else None
                self.stdout.write(f'Procesando imagen {idx}/{total}: {current_url}')
                
                if not current_url:
                    self.stdout.write(self.style.WARNING(f'La imagen {idx} no tiene URL'))
                    continue
                
                # Si la imagen ya está en S3, verificar si es accesible
                if 's3.amazonaws.com' in current_url:
                    try:
                        response = requests.head(current_url)
                        if response.status_code == 200:
                            self.stdout.write(f'La imagen {idx} ya está en S3 y es accesible: {current_url}')
                            continue
                        else:
                            self.stdout.write(self.style.WARNING(f'La imagen {idx} está en S3 pero no es accesible (status: {response.status_code}): {current_url}'))
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Error al verificar imagen en S3: {str(e)}'))
                
                # Intentar obtener la imagen de su ubicación actual
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
                    
                    # Subir a S3
                    default_storage.save(s3_path, img_temp)
                    
                    # Actualizar el campo imagen con la nueva ubicación
                    imagen.imagen = s3_path
                    imagen.save()
                    
                    self.stdout.write(self.style.SUCCESS(f'Imagen {idx} migrada exitosamente a S3'))
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error al migrar imagen {idx}: {str(e)}'))
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error general al procesar imagen {idx}: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS('Migración completada')) 