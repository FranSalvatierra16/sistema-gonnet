import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0201_cuadro_honorarios_columna'),
    ]

    operations = [
        migrations.CreateModel(
            name='CuadroHonorariosTotalGral',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'sucursal',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cuadro_honorarios_totales',
                        to='inmobiliaria.sucursal',
                    ),
                ),
                (
                    'vendedor',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cuadro_honorarios_totales',
                        to='inmobiliaria.vendedor',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Productor en TOTAL GRAL',
                'verbose_name_plural': 'Productores en TOTAL GRAL',
            },
        ),
        migrations.AddConstraint(
            model_name='cuadrohonorariostotalgral',
            constraint=models.UniqueConstraint(
                fields=('sucursal', 'vendedor'),
                name='uniq_cuadro_honorarios_total_gral_sucursal_vendedor',
            ),
        ),
    ]
