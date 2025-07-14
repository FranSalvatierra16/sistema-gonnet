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
        
        # URL base de la aplicación
        BASE_URL = 'https://gonnet-interno.herokuapp.com'
        
        for idx, imagen in enumerate(imagenes, 1):
            try:
                # Obtener la URL actual
                current_url = str(imagen.imagen)
                self.stdout.write(f'Procesando imagen {idx}/{total}: {current_url}')
                
                # Si ya está en S3, intentar descargarla de ahí
                if 's3.amazonaws.com' in current_url:
                    url_to_try = current_url
                else:
                    # Si no está en S3, construir la URL completa
                    # Asegurarnos de que la ruta comience con /media/
                    if not current_url.startswith('/'):
                        current_url = '/' + current_url
                    if not current_url.startswith('/media/'):
                        current_url = '/media' + current_url
                    url_to_try = f"{BASE_URL}{current_url}"
                
                self.stdout.write(f'Intentando descargar desde: {url_to_try}')
                
                # Intentar descargar la imagen
                try:
                    response = requests.get(url_to_try, timeout=30)
                    response.raise_for_status()  # Esto lanzará una excepción si el status no es 200
                    
                    # Verificar que realmente obtuvimos una imagen
                    content_type = response.headers.get('content-type', '')
                    if not content_type.startswith('image/'):
                        raise ValueError(f'El contenido no es una imagen: {content_type}')
                    
                    # Crear un archivo temporal con el contenido
                    img_temp = BytesIO(response.content)
                    
                    # Obtener el nombre del archivo
                    file_name = os.path.basename(current_url)
                    
                    # Construir la ruta en S3
                    s3_path = f'media/propiedades/{file_name}'
                    self.stdout.write(f'Subiendo a S3: {s3_path}')
                    
                    # Subir a S3
                    default_storage.save(s3_path, img_temp)
                    
                    # Actualizar el campo imagen
                    imagen.imagen = s3_path
                    imagen.save()
                    
                    self.stdout.write(self.style.SUCCESS(f'Imagen {idx} migrada exitosamente'))
                    
                except requests.exceptions.RequestException as e:
                    self.stdout.write(self.style.ERROR(f'Error al descargar la imagen: {str(e)}'))
                except ValueError as e:
                    self.stdout.write(self.style.ERROR(str(e)))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error al procesar la imagen: {str(e)}'))
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error general al procesar imagen {idx}: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS('Migración completada')) 