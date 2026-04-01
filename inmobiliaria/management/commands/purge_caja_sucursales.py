"""
Elimina cajas y movimientos (CASCADE) para sucursales indicadas y abre caja nueva en $0.
Corrige la secuencia PostgreSQL de `numero` para evitar duplicate key.

Modo --todo-el-sistema: borra TODAS las cajas de la base, recrea una por cada sucursal
(numeración global desde 1 si la tabla quedó vacía antes de recrear).
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from inmobiliaria.caja_reset import purge_cajas_sucursales_y_reabrir
from inmobiliaria.models import Sucursal


class Command(BaseCommand):
    help = (
        'Elimina datos de caja (y movimientos/recibos en cascada) y abre una caja nueva en $0. '
        'Requiere --confirm. Usar --todo-el-sistema para borrar todas las cajas y renumerar desde 1.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'nombres',
            nargs='*',
            default=['Colon', 'Corrientes'],
            help='Nombres de sucursal (por defecto: Colon Corrientes)',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Obligatorio para ejecutar el borrado',
        )
        parser.add_argument(
            '--usuario-id',
            type=int,
            default=None,
            help='Usuario para usuario_apertura de las cajas nuevas',
        )
        parser.add_argument(
            '--sucursal-id',
            type=int,
            action='append',
            dest='sucursal_ids',
            default=None,
            help='ID(s) de sucursal (repetible). Si se indica, ignora nombres.',
        )
        parser.add_argument(
            '--todo-el-sistema',
            action='store_true',
            help=(
                'Borra TODAS las cajas (todas las sucursales) para reiniciar la numeración global. '
                'Si pasás nombres o --sucursal-id, solo se vuelven a abrir cajas en esas sucursales '
                '(el resto queda sin caja hasta abrirla desde el sistema). '
                'Sin nombres ni ids: reabre una caja en cada sucursal.'
            ),
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stderr.write(
                self.style.ERROR(
                    'Este comando borra datos de caja. Repetí con --confirm para ejecutar.'
                )
            )
            return

        User = get_user_model()
        uid = options['usuario_id']
        if uid:
            usuario = User.objects.filter(pk=uid).first()
            if not usuario:
                self.stderr.write(self.style.ERROR(f'No existe usuario id={uid}'))
                return
        else:
            usuario = (
                User.objects.filter(is_staff=True).order_by('id').first()
                or User.objects.filter(is_superuser=True).order_by('id').first()
                or User.objects.order_by('id').first()
            )
            if not usuario:
                self.stderr.write(self.style.ERROR('No hay usuario para asignar a la caja.'))
                return

        todo_sistema = options['todo_el_sistema']
        ids = options['sucursal_ids']

        def _resolver_sucursales():
            found = []
            if ids:
                for sid in ids:
                    s = Sucursal.objects.filter(pk=sid).first()
                    if not s:
                        self.stderr.write(self.style.WARNING(f'No existe sucursal id={sid}'))
                        continue
                    found.append(s)
            else:
                for nombre in options['nombres']:
                    n = nombre.strip()
                    if not n:
                        continue
                    s = Sucursal.objects.filter(nombre__iexact=n).first()
                    if not s:
                        s = Sucursal.objects.filter(nombre__icontains=n).first()
                    if not s:
                        self.stderr.write(self.style.WARNING(f'No se encontró sucursal: {nombre}'))
                        continue
                    found.append(s)
            return found

        if todo_sistema:
            sucursales_objetivo = _resolver_sucursales()
            if not sucursales_objetivo:
                todas = list(Sucursal.objects.order_by('id'))
                if not todas:
                    self.stderr.write(self.style.ERROR('No hay sucursales en la base.'))
                    return
                self.stdout.write(
                    self.style.WARNING(
                        'Modo TODO EL SISTEMA: se borran todas las cajas; se reabre una por '
                        f'cada sucursal ({len(todas)}).'
                    )
                )
                nuevas = purge_cajas_sucursales_y_reabrir(
                    todas,
                    usuario,
                    sistema_completo=True,
                    recrear_solo_sucursales=None,
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        'Modo TODO EL SISTEMA: se borran todas las cajas del sistema; solo se '
                        'reabren: '
                        + ', '.join(s.nombre for s in sucursales_objetivo)
                    )
                )
                nuevas = purge_cajas_sucursales_y_reabrir(
                    sucursales_objetivo,
                    usuario,
                    sistema_completo=True,
                    recrear_solo_sucursales=sucursales_objetivo,
                )
        else:
            sucursales = _resolver_sucursales()
            if not sucursales:
                self.stderr.write(self.style.ERROR('No hay sucursales válidas.'))
                return

            self.stdout.write(
                self.style.WARNING(
                    'Se eliminan solo las cajas de: '
                    + ', '.join(s.nombre for s in sucursales)
                )
            )
            nuevas = purge_cajas_sucursales_y_reabrir(
                sucursales,
                usuario,
                sistema_completo=False,
            )

        for c in nuevas:
            self.stdout.write(
                self.style.SUCCESS(
                    f'  Caja #{c.numero} abierta — {c.sucursal.nombre} — saldo inicial $0'
                )
            )
        self.stdout.write(self.style.SUCCESS(f'\nListo. {len(nuevas)} caja(s) nuevas.'))
