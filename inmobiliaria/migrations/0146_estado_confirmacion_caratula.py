from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0145_confirmar_comisiones_contrato'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='estado_confirmacion_caratula',
            field=models.CharField(
                choices=[('pendiente', 'Pendiente'), ('confirmada', 'Confirmada')],
                default='pendiente',
                help_text='Revisión administrativa de la carátula (independiente de comisiones y pagos).',
                max_length=12,
                verbose_name='Estado carátula',
            ),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='estado_confirmacion_caratula',
            field=models.CharField(
                choices=[('pendiente', 'Pendiente'), ('confirmada', 'Confirmada')],
                default='pendiente',
                help_text='Revisión administrativa de la carátula (independiente de comisiones y pagos).',
                max_length=12,
                verbose_name='Estado carátula',
            ),
        ),
    ]
