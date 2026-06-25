from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0138_reserva_sin_carpeta'),
    ]

    operations = [
        migrations.AddField(
            model_name='gastopropietario',
            name='tipo_movimiento',
            field=models.CharField(
                choices=[('egreso', 'Egreso'), ('ingreso', 'Ingreso')],
                default='egreso',
                max_length=10,
                verbose_name='Tipo de movimiento',
            ),
        ),
        migrations.AddField(
            model_name='gastopropietario',
            name='efecto_inquilino',
            field=models.CharField(
                choices=[
                    ('favor', 'A favor del inquilino'),
                    ('contra', 'En contra del inquilino'),
                ],
                default='contra',
                max_length=10,
                verbose_name='Efecto sobre el inquilino',
            ),
        ),
        migrations.AddField(
            model_name='gastopropietario',
            name='operacion_monto',
            field=models.CharField(
                choices=[('resta', 'Resta'), ('suma', 'Suma')],
                default='resta',
                help_text='Suma aumenta lo que se paga al propietario; resta lo descuenta.',
                max_length=10,
                verbose_name='Operación',
            ),
        ),
    ]
