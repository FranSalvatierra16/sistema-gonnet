from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0129_categoria_vales_oficina'),
    ]

    operations = [
        migrations.AddField(
            model_name='liquidacionpropietario',
            name='moneda',
            field=models.CharField(
                choices=[('ARS', 'Pesos (ARS)'), ('USD', 'Dólares (USD)')],
                default='ARS',
                help_text='Moneda en la que se expresan los montos de esta liquidación.',
                max_length=3,
                verbose_name='Moneda',
            ),
        ),
        migrations.AddField(
            model_name='gastopropietario',
            name='moneda',
            field=models.CharField(
                choices=[('ARS', 'Pesos (ARS)'), ('USD', 'Dólares (USD)')],
                default='ARS',
                max_length=3,
                verbose_name='Moneda',
            ),
        ),
    ]
