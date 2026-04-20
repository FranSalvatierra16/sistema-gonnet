# Generated manually: cierre de cajas abiertas y nueva caja con saldo 0 en Colón y Corrientes.

from django.contrib.auth import get_user_model
from django.db import migrations


def _usuario_apertura(apps, schema_editor):
    User = get_user_model()
    return (
        User.objects.filter(is_superuser=True).order_by('id').first()
        or User.objects.filter(is_staff=True).order_by('id').first()
        or User.objects.order_by('id').first()
    )


def reset_cajas_colon_corrientes(apps, schema_editor):
    from inmobiliaria.caja_reset import reset_caja_sucursal_desde_cero
    from inmobiliaria.models import Sucursal

    usuario = _usuario_apertura(apps, schema_editor)
    if not usuario:
        return

    def _resolver(*aliases):
        for a in aliases:
            s = Sucursal.objects.filter(nombre__iexact=a).first()
            if s:
                return s
        for a in aliases:
            s = Sucursal.objects.filter(nombre__icontains=a).first()
            if s:
                return s
        return None

    vistos = set()
    for aliases in (('Colon', 'Colón'), ('Corrientes',)):
        suc = _resolver(*aliases)
        if not suc or suc.pk in vistos:
            continue
        vistos.add(suc.pk)
        reset_caja_sucursal_desde_cero(
            suc,
            usuario,
            observacion_cierre_extra='[Migración 0098] Reinicio caja a cero — inicio uso Colón/Corrientes',
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0097_contratoalquiler_precios_bloques'),
    ]

    operations = [
        migrations.RunPython(reset_cajas_colon_corrientes, noop_reverse),
    ]
