# Generated by Django 4.2.7 on 2025-01-10 12:49

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0026_alter_precio_tipo_precio'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='disponibilidad',
            options={'ordering': ['fecha_inicio'], 'verbose_name': 'Disponibilidad', 'verbose_name_plural': 'Disponibilidades'},
        ),
    ]
