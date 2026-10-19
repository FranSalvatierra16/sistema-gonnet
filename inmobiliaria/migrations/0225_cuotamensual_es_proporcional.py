from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0224_cierre_oficina_mes'),
    ]

    operations = [
        migrations.AddField(
            model_name='cuotamensual',
            name='es_proporcional',
            field=models.BooleanField(
                default=False,
                help_text='Días anteriores al inicio del plan (ej. octubre de un 24 meses que empieza en noviembre). No cuenta como mes del contrato.',
            ),
        ),
    ]
