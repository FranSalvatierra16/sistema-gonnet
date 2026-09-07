from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0199_vendedor_sueldo_basico'),
    ]

    operations = [
        migrations.CreateModel(
            name='SueldoBasicoVigencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vigente_desde', models.DateField(help_text='Primer día del mes desde el que rige este básico.')),
                ('monto', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                (
                    'vendedor',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='sueldos_basicos_vigencia',
                        to='inmobiliaria.vendedor',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Sueldo básico por vigencia',
                'verbose_name_plural': 'Sueldos básicos por vigencia',
                'ordering': ['vendedor_id', '-vigente_desde'],
            },
        ),
        migrations.AddConstraint(
            model_name='sueldobasicovigencia',
            constraint=models.UniqueConstraint(
                fields=('vendedor', 'vigente_desde'),
                name='uniq_sueldo_basico_vigencia_vendedor_desde',
            ),
        ),
    ]
