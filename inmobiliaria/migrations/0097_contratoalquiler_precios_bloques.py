from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0096_contratoalquiler_honorarios_sellados_referencia'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='precios_bloques',
            field=models.JSONField(
                blank=True,
                help_text='Opcional: importes por bloque de 3 meses desde el 2.º trimestre; vacío = mismo valor que el trimestre anterior.',
                null=True,
                verbose_name='Precios por trimestre (opcional)',
            ),
        ),
    ]
