import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0185_observacioncobro_fecha'),
    ]

    operations = [
        migrations.AddField(
            model_name='observacioncobroinquilino',
            name='gasto_propietario',
            field=models.ForeignKey(
                blank=True,
                help_text='Gasto/ingreso pendiente generado al cobrar, para liquidar al propietario.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='observaciones_cobro_origen',
                to='inmobiliaria.gastopropietario',
            ),
        ),
    ]
