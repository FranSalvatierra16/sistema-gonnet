from django.db import migrations


def sincronizar_lote_desde_15_dic_2026(apps, schema_editor):
    from inmobiliaria.disponibilidad_masiva_utils import recuperar_ultima_masiva_corrientes

    recuperar_ultima_masiva_corrientes(
        apps=apps,
        nombre='Verano 2027',
        min_deptos=5,
        actualizar_si_existe=True,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0192_recuperar_lote_verano_2027_corrientes'),
    ]

    operations = [
        migrations.RunPython(sincronizar_lote_desde_15_dic_2026, noop),
    ]
