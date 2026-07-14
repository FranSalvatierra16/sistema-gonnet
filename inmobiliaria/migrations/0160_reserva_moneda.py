from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0159_contratoalquiler_vendedor_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='moneda',
            field=models.CharField(
                choices=[('ARS', 'Pesos (ARS)'), ('USD', 'Dólares (USD)')],
                default='ARS',
                help_text='Moneda del precio, seña, depósito y cobros de la reserva (alquiler por día).',
                max_length=3,
                verbose_name='Moneda de la operación',
            ),
        ),
    ]
