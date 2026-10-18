from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0222_vendedor_comision_marconi'),
    ]

    operations = [
        migrations.CreateModel(
            name='AjusteLiquidacionProductorMes',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('anio', models.PositiveSmallIntegerField()),
                ('mes', models.PositiveSmallIntegerField()),
                ('diferencia_sueldo', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('vendedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ajustes_liquidacion_mes', to='inmobiliaria.vendedor')),
            ],
            options={
                'verbose_name': 'Diferencia de sueldo del mes',
                'verbose_name_plural': 'Diferencias de sueldo del mes',
            },
        ),
        migrations.AddConstraint(
            model_name='ajusteliquidacionproductormes',
            constraint=models.UniqueConstraint(fields=('vendedor', 'anio', 'mes'), name='uniq_ajuste_liq_productor_mes'),
        ),
    ]
