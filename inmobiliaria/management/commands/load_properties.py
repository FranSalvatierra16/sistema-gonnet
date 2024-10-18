from django.core.management.base import BaseCommand
from inmobiliaria.models import Propiedad, Propietario, ImagenPropiedad
from django.core.files import File
import json
import os
from django.conf import settings

class Command(BaseCommand):
    help = 'Carga propiedades desde el archivo JSON predefinido'

    def handle(self, *args, **options):
        self.stdout.write("Comando ejecutado correctamente")
        
        # Definir la ruta al archivo JSON
        json_path = os.path.join(settings.BASE_DIR, 'inmobiliaria', 'propiedades.json')
        
        try:
            with open(json_path, 'r', encoding='utf-8') as file:
                propiedades = json.load(file)
                
                for prop in propiedades:
                    # Obtener el propietario existente por ID
                    propietario_id = prop.pop('propietario', None)
                    if propietario_id:
                        try:
                            propietario = Propietario.objects.get(id=propietario_id)
                            nombre_propietario = f"{propietario.nombre} {propietario.apellido}"
                        except Propietario.DoesNotExist:
                            self.stdout.write(self.style.WARNING(f'Propietario con ID {propietario_id} no encontrado. Saltando esta propiedad.'))
                            continue
                    else:
                        propietario = None
                        nombre_propietario = "Sin propietario"

                    # Extraer las rutas de las imágenes
                    imagenes = prop.pop('imagenes', [])

                    # Crear la propiedad
                    try:
                        propiedad = Propiedad(
                            propietario=propietario,
                            **prop
                        )
                        propiedad.save()

                        # Cargar las imágenes
                        for imagen_path in imagenes:
                            ruta_completa = os.path.join(settings.MEDIA_ROOT, imagen_path)
                            if os.path.exists(ruta_completa):
                                with open(ruta_completa, 'rb') as img_file:
                                    imagen = ImagenPropiedad(propiedad=propiedad)
                                    imagen.imagen.save(os.path.basename(imagen_path), File(img_file), save=True)
                            else:
                                self.stdout.write(self.style.WARNING(f'Imagen no encontrada: {ruta_completa}'))

                        self.stdout.write(self.style.SUCCESS(f'Propiedad creada exitosamente para propietario ID: {propietario_id}, Nombre: {nombre_propietario}'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'Error al crear propiedad para propietario ID: {propietario_id}, Nombre: {nombre_propietario}. Error: {str(e)}'))

                self.stdout.write(self.style.SUCCESS(f'Proceso de carga completado.'))
        
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'No se encontró el archivo JSON en {json_path}'))
        except json.JSONDecodeError:
            self.stdout.write(self.style.ERROR('Error al decodificar el archivo JSON'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ocurrió un error: {str(e)}'))
