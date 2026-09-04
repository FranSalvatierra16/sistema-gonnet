# Multiple vendedores + fichaje en OperacionVenta

from django.conf import settings
from django.db import migrations, models


def backfill_vendedores_m2m(apps, schema_editor):
    OperacionVenta = apps.get_model('inmobiliaria', 'OperacionVenta')
    for op in OperacionVenta.objects.exclude(vendedor_id=None).iterator():
        op.vendedores.add(op.vendedor_id)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inmobiliaria', '0195_inferir_errores_lotes_masivos'),
    ]

    operations = [
        migrations.AddField(
            model_name='operacionventa',
            name='fichado_por',
            field=models.ForeignKey(
                blank=True,
                help_text='Quien fichó la propiedad (puede generar comisión de fichaje).',
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='operaciones_venta_fichaje',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Fichaje',
            ),
        ),
        migrations.AddField(
            model_name='operacionventa',
            name='vendedores',
            field=models.ManyToManyField(
                blank=True,
                help_text='Uno o más productores que intervinieron en la venta (reparten honorarios).',
                related_name='operaciones_venta_participacion',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Vendedores / productores',
            ),
        ),
        migrations.AlterField(
            model_name='operacionventa',
            name='vendedor',
            field=models.ForeignKey(
                help_text='Vendedor principal (el primero de la lista si hay varios).',
                on_delete=models.deletion.PROTECT,
                related_name='operaciones_venta',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Vendedor / productor',
            ),
        ),
        migrations.RunPython(backfill_vendedores_m2m, migrations.RunPython.noop),
    ]
