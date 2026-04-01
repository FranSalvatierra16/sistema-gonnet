"""
Lógica compartida para dejar la caja de una sucursal en cero: cierra abiertas y abre una nueva sin movimientos.
"""
from decimal import Decimal

from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone

from inmobiliaria.models import Caja, MovimientoCaja, Sucursal


def sync_postgres_serial_sequence(table_name: str, column_name: str, model_cls):
    """
    Tras borrar filas, alinea la secuencia SERIAL con MAX(column) para evitar
    duplicate key (numero)=(N) already exists.
    """
    if connection.vendor != 'postgresql':
        return
    max_v = model_cls.objects.aggregate(m=Max(column_name))['m']
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT pg_get_serial_sequence(%s, %s)',
            [table_name, column_name],
        )
        row = cursor.fetchone()
        seq = row[0] if row else None
        if not seq:
            return
        if max_v is None:
            cursor.execute('SELECT setval(%s, 1, false)', [seq])
        else:
            cursor.execute('SELECT setval(%s, %s, true)', [seq, max_v])


def sync_caja_y_movimiento_sequences():
    """Sincroniza secuencias PK de caja (numero) y movimiento (id) en PostgreSQL."""
    sync_postgres_serial_sequence('inmobiliaria_caja', 'numero', Caja)
    sync_postgres_serial_sequence('inmobiliaria_movimientocaja', 'id', MovimientoCaja)


def purge_cajas_sucursales_y_reabrir(
    sucursales,
    usuario,
    sistema_completo: bool = False,
    recrear_solo_sucursales=None,
):
    """
    Elimina registros de Caja (CASCADE: movimientos, recibos vinculados, etc.).

    - sistema_completo=False: borra solo cajas de `sucursales` y recrea una por cada una.
    - sistema_completo=True: borra TODAS las cajas. Si `recrear_solo_sucursales` es una lista
      no vacía, solo abre caja nueva en esas sucursales (el resto queda sin caja). Si es None,
      abre una caja en cada sucursal del sistema.

    Returns:
        list: cajas nuevas creadas
    """
    sucursales = list(sucursales)
    if not sucursales and not sistema_completo:
        return []

    with transaction.atomic():
        if sistema_completo:
            Caja.objects.all().delete()
        else:
            Caja.objects.filter(sucursal__in=sucursales).delete()

        sync_caja_y_movimiento_sequences()

        if sistema_completo:
            if recrear_solo_sucursales is not None:
                a_crear = list(
                    Sucursal.objects.filter(
                        pk__in=[s.pk for s in recrear_solo_sucursales]
                    ).order_by('id')
                )
            else:
                a_crear = list(Sucursal.objects.order_by('id'))
        else:
            a_crear = sucursales

        nuevas = []
        for sucursal in a_crear:
            nuevas.append(
                Caja.objects.create(
                    sucursal=sucursal,
                    saldo_inicial=Decimal('0.00'),
                    estado='abierta',
                    usuario_apertura=usuario,
                    observaciones_apertura='Caja nueva tras eliminación de historial de caja (purge)',
                )
            )
        return nuevas


def reset_caja_sucursal_desde_cero(sucursal, usuario, observacion_cierre_extra='[Cierre automático reset caja]'):
    """
    Cierra todas las cajas abiertas de la sucursal y crea una nueva con saldo_inicial=0.

    No elimina movimientos: quedan asociados a las cajas cerradas.

    Returns:
        tuple: (nueva_caja, lista de cajas cerradas)
    """
    abiertas = list(
        Caja.objects.filter(sucursal=sucursal, estado='abierta').order_by('numero')
    )
    cerradas = []

    with transaction.atomic():
        for caja in abiertas:
            saldo_final = caja.get_saldo_actual()
            caja.fecha_cierre = timezone.now()
            caja.estado = 'cerrada'
            caja.saldo_final = saldo_final
            caja.usuario_cierre = usuario
            extra = observacion_cierre_extra.strip()
            if extra:
                caja.observaciones_cierre = (
                    (caja.observaciones_cierre or '').strip() + '\n' + extra
                ).strip()
            caja.save(
                update_fields=[
                    'fecha_cierre',
                    'estado',
                    'saldo_final',
                    'usuario_cierre',
                    'observaciones_cierre',
                ]
            )
            cerradas.append(caja)

        nueva = Caja.objects.create(
            sucursal=sucursal,
            saldo_inicial=Decimal('0.00'),
            estado='abierta',
            usuario_apertura=usuario,
            observaciones_apertura='Apertura tras reset de caja (saldo desde cero)',
        )

    return nueva, cerradas
