from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0238_transferenciamovimientocaja'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='fecha_salida',
            field=models.DateField(
                blank=True,
                help_text='Día en que se hace la salida (puede cargarse desde el listado).',
                null=True,
                verbose_name='Fecha de salida (operativa)',
            ),
        ),
    ]
