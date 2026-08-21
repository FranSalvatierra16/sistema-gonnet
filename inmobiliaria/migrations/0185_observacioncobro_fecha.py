from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0184_observacioncobro_cuota'),
    ]

    operations = [
        migrations.AddField(
            model_name='observacioncobroinquilino',
            name='fecha',
            field=models.DateField(
                default=django.utils.timezone.localdate,
                help_text='Fecha del gasto/observación (por defecto el día en que se carga).',
                verbose_name='Fecha',
            ),
        ),
    ]
