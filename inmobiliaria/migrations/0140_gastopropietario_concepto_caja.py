from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0139_gastopropietario_movimiento'),
    ]

    operations = [
        migrations.AddField(
            model_name='gastopropietario',
            name='concepto_caja_id',
            field=models.CharField(
                blank=True,
                help_text='ID del concepto del catálogo de caja',
                max_length=20,
                verbose_name='Concepto caja',
            ),
        ),
    ]
