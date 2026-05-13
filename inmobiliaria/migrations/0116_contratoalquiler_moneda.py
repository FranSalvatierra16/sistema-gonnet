from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0115_vendedor_nivel_super_admin'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='moneda',
            field=models.CharField(
                choices=[('ARS', 'Pesos (ARS)'), ('USD', 'Dólares (USD)')],
                default='ARS',
                help_text='Moneda en la que se expresan el precio mensual y las cuotas del plan.',
                max_length=3,
                verbose_name='Moneda de cuotas',
            ),
        ),
    ]
