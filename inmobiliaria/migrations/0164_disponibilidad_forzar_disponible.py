from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0163_operacionproductor_porcentaje_participacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='disponibilidad',
            name='forzar_disponible',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Disponibilidad superpuesta forzada: la propiedad aparece para alquiler '
                    'por día en estas fechas aunque ya haya otra disponibilidad o una reserva.'
                ),
                verbose_name='Forzar disponible',
            ),
        ),
    ]
