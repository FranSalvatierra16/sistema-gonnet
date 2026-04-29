from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0108_movimientocaja_fecha_eliminacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='neto_a_posesion_referencia',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Saldo neto de la operación inicial (recibo): total a abonar menos lo efectivamente pagado.',
                max_digits=12,
                verbose_name='Neto a la posesión (referencia)',
            ),
        ),
    ]
