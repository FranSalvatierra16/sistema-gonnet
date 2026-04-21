import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0105_corregir_rol_comision_linea_unica'),
    ]

    operations = [
        migrations.CreateModel(
            name='MesComisionPagadoVendedor',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('anio', models.PositiveIntegerField(verbose_name='Año')),
                ('mes', models.PositiveSmallIntegerField(help_text='1–12', verbose_name='Mes')),
                ('creado_en', models.DateTimeField(auto_now_add=True, verbose_name='Marcado el')),
                (
                    'vendedor',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='meses_comision_pagados',
                        to='inmobiliaria.vendedor',
                        verbose_name='Vendedor',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Mes comisiones/vales pagado (vendedor)',
                'verbose_name_plural': 'Meses comisiones/vales pagados',
                'ordering': ['-anio', '-mes'],
                'unique_together': {('vendedor', 'anio', 'mes')},
            },
        ),
    ]
