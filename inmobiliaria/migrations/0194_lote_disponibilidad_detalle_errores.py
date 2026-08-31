# Generated manually — detalle de errores en lotes de disponibilidad masiva

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0193_sincronizar_lote_corrientes_dic_2026'),
    ]

    operations = [
        migrations.AddField(
            model_name='lotedisponibilidadmasiva',
            name='detalle_errores',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Lista de deptos que fallaron al crear (id, dirección, error).',
                verbose_name='Detalle de errores',
            ),
        ),
    ]
