from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0161_liquidacionpropietario_cotizacion_dolar'),
    ]

    operations = [
        migrations.AddField(
            model_name='gastooficina',
            name='porcentaje',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Porcentaje del total en el reparto Colón / Corrientes.',
                max_digits=5,
                null=True,
                verbose_name='% imputado a esta sucursal',
            ),
        ),
        migrations.AddField(
            model_name='gastooficina',
            name='monto_total',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Monto completo antes de repartir entre sucursales.',
                max_digits=14,
                null=True,
                verbose_name='Monto total del movimiento',
            ),
        ),
        migrations.AddField(
            model_name='gastooficina',
            name='gasto_relacionado',
            field=models.ForeignKey(
                blank=True,
                help_text='Par del reparto Colón ↔ Corrientes.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='gastos_reparto_pareja',
                to='inmobiliaria.gastooficina',
                verbose_name='Gasto en la otra sucursal',
            ),
        ),
    ]
