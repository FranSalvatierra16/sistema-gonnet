# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0072_agregar_ventilador_aire_cable'),
    ]

    operations = [
        migrations.AlterField(
            model_name='inquilino',
            name='codigo_postal',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='propietario',
            name='codigo_postal',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
    ]

