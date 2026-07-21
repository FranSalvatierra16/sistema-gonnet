# Generated manually for OperacionProductor.porcentaje_participacion

from decimal import Decimal

from django.db import migrations, models


def backfill_participaciones(apps, schema_editor):
    OperacionProductor = apps.get_model('inmobiliaria', 'OperacionProductor')
    from collections import defaultdict

    grupos = defaultdict(list)
    for op in OperacionProductor.objects.all().order_by('orden', 'id'):
        key = ('r', op.reserva_id) if op.reserva_id else ('c', op.contrato_id)
        grupos[key].append(op)

    for ops in grupos.values():
        n = len(ops)
        if n == 0:
            continue
        if n == 1:
            ops[0].porcentaje_participacion = Decimal('100')
            ops[0].save(update_fields=['porcentaje_participacion'])
            continue
        cada = (Decimal('100') / n).quantize(Decimal('0.01'))
        assigned = Decimal('0')
        for i, op in enumerate(ops):
            if i == n - 1:
                op.porcentaje_participacion = Decimal('100') - assigned
            else:
                op.porcentaje_participacion = cada
                assigned += cada
            op.save(update_fields=['porcentaje_participacion'])


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0162_gastooficina_reparto_sucursales'),
    ]

    operations = [
        migrations.AddField(
            model_name='operacionproductor',
            name='porcentaje_participacion',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('100'),
                help_text='Porcentaje de la operación que corresponde a este productor (ej. 50 si hay dos a partes iguales). Sobre esa parte se aplica su % de comisión.',
                max_digits=5,
                verbose_name='% participación en la operación',
            ),
        ),
        migrations.RunPython(backfill_participaciones, migrations.RunPython.noop),
    ]
