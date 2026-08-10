from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0174_propiedad_propietario_desde'),
    ]

    operations = [
        migrations.AddField(
            model_name='caja',
            name='cotizacion_dolar',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='ARS por 1 USD. Se define al abrir la caja y se usa en los movimientos del día.',
                max_digits=14,
                null=True,
                verbose_name='Cotización dólar del día',
            ),
        ),
    ]
