# Campo opcional para precio del 2do cuatrimestre en contratos estudiante (9 meses)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0085_fix_alquilermeses_id_sequence'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='precio_segundo_cuatrimestre',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Precio 2do cuatrimestre (contrato estudiante 9 meses)'),
        ),
    ]
