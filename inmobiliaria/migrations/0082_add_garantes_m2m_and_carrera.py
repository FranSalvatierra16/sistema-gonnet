# Garantes como Inquilinos (M2M) y campo Carrera para contrato estudiante

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0081_garante_email_domicilio'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='carrera',
            field=models.CharField(blank=True, max_length=200, verbose_name='Carrera'),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='garantes',
            field=models.ManyToManyField(
                blank=True,
                related_name='contratos_como_garante',
                to='inmobiliaria.inquilino',
                verbose_name='Garantes',
            ),
        ),
    ]
