from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0099_liquidacionpropietario_monto_fondo_mantenimiento'),
    ]

    operations = [
        migrations.AddField(
            model_name='movimientocaja',
            name='tarjeta_numero',
            field=models.CharField(
                blank=True,
                help_text='Referencia o últimos dígitos; opcional',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='movimientocaja',
            name='tarjeta_cupon',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='movimientocaja',
            name='tarjeta_tipo',
            field=models.CharField(
                blank=True,
                choices=[('credito', 'Crédito'), ('debito', 'Débito')],
                default='',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='movimientocaja',
            name='cheque_numero',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='movimientocaja',
            name='cheque_banco',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='movimientocaja',
            name='cheque_fecha_vencimiento',
            field=models.DateField(blank=True, null=True),
        ),
    ]
