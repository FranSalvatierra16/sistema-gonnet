from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0149_operacion_productor'),
    ]

    operations = [
        migrations.AddField(
            model_name='sucursal',
            name='vacaciones_invierno_desde',
            field=models.DateField(
                blank=True,
                help_text='Día y mes de inicio (el año se ignora; se repite cada año). Vacío = todo julio.',
                null=True,
                verbose_name='Vacaciones de invierno — desde',
            ),
        ),
        migrations.AddField(
            model_name='sucursal',
            name='vacaciones_invierno_hasta',
            field=models.DateField(
                blank=True,
                help_text='Día y mes de fin inclusive. Debe cargarse junto con «desde».',
                null=True,
                verbose_name='Vacaciones de invierno — hasta',
            ),
        ),
    ]
