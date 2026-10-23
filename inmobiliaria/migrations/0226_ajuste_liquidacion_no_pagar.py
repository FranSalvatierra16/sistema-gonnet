from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0225_cuotamensual_es_proporcional'),
    ]

    operations = [
        migrations.AddField(
            model_name='ajusteliquidacionproductormes',
            name='no_pagar',
            field=models.BooleanField(
                default=False,
                help_text='Este mes no se le paga: el detalle se ve y el total de la columna queda en 0.',
            ),
        ),
    ]
