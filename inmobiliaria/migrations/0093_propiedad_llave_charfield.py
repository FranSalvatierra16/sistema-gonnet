# Llave: permitir texto (ej. «coordinar») además de número

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0092_propiedad_5331_sucursal_corrientes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='propiedad',
            name='llave',
            field=models.CharField(
                blank=True,
                help_text='Número de llave o texto (ej. «coordinar» si el depto está ocupado y no hay llave física).',
                max_length=50,
                null=True,
                verbose_name='Llave',
            ),
        ),
    ]
