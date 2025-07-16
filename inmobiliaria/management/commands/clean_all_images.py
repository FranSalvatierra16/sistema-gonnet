from django.core.management.base import BaseCommand
from inmobiliaria.models import ImagenPropiedad
from django.db import transaction

class Command(BaseCommand):
    help = 'Elimina todas las imágenes de las propiedades'

    def add_arguments(self, parser):
        parser.add_argument(
            '--propiedad',
            type=str,
            help='ID de la propiedad específica de la cual eliminar las imágenes. Si no se especifica, se eliminarán todas.',
        )

    def handle(self, *args, **options):
        propiedad_id = options.get('propiedad')
        
        try:
            with transaction.atomic():
                # Filtrar por propiedad si se especificó una
                imagenes = ImagenPropiedad.objects.all()
                if propiedad_id:
                    imagenes = imagenes.filter(propiedad_id=propiedad_id)
                
                total_imagenes = imagenes.count()
                
                if total_imagenes == 0:
                    self.stdout.write(
                        self.style.WARNING(
                            'No se encontraron imágenes para eliminar.'
                        )
                    )
                    return
                
                # Primero intentamos eliminar los archivos físicos
                for imagen in imagenes:
                    try:
                        if imagen.imagen:
                            imagen.imagen.delete(save=False)
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(
                                f'No se pudo eliminar el archivo físico de la imagen {imagen.id}: {str(e)}'
                            )
                        )
                
                # Luego eliminamos los registros de la base de datos
                imagenes.delete()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Se eliminaron exitosamente {total_imagenes} imágenes'
                        f'{" de la propiedad " + propiedad_id if propiedad_id else ""}'
                    )
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Error al eliminar las imágenes: {str(e)}'
                )
            ) 