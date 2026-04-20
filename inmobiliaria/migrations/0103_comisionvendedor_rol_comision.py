from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0102_vendedor_comision_invierno'),
    ]

    operations = [
        migrations.AddField(
            model_name='comisionvendedor',
            name='rol_comision',
            field=models.CharField(
                default='general',
                help_text='Discrimina varias líneas de comisión por el mismo movimiento (fichaje, operación día/invierno/24 meses, etc.)',
                max_length=32,
                verbose_name='Rol de comisión',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='comisionvendedor',
            unique_together={('vendedor', 'reserva', 'movimiento_caja', 'rol_comision')},
        ),
    ]
