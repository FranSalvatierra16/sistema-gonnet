from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0129_categoria_vales_oficina'),
    ]

    operations = [
        migrations.AddField(
            model_name='movimientocaja',
            name='fecha_transferencia',
            field=models.DateField(
                blank=True,
                help_text='Fecha real en que se acreditó o envió la transferencia/depósito (conciliación bancaria).',
                null=True,
                verbose_name='Fecha transferencia/depósito',
            ),
        ),
    ]
