from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0089_sucursal_porcentaje_comision_default'),
    ]

    operations = [
        migrations.AlterField(
            model_name='liquidacionpropietario',
            name='estado',
            field=models.CharField(
                choices=[
                    ('pendiente', 'Pendiente'),
                    ('cerrada', 'Cerrada'),
                    ('pagada', 'Pagada'),
                    ('oficina', 'Oficina'),
                    ('procesada', 'Procesada (legacy)'),
                    ('cancelada', 'Cancelada'),
                ],
                default='pendiente',
                max_length=20,
                verbose_name='Estado',
            ),
        ),
    ]
