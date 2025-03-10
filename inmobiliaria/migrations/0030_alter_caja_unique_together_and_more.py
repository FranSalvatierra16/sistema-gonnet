# Generated by Django 4.2.7 on 2025-03-05 12:33

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0029_alter_caja_unique_together'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='caja',
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name='movimientocaja',
            name='estado',
        ),
        migrations.RemoveField(
            model_name='movimientocaja',
            name='referencia',
        ),
        migrations.RemoveField(
            model_name='caja',
            name='empleado_apertura',
        ),
        migrations.RemoveField(
            model_name='caja',
            name='empleado_cierre',
        ),
        migrations.RemoveField(
            model_name='caja',
            name='estado',
        ),
        migrations.RemoveField(
            model_name='caja',
            name='fecha_apertura',
        ),
        migrations.RemoveField(
            model_name='caja',
            name='fecha_cierre',
        ),
        migrations.RemoveField(
            model_name='caja',
            name='observaciones',
        ),
        migrations.RemoveField(
            model_name='caja',
            name='saldo_final',
        ),
        migrations.RemoveField(
            model_name='caja',
            name='saldo_inicial',
        ),
    ]
