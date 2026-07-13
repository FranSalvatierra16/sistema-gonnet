from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0157_chequemovimientocaja'),
    ]

    operations = [
        migrations.AddField(
            model_name='movimientocaja',
            name='cotizacion_dolar',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Cotización ARS por USD del día al cargar el movimiento en dólares.',
                max_digits=14,
                null=True,
            ),
        ),
    ]
