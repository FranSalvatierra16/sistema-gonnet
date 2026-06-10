from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0121_caja_arqueo_manual'),
    ]

    operations = [
        migrations.AddField(
            model_name='movimientocaja',
            name='monto_a_oficina',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Parte del total que corresponde a la oficina / depto.',
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name='movimientocaja',
            name='monto_a_propietario',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Parte del total que corresponde al propietario.',
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name='movimientocaja',
            name='monto_a_inquilino',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Parte del total que corresponde al inquilino.',
                max_digits=14,
            ),
        ),
    ]
