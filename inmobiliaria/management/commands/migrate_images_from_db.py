from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.conf import settings
import os
import mysql.connector
from io import BytesIO
from inmobiliaria.models import ImagenPropiedad

class Command(BaseCommand):
    help = 'Migra las imágenes desde MySQL a S3'

    def handle(self, *args, **options):
        self.stdout.write('Iniciando migración de imágenes desde MySQL a S3...')
        
        # Conectar a MySQL
        db = mysql.connector.connect(
            host=settings.DATABASES['default']['HOST'],
            user=settings.DATABASES['default']['USER'],
            password=settings.DATABASES['default']['PASSWORD'],
            database=settings.DATABASES['default']['NAME']
        )
        
        cursor = db.cursor()
        
        # Obtener todas las imágenes de la base de datos
        cursor.execute("""
            SELECT ip.id, ip.imagen 
            FROM inmobiliaria_imagenpropiedad ip
            WHERE ip.imagen IS NOT NULL
        """)
        
        rows = cursor.fetchall()
        total = len(rows)
        self.stdout.write(f'Se encontraron {total} imágenes para migrar')
        
        for idx, (imagen_id, imagen_path) in enumerate(rows, 1):
            try:
                self.stdout.write(f'Procesando imagen {idx}/{total} (ID: {imagen_id})')
                
                # Obtener los datos binarios de la imagen
                cursor.execute("""
                    SELECT imagen 
                    FROM django_content_type_imagenpropiedad 
                    WHERE id = %s
                """, (imagen_id,))
                
                result = cursor.fetchone()
                if not result:
                    self.stdout.write(self.style.WARNING(f'No se encontraron datos para la imagen {imagen_id}'))
                    continue
                
                image_data = result[0]
                if not image_data:
                    self.stdout.write(self.style.WARNING(f'Datos de imagen vacíos para {imagen_id}'))
                    continue
                
                # Crear un archivo temporal con el contenido
                img_temp = BytesIO(image_data)
                
                # Obtener el nombre del archivo original
                file_name = os.path.basename(imagen_path)
                
                # Construir la ruta en S3
                s3_path = f'media/propiedades/{file_name}'
                self.stdout.write(f'Subiendo a S3: {s3_path}')
                
                # Subir a S3
                default_storage.save(s3_path, img_temp)
                
                # Actualizar el registro en Django
                try:
                    imagen = ImagenPropiedad.objects.get(id=imagen_id)
                    imagen.imagen = s3_path
                    imagen.save()
                    self.stdout.write(self.style.SUCCESS(f'Imagen {idx} migrada exitosamente'))
                except ImagenPropiedad.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f'No se encontró el registro de ImagenPropiedad {imagen_id}'))
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error al procesar imagen {imagen_id}: {str(e)}'))
        
        cursor.close()
        db.close()
        
        self.stdout.write(self.style.SUCCESS('Migración completada')) 