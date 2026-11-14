"""
Ficha 100870: mismo caso que Entre Ríos 1808 — dos disponibilidades
(1/1–31/1 asegurado y 1/2–1/3) se fusionaron y se perdió el asegurado.
"""
from datetime import date

from django.db import migrations


PROPIEDAD_ID = '100870'
INICIO_ASEG = date(2027, 1, 1)
FIN_ASEG = date(2027, 1, 31)
INICIO_REST = date(2027, 2, 1)
FIN_REST = date(2027, 3, 1)


def forwards(apps, schema_editor):
    Propiedad = apps.get_model('inmobiliaria', 'Propiedad')
    Disponibilidad = apps.get_model('inmobiliaria', 'Disponibilidad')
    HistorialDisponibilidad = apps.get_model('inmobiliaria', 'HistorialDisponibilidad')

    prop = Propiedad.objects.filter(pk=PROPIEDAD_ID).first()
    if not prop:
        return

    # Conservar monto/moneda si el bloque fusionado aún tenía asegurado.
    prev = (
        Disponibilidad.objects.filter(
            propiedad=prop,
            fecha_inicio__lte=FIN_REST,
            fecha_fin__gte=INICIO_ASEG,
        )
        .order_by('-asegurado', '-monto_asegurado')
        .first()
    )
    monto = getattr(prev, 'monto_asegurado', None) if prev else None
    moneda = getattr(prev, 'moneda_asegurado', None) if prev and prev.asegurado else 'ARS'

    Disponibilidad.objects.filter(
        propiedad=prop,
        fecha_inicio__lte=FIN_REST,
        fecha_fin__gte=INICIO_ASEG,
    ).delete()

    Disponibilidad.objects.create(
        propiedad=prop,
        fecha_inicio=INICIO_ASEG,
        fecha_fin=FIN_ASEG,
        es_manual=True,
        asegurado=True,
        monto_asegurado=monto,
        moneda_asegurado=moneda or 'ARS',
    )
    Disponibilidad.objects.create(
        propiedad=prop,
        fecha_inicio=INICIO_REST,
        fecha_fin=FIN_REST,
        es_manual=True,
        asegurado=False,
        monto_asegurado=None,
        moneda_asegurado=None,
    )

    HistorialDisponibilidad.objects.filter(
        propiedad=prop,
        estado='libre',
        fecha_inicio__lte=FIN_REST,
        fecha_fin__gte=INICIO_ASEG,
    ).delete()
    HistorialDisponibilidad.objects.create(
        propiedad=prop,
        fecha_inicio=INICIO_ASEG,
        fecha_fin=FIN_ASEG,
        estado='libre',
        reserva=None,
        es_principal=True,
    )
    HistorialDisponibilidad.objects.create(
        propiedad=prop,
        fecha_inicio=INICIO_REST,
        fecha_fin=FIN_REST,
        estado='libre',
        reserva=None,
        es_principal=True,
    )


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0234_separar_disponibilidad_entre_rios_1808'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
