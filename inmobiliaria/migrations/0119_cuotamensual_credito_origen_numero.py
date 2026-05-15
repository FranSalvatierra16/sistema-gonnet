from decimal import Decimal

from django.db import migrations, models


def asignar_credito_origen_existente(apps, schema_editor):
    CuotaMensual = apps.get_model('inmobiliaria', 'CuotaMensual')
    for c in (
        CuotaMensual.objects.filter(credito_aplicado__gt=Decimal('0.01'))
        .filter(credito_origen_numero_cuota__isnull=True)
        .iterator(chunk_size=500)
    ):
        prev = (
            CuotaMensual.objects.filter(
                contrato_id=c.contrato_id,
                estado__in=['pagada', 'pagada_con_mora'],
                numero_cuota__lt=c.numero_cuota,
            )
            .order_by('-numero_cuota')
            .values_list('numero_cuota', flat=True)
            .first()
        )
        if prev is not None:
            CuotaMensual.objects.filter(pk=c.pk).update(credito_origen_numero_cuota=int(prev))


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0118_cuotamensual_credito_aplicado'),
    ]

    operations = [
        migrations.AddField(
            model_name='cuotamensual',
            name='credito_origen_numero_cuota',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name='Crédito procedente de cuota N',
                help_text='Si credito_aplicado viene de un excedente al pagar la cuota N, guarda N para revertir al anular ese cobro.',
            ),
        ),
        migrations.RunPython(asignar_credito_origen_existente, migrations.RunPython.noop),
    ]
