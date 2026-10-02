from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0208_reporte_deptos_oculto_desde'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='cuadrohonorarioscolumna',
            name='uniq_cuadro_honorarios_sucursal_vendedor',
        ),
        migrations.AddField(
            model_name='cuadrohonorarioscolumna',
            name='vigente_desde',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='cuadrohonorarioscolumna',
            name='oculto_desde',
            field=models.DateField(blank=True, null=True),
        ),
    ]
