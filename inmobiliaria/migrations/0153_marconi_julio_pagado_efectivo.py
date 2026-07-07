# Una sola vez: lote Marconi 18/07–02/08/2026 pagado en efectivo (no sindicato).
# Sin lógica automática en runtime; solo corrige datos en BD.

from datetime import date
from decimal import Decimal

from django.db import migrations
from django.db.models import Q


def marcar_lote_marconi_julio_pagado_efectivo(apps, schema_editor):
    Reserva = apps.get_model('inmobiliaria', 'Reserva')

    fecha_ingreso = date(2026, 7, 18)
    fecha_egreso = date(2026, 8, 2)

    candidatas = (
        Reserva.objects.filter(
            eliminada=False,
            fecha_fin=fecha_egreso,
            fecha_inicio__gte=fecha_ingreso,
        )
        .filter(
            Q(cliente__apellido__icontains='marconi')
            | Q(cliente__nombre__icontains='marconi')
        )
        .select_related('cliente')
    )

    propiedad_ids: set[int] = set()
    actualizadas = 0

    for reserva in candidatas.iterator(chunk_size=100):
        precio = Decimal(str(reserva.precio_total or 0))
        if precio <= Decimal('1.01'):
            continue
        senia = Decimal(str(reserva.senia or 0))
        if (
            (reserva.estado or '') == 'pagada'
            and not reserva.es_alquiler_sindicato
            and senia >= precio - Decimal('0.01')
        ):
            continue

        reserva.es_alquiler_sindicato = False
        reserva.senia = precio
        reserva.cuota_pendiente = Decimal('0')
        reserva.estado = 'pagada'
        reserva.save(
            update_fields=['es_alquiler_sindicato', 'senia', 'cuota_pendiente', 'estado']
        )
        actualizadas += 1
        if reserva.propiedad_id:
            propiedad_ids.add(reserva.propiedad_id)

    if not propiedad_ids:
        return

    from inmobiliaria.models import Reserva as ReservaReal

    for propiedad_id in sorted(propiedad_ids):
        primera = (
            ReservaReal.objects.filter(propiedad_id=propiedad_id, eliminada=False)
            .order_by('fecha_inicio')
            .first()
        )
        if primera:
            primera.reconstruir_historial_cronologico()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0152_categorias_gasto_personalizadas_al_final'),
    ]

    operations = [
        migrations.RunPython(marcar_lote_marconi_julio_pagado_efectivo, noop),
    ]
