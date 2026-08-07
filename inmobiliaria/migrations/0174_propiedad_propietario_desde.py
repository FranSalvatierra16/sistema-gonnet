# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0173_personaoficina_vales'),
    ]

    operations = [
        migrations.AddField(
            model_name='propiedad',
            name='propietario_desde',
            field=models.DateField(
                blank=True,
                help_text=(
                    'Fecha desde la cual el propietario actual es titular. '
                    'En liquidaciones no se listan gastos ni egresos de caja anteriores a esta fecha.'
                ),
                null=True,
                verbose_name='Titular desde',
            ),
        ),
    ]
