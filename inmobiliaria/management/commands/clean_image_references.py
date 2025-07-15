from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.conf import settings
import requests
from inmobiliaria.models import ImagenPropiedad

class Command(BaseCommand):
    help = 'Limpia las referencias a imágenes que ya no existen y verifica las que están en S3'

    def handle(self, *args, **options):
        self.stdout.write('Iniciando verificación de imágenes...')
        
        # Obtener todas las imágenes
        imagenes = ImagenPropiedad.objects.all()
        total = imagenes.count()
        
        self.stdout.write(f'Se encontraron {total} imágenes para verificar')
        
        imagenes_ok = 0
        imagenes_error = 0
        
        for idx, imagen in enumerate(imagenes, 1):
            try:
                imagen_url = str(imagen.imagen)
                self.stdout.write(f'Verificando imagen {idx}/{total}: {imagen_url}')
                
                # Si la imagen está en S3
                if 's3.amazonaws.com' in imagen_url:
                    try:
                        # Verificar si la imagen es accesible
                        response = requests.head(imagen_url, timeout=10)
                        if response.status_code == 200:
                            self.stdout.write(self.style.SUCCESS(f'Imagen {idx} OK en S3: {imagen_url}'))
                            imagenes_ok += 1
                            continue
                        else:
                            self.stdout.write(self.style.WARNING(f'Imagen {idx} en S3 pero no accesible: {imagen_url}'))
                            imagen.imagen = ''
                            imagen.save()
                            imagenes_error += 1
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'Error al verificar imagen en S3: {str(e)}'))
                        imagen.imagen = ''
                        imagen.save()
                        imagenes_error += 1
                else:
                    # Si la imagen no está en S3, limpiar la referencia
                    self.stdout.write(self.style.WARNING(f'Imagen {idx} no está en S3, limpiando referencia: {imagen_url}'))
                    imagen.imagen = ''
                    imagen.save()
                    imagenes_error += 1
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error al procesar imagen {idx}: {str(e)}'))
                imagenes_error += 1
        
        self.stdout.write('\nResumen:')
        self.stdout.write(f'Total de imágenes procesadas: {total}')
        self.stdout.write(self.style.SUCCESS(f'Imágenes correctas en S3: {imagenes_ok}'))
        self.stdout.write(self.style.ERROR(f'Imágenes con error o limpiadas: {imagenes_error}'))
        self.stdout.write('\nVerificación completada') 