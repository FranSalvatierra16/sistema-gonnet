# Saldo y montos de caja: decimal(10,2) overflow > ~100M — ampliar a 14 dígitos.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0089_sucursal_porcentaje_comision_default'),
    ]

    operations = [
        migrations.AlterField(
            model_name='caja',
            name='saldo_inicial',
            field=models.DecimalField(decimal_places=2, max_digits=14),
        ),
        migrations.AlterField(
            model_name='caja',
            name='saldo_final',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=14, null=True
            ),
        ),
        migrations.AlterField(
            model_name='movimientocaja',
            name='monto_efectivo',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name='movimientocaja',
            name='monto_cheque',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name='movimientocaja',
            name='monto_tarjeta',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name='movimientocaja',
            name='monto_deposito',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name='movimientocaja',
            name='honorarios',
            field=models.DecimalField(
                blank=True, decimal_places=2, default=0, max_digits=14
            ),
        ),
        migrations.AlterField(
            model_name='movimientocaja',
            name='sellados',
            field=models.DecimalField(
                blank=True, decimal_places=2, default=0, max_digits=14
            ),
        ),
        migrations.AlterField(
            model_name='registro',
            name='liquidacion',
            field=models.DecimalField(decimal_places=2, max_digits=14),
        ),
        migrations.AlterField(
            model_name='registro',
            name='efectivo',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name='registro',
            name='cheques',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name='registro',
            name='tarjeta',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name='registro',
            name='deposito',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name='registro',
            name='qr',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
    ]
