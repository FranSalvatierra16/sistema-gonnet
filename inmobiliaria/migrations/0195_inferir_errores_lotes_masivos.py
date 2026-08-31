from django.db import migrations


def inferir_errores_lotes_viejos(apps, schema_editor):
    Lote = apps.get_model('inmobiliaria', 'LoteDisponibilidadMasiva')
    from inmobiliaria.disponibilidad_masiva_utils import inferir_y_guardar_errores_lote

    Disponibilidad = apps.get_model('inmobiliaria', 'Disponibilidad')
    Propiedad = apps.get_model('inmobiliaria', 'Propiedad')

    for lote in Lote.objects.all().iterator():
        if lote.detalle_errores:
            continue
        inferir_y_guardar_errores_lote(lote, Disponibilidad=Disponibilidad, Propiedad=Propiedad)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0194_lote_disponibilidad_detalle_errores'),
    ]

    operations = [
        migrations.RunPython(inferir_errores_lotes_viejos, noop),
    ]
