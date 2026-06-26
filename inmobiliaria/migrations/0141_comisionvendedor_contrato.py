from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0140_gastopropietario_concepto_caja'),
    ]

    operations = [
        migrations.AlterField(
            model_name='comisionvendedor',
            name='reserva',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='comisiones_vendedor',
                to='inmobiliaria.reserva',
                verbose_name='Reserva',
            ),
        ),
        migrations.AddField(
            model_name='comisionvendedor',
            name='contrato',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='comisiones_vendedor',
                to='inmobiliaria.contratoalquiler',
                verbose_name='Contrato',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='comisionvendedor',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='comisionvendedor',
            constraint=models.UniqueConstraint(
                condition=models.Q(('reserva__isnull', False)),
                fields=('vendedor', 'reserva', 'movimiento_caja', 'rol_comision'),
                name='uniq_comision_vendedor_reserva_mov_rol',
            ),
        ),
        migrations.AddConstraint(
            model_name='comisionvendedor',
            constraint=models.UniqueConstraint(
                condition=models.Q(('contrato__isnull', False)),
                fields=('vendedor', 'contrato', 'rol_comision'),
                name='uniq_comision_vendedor_contrato_rol',
            ),
        ),
    ]
