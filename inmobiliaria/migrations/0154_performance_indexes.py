# Índices para listados frecuentes (operaciones, caja, recibos).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0153_marconi_julio_pagado_efectivo'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='reserva',
            index=models.Index(
                fields=['sucursal', 'eliminada', '-id'],
                name='reserva_suc_elim_id_desc',
            ),
        ),
        migrations.AddIndex(
            model_name='movimientocaja',
            index=models.Index(
                fields=['sucursal', 'propiedad', 'tipo'],
                name='mov_suc_prop_tipo_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='movimientocaja',
            index=models.Index(
                fields=['caja', '-fecha'],
                name='mov_caja_fecha_desc_idx',
            ),
        ),
    ]
