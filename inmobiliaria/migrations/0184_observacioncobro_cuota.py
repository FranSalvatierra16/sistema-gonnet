import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0183_observacion_cobro_inquilino'),
    ]

    operations = [
        migrations.AddField(
            model_name='observacioncobroinquilino',
            name='cuota',
            field=models.ForeignKey(
                blank=True,
                help_text='Mes/cuota al que corresponde este gasto a cobrar.',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='observaciones_cobro',
                to='inmobiliaria.cuotamensual',
            ),
        ),
    ]
