# Soft delete: propiedades no se borran de la DB, se marcan como eliminadas y se pueden recuperar

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0078_movimientocaja_concepto_detalle'),
    ]

    operations = [
        migrations.AddField(
            model_name='propiedad',
            name='eliminada',
            field=models.BooleanField(default=False, help_text='Si está marcada, la propiedad no se muestra en listados pero se puede recuperar.', verbose_name='Eliminada'),
        ),
        migrations.AddField(
            model_name='propiedad',
            name='fecha_eliminacion',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Fecha de eliminación'),
        ),
    ]
