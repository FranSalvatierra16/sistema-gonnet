from django.db import migrations

ROL_COMISION_OP_24 = 'operacion_24_meses'
ROL_COMISION_OP_INVIERNO = 'operacion_invierno'
ROL_COMISION_GENERAL = 'general'


def _categoria_contrato_historico(contrato):
    dm = int(getattr(contrato, 'duracion_meses', 0) or 0)
    if dm == 9:
        return 'invierno'
    if dm >= 9:
        return '24'
    return 'otro'


def confirmar_comisiones_contrato_pendientes(apps, schema_editor):
    ComisionVendedor = apps.get_model('inmobiliaria', 'ComisionVendedor')
    ContratoAlquiler = apps.get_model('inmobiliaria', 'ContratoAlquiler')

    qs = ComisionVendedor.objects.filter(
        contrato_id__isnull=False,
        estado='pendiente',
    )

    for c in qs.iterator():
        updates = {'estado': 'confirmada'}
        rol = (c.rol_comision or ROL_COMISION_GENERAL).strip()
        if rol in (ROL_COMISION_GENERAL, '', 'general'):
            try:
                contrato = ContratoAlquiler.objects.get(pk=c.contrato_id)
                cat = _categoria_contrato_historico(contrato)
                if cat == 'invierno':
                    updates['rol_comision'] = ROL_COMISION_OP_INVIERNO
                elif cat == '24':
                    updates['rol_comision'] = ROL_COMISION_OP_24
            except Exception:
                pass
        ComisionVendedor.objects.filter(pk=c.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0144_propiedad_oficina_comisiones'),
    ]

    operations = [
        migrations.RunPython(
            confirmar_comisiones_contrato_pendientes,
            migrations.RunPython.noop,
        ),
    ]
