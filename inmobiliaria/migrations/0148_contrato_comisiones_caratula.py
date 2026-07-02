from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0147_comisiones_fichaje_invierno_24'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='caratula_comision_locador',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Override manual desde carátula cuando aún no hay liquidación al propietario.',
                max_digits=12,
                null=True,
                verbose_name='Comisión locador (carátula)',
            ),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='caratula_comision_locatario',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Override manual desde carátula cuando aún no hay liquidación al propietario.',
                max_digits=12,
                null=True,
                verbose_name='Comisión locatario (carátula)',
            ),
        ),
    ]
