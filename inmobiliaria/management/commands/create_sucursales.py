from django.core.management.base import BaseCommand
from inmobiliaria.models import Sucursal

class Command(BaseCommand):
    help = 'Crea las sucursales iniciales'

    def handle(self, *args, **kwargs):
        sucursales = [
            {
                'nombre': 'MORENO',
                'direccion': 'Dirección Moreno',
                'telefono': '123456789',
                'email': 'moreno@inmobiliaria.com',
            },
            {
                'nombre': 'COLON',
                'direccion': 'Dirección Colon',
                'telefono': '987654321',
                'email': 'colon@inmobiliaria.com',
            },
        ]

        for sucursal_data in sucursales:
            Sucursal.objects.get_or_create(
                nombre=sucursal_data['nombre'],
                defaults=sucursal_data
            )