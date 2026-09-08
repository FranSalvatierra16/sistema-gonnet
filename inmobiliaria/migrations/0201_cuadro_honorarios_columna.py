import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0200_sueldo_basico_vigencia'),
    ]

    operations = [
        migrations.CreateModel(
            name='CuadroHonorariosColumna',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'sucursal',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cuadro_honorarios_columnas',
                        to='inmobiliaria.sucursal',
                    ),
                ),
                (
                    'vendedor',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cuadro_honorarios_columnas',
                        to='inmobiliaria.vendedor',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Columna de planilla de honorarios',
                'verbose_name_plural': 'Columnas de planilla de honorarios',
            },
        ),
        migrations.AddConstraint(
            model_name='cuadrohonorarioscolumna',
            constraint=models.UniqueConstraint(
                fields=('sucursal', 'vendedor'),
                name='uniq_cuadro_honorarios_sucursal_vendedor',
            ),
        ),
    ]
