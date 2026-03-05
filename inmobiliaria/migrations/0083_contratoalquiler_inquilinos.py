# Varios inquilinos por contrato (M2M), como garantes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0082_add_garantes_m2m_and_carrera'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='inquilinos',
            field=models.ManyToManyField(
                blank=True,
                help_text='Todos los inquilinos del contrato',
                related_name='contratos_como_inquilino',
                to='inmobiliaria.inquilino',
                verbose_name='Inquilinos',
            ),
        ),
    ]
