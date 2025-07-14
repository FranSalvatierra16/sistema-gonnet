from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.conf import settings
import os
from pathlib import Path
from inmobiliaria.models import ImagenPropiedad

class Command(BaseCommand):
    help = 'Migra las imágenes existentes al bucket de S3'

    def handle(self, *args, **options):
        self.stdout.write('Iniciando migración de imágenes a S3...')
        
        # Obtener todas las imágenes
        imagenes = ImagenPropiedad.objects.all()
        total = imagenes.count()
        
        self.stdout.write(f'Se encontraron {total} imágenes para migrar')
        
        # Asegurarnos que estamos en el directorio correcto
        base_dir = Path(settings.MEDIA_ROOT)
        self.stdout.write(f'Directorio base de medios: {base_dir}')
        
        for idx, imagen in enumerate(imagenes, 1):
            try:
                # Obtener la ruta relativa del archivo
                relative_path = str(imagen.imagen)
                self.stdout.write(f'Procesando imagen {idx}/{total}: {relative_path}')
                
                # Construir la ruta completa
                file_path = base_dir / relative_path
                self.stdout.write(f'Buscando archivo en: {file_path}')
                
                if not os.path.exists(file_path):
                    self.stdout.write(self.style.WARNING(f'Archivo no encontrado: {file_path}'))
                    # Intentar buscar en la carpeta propiedades
                    alt_path = base_dir / 'propiedades' / os.path.basename(relative_path)
                    self.stdout.write(f'Intentando ruta alternativa: {alt_path}')
                    if os.path.exists(alt_path):
                        file_path = alt_path
                    else:
                        self.stdout.write(self.style.ERROR(f'No se encontró el archivo en ninguna ubicación'))
                        continue
                
                # Abrir y leer el archivo
                with open(file_path, 'rb') as f:
                    # Construir la ruta en S3
                    s3_path = f'media/propiedades/{os.path.basename(relative_path)}'
                    self.stdout.write(f'Subiendo a S3: {s3_path}')
                    
                    # Subir a S3
                    default_storage.save(s3_path, f)
                    
                    # Actualizar el campo imagen
                    imagen.imagen = s3_path
                    imagen.save()
                    
                    self.stdout.write(self.style.SUCCESS(f'Imagen {idx} migrada exitosamente'))
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error al procesar imagen {idx}: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS('Migración completada')) 