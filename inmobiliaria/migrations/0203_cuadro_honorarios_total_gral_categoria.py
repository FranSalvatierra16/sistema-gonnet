import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0202_cuadro_honorarios_total_gral'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='cuadrohonorariostotalgral',
            name='uniq_cuadro_honorarios_total_gral_sucursal_vendedor',
        ),
        migrations.AlterField(
            model_name='cuadrohonorariostotalgral',
            name='vendedor',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='cuadro_honorarios_totales',
                to='inmobiliaria.vendedor',
            ),
        ),
        migrations.AddField(
            model_name='cuadrohonorariostotalgral',
            name='categoria',
            field=models.ForeignKey(
                blank=True,
                help_text='Fila de Sueldos sin vendedor vinculado (cargada a mano).',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='cuadro_honorarios_totales',
                to='inmobiliaria.categoriagastooficina',
            ),
        ),
    ]
