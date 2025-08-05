# Generated manually to add fecha_operacion field

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0022_simple_contract_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='fecha_operacion',
            field=models.DateField(default=django.utils.timezone.now, help_text='Fecha en que se realiza la operación'),
        ),
    ] 