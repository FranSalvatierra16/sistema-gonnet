from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0221_quitar_disponibilidades_forzadas'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendedor',
            name='comision_marconi',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text=(
                    'Porcentaje del productor en operaciones cuyo inquilino es Marconi (ID 160). '
                    'Si está vacío, se usa la comisión por día.'
                ),
                max_digits=5,
                null=True,
                verbose_name='Comisión Marconi (%)',
            ),
        ),
    ]
