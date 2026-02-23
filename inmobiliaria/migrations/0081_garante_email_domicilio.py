# Mail y domicilio del garante en contrato de alquiler (invierno)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0080_add_garante_contrato_alquiler'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='garante_email',
            field=models.EmailField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='garante_domicilio',
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
