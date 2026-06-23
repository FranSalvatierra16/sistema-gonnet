from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0134_liquidacion_comisiones_locador_locatario'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='es_alquiler_sindicato',
            field=models.BooleanField(
                default=False,
                help_text='Reserva informativa: figura en el historial pero no bloquea disponibilidad.',
                verbose_name='Alquiler sindicato',
            ),
        ),
        migrations.AlterField(
            model_name='historialdisponibilidad',
            name='estado',
            field=models.CharField(
                choices=[
                    ('libre', 'Libre'),
                    ('reservado', 'Reservado'),
                    ('alquilado', 'Operación'),
                    ('alquiler_sindicato', 'Alquiler sindicato'),
                ],
                default='libre',
                max_length=20,
            ),
        ),
    ]
