# Generated manually for adding anotaciones field to Propiedad

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0049_add_es_manual_to_disponibilidad'),
    ]

    operations = [
        migrations.AddField(
            model_name='propiedad',
            name='anotaciones',
            field=models.TextField(blank=True, help_text='Notas y observaciones sobre la propiedad', null=True, verbose_name='Anotaciones'),
        ),
    ]
