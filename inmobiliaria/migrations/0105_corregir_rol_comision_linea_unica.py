from django.db import migrations

# Constantes alineadas con inmobiliaria.models.comision (sin importar el módulo en migración)
ROL_GENERAL = 'general'
ROL_FICHAJE = 'fichaje'
ROL_OP_24 = 'operacion_24_meses'
ROL_OP_INV = 'operacion_invierno'


def _rol_desde_vendedor_reserva(vendedor, reserva, prop):
    """Misma prioridad que Vendedor.porcentaje_comision_para_reserva / rol_comision_al_crear_linea_unica."""
    if not reserva or not prop:
        return ROL_GENERAL
    try:
        dias = (reserva.fecha_fin - reserva.fecha_inicio).days
    except (TypeError, AttributeError):
        dias = 0
    if dias >= 600 and vendedor.comision_alquiler_24_meses is not None:
        return ROL_OP_24
    if (
        vendedor.comision_invierno is not None
        and dias < 600
        and dias >= 14
        and getattr(prop, 'habilitar_invierno', False)
    ):
        try:
            mes_ini = reserva.fecha_inicio.month
        except AttributeError:
            mes_ini = 0
        if mes_ini in (4, 5, 6, 7, 8, 9, 10):
            return ROL_OP_INV
    tipo = getattr(prop, 'tipo_fichaje', None) or 'primer'
    if tipo == 'segundo' and vendedor.comision_segundo_fichaje is not None:
        return ROL_FICHAJE
    if tipo == 'primer' and vendedor.comision_primer_fichaje is not None:
        return ROL_FICHAJE
    return ROL_GENERAL


def forwards(apps, schema_editor):
    ComisionVendedor = apps.get_model('inmobiliaria', 'ComisionVendedor')
    qs = (
        ComisionVendedor.objects.filter(rol_comision=ROL_GENERAL)
        .select_related('vendedor', 'reserva__propiedad')
        .iterator(chunk_size=500)
    )
    for c in qs:
        res = c.reserva
        if not res:
            continue
        prop = getattr(res, 'propiedad', None)
        if not prop:
            continue
        new_rol = _rol_desde_vendedor_reserva(c.vendedor, res, prop)
        if new_rol == ROL_GENERAL:
            continue
        clash = ComisionVendedor.objects.filter(
            vendedor_id=c.vendedor_id,
            reserva_id=c.reserva_id,
            movimiento_caja_id=c.movimiento_caja_id,
            rol_comision=new_rol,
        ).exclude(pk=c.pk).exists()
        if clash:
            continue
        ComisionVendedor.objects.filter(pk=c.pk).update(rol_comision=new_rol)


def backwards(apps, schema_editor):
    # No revertimos: no hay forma segura de distinguir qué «general» era antes.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0104_valevendedor_tipo_vale'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
