from django.core.management.base import BaseCommand
from inmobiliaria.models import ImagenPropiedad
from django.db import connection

class Command(BaseCommand):
    help = 'Elimina todos los registros de imágenes de la base de datos'

    def handle(self, *args, **options):
        try:
            # Obtener el total de imágenes antes de eliminar
            total = ImagenPropiedad.objects.count()
            
            # Eliminar directamente de la base de datos
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM inmobiliaria_imagenpropiedad')
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Se eliminaron exitosamente {total} registros de imágenes de la base de datos'
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Error al eliminar los registros: {str(e)}'
                )
            ) 