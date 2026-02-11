# Campo para guardar JSON completo de conceptos (recibos de contrato)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0077_contratoalquiler_dia_vencimiento_default_5'),
    ]

    operations = [
        migrations.AddField(
            model_name='movimientocaja',
            name='concepto_detalle',
            field=models.TextField(blank=True, help_text='JSON completo de conceptos para recibos de contrato'),
        ),
    ]
