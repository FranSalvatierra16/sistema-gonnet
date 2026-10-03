from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0211_gastos_bancarios_caja_a_pago_iibb'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='sin_fichaje',
            field=models.BooleanField(
                default=False,
                verbose_name='Sin comisión de fichaje',
                help_text='Fichaje eliminado desde la carátula: no se genera comisión de fichaje para esta operación.',
            ),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='sin_fichaje',
            field=models.BooleanField(
                default=False,
                verbose_name='Sin comisión de fichaje',
                help_text='Fichaje eliminado desde la carátula: no se genera comisión de fichaje para este contrato.',
            ),
        ),
    ]
