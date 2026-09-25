from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0207_observacioncobro_monto_cobrado'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportedeptosoficinapreferencia',
            name='oculto_desde',
            field=models.DateField(
                blank=True,
                help_text='Mes desde el cual el depto queda fuera del resumen (meses anteriores siguen).',
                null=True,
            ),
        ),
    ]
