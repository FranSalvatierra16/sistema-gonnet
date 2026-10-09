from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0217_invierno_precio_desde_estudiante'),
    ]

    operations = [
        migrations.AddField(
            model_name='gastooficina',
            name='reciclable',
            field=models.BooleanField(
                default=False,
                help_text='Se informa aparte en el cierre (no cambia los totales).',
                verbose_name='Gasto reciclable',
            ),
        ),
    ]
