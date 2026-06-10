from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0124_cartera_propietario_ref'),
    ]

    operations = [
        migrations.AddField(
            model_name='cajaarqueomanual',
            name='anteriores_json',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Saldos ANTERIOR por medio (fijos). El saldo actual = anterior + ingresos − egresos.',
            ),
        ),
    ]
