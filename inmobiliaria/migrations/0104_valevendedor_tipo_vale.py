from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0103_comisionvendedor_rol_comision'),
    ]

    operations = [
        migrations.AddField(
            model_name='valevendedor',
            name='tipo_vale',
            field=models.CharField(
                choices=[('EG', 'Egreso (entrega al productor)'), ('IN', 'Ingreso (devolución del productor)')],
                default='EG',
                max_length=2,
                verbose_name='Tipo de vale',
            ),
        ),
    ]
