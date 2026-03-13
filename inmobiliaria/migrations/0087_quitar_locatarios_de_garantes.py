# Quitar locatarios que fueron agregados incorrectamente como garantes (migración 0087 anterior)
# Solo removemos al locatario del M2M garantes; no borramos garantes legítimos.

from django.db import migrations


def quitar_locatarios_de_garantes(apps, schema_editor):
    ContratoAlquiler = apps.get_model('inmobiliaria', 'ContratoAlquiler')
    ContratoInquilino = apps.get_model('inmobiliaria', 'ContratoInquilino')

    for contrato in ContratoAlquiler.objects.prefetch_related('garantes', 'contrato_inquilinos'):
        # Obtener locatario principal
        locatario = None
        through = contrato.contrato_inquilinos.order_by('id').first()
        if through:
            locatario = through.inquilino
        if not locatario and contrato.inquilino_id:
            locatario = contrato.inquilino

        if locatario and contrato.garantes.filter(id=locatario.id).exists():
            contrato.garantes.remove(locatario)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0086_contratoalquiler_precio_segundo_cuatrimestre'),
    ]

    operations = [
        migrations.RunPython(quitar_locatarios_de_garantes, noop),
    ]
