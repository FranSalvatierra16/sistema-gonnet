from django.core.management.base import BaseCommand

from inmobiliaria.models.sucursal import Sucursal
from inmobiliaria.oficina_gastos import (
    get_sucursal_referencia_categorias_oficina,
    sincronizar_categorias_gasto_oficina_desde_referencia,
    sucursal_espeja_categorias_oficina_desde_referencia,
)


class Command(BaseCommand):
    help = (
        'Copia categorías y subcategorías de gasto de oficina desde Corrientes '
        'hacia Colón (misma estructura que la sucursal de referencia).'
    )

    def handle(self, *args, **options):
        origen = get_sucursal_referencia_categorias_oficina()
        if not origen:
            self.stderr.write(self.style.ERROR('No se encontró la sucursal Corrientes.'))
            return

        destinos = [
            s for s in Sucursal.objects.all().order_by('nombre')
            if sucursal_espeja_categorias_oficina_desde_referencia(s)
        ]
        if not destinos:
            self.stderr.write(self.style.ERROR('No se encontró la sucursal Colón.'))
            return

        self.stdout.write(
            f'Origen: {origen.nombre} (id={origen.pk}) — '
            f'{origen.categorias_gasto_oficina.count()} categorías en total'
        )
        for destino in destinos:
            antes = destino.categorias_gasto_oficina.filter(activa=True).count()
            stats = sincronizar_categorias_gasto_oficina_desde_referencia(destino, origen)
            despues = destino.categorias_gasto_oficina.filter(activa=True).count()
            self.stdout.write(
                self.style.SUCCESS(
                    f'{destino.nombre} (id={destino.pk}): '
                    f'creadas={stats["creadas"]}, actualizadas={stats["actualizadas"]}, '
                    f'activas antes={antes} → después={despues}'
                )
            )
