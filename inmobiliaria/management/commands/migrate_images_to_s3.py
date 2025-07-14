from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.conf import settings
import os
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
                # Verificar si la imagen existe localmente
                local_path = os.path.join(settings.MEDIA_ROOT, str(imagen.imagen))
                if os.path.exists(local_path):
                    # Abrir el archivo local
                    with open(local_path, 'rb') as f:
                        # Construir la ruta en S3
                        s3_path = f'propiedades/{os.path.basename(local_path)}'
                        
                        # Subir a S3
                        default_storage.save(s3_path, f)
                        
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'[{idx}/{total}] Migrada imagen {s3_path}'
                            )
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'[{idx}/{total}] No se encontró el archivo local: {local_path}'
                        )
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'[{idx}/{total}] Error al migrar imagen {imagen.imagen}: {str(e)}'
                    )
                )
        
        self.stdout.write(self.style.SUCCESS('Migración completada')) 