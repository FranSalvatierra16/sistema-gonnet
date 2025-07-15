from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.conf import settings
import os
import requests
from io import BytesIO
from inmobiliaria.models import ImagenPropiedad
from urllib.parse import urlparse

class Command(BaseCommand):
    help = 'Migra las imágenes existentes al bucket de S3'

    def handle(self, *args, **options):
        self.stdout.write('Iniciando migración de imágenes desde MySQL a S3...')
        
        # Obtener todas las imágenes
        imagenes = ImagenPropiedad.objects.all()
        total = imagenes.count()
        
        self.stdout.write(f'Se encontraron {total} imágenes para migrar')
        
        for idx, imagen in enumerate(imagenes, 1):
            try:
                # Obtener la ruta de la imagen
                imagen_path = str(imagen.imagen)
                self.stdout.write(f'Procesando imagen {idx}/{total}: {imagen_path}')
                
                # Si ya está en S3, saltamos
                if 's3.amazonaws.com' in imagen_path:
                    self.stdout.write(f'La imagen {idx} ya está en S3: {imagen_path}')
                    continue
                
                # Construir la URL completa
                if imagen_path.startswith('http'):
                    url = imagen_path
                else:
                    if not imagen_path.startswith('/'):
                        imagen_path = '/' + imagen_path
                    if not imagen_path.startswith('/media/'):
                        imagen_path = '/media' + imagen_path
                    url = f"https://gonnet-interno.herokuapp.com{imagen_path}"
                
                self.stdout.write(f'Intentando descargar desde: {url}')
                
                # Intentar descargar la imagen
                try:
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    
                    # Verificar que realmente obtuvimos una imagen
                    content_type = response.headers.get('content-type', '')
                    if not content_type.startswith('image/'):
                        raise ValueError(f'El contenido no es una imagen: {content_type}')
                    
                    # Crear un archivo temporal con el contenido
                    img_temp = BytesIO(response.content)
                    
                    # Obtener el nombre del archivo
                    file_name = os.path.basename(imagen_path)
                    
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