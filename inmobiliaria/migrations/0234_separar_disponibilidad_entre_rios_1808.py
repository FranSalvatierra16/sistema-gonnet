"""
Entre Ríos 1808 (ficha 200099): se habían cargado dos disponibilidades
(1/1–31/1 asegurado y 1/2–1/3) y el sistema las fusionó perdiendo el asegurado.
Las vuelve a separar.
"""
from datetime import date

from django.db import migrations


PROPIEDAD_ID = '200099'
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

    # Borrar el bloque fusionado que cubre ese verano (o trozos dentro del rango).
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
        moneda_asegurado='ARS',
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

    # Historial libre alineado (sin reservas en el medio se unifica visualmente;
    # igual dejamos dos tramos para que coincida con las disponibilidades).
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
    Propiedad = apps.get_model('inmobiliaria', 'Propiedad')
    Disponibilidad = apps.get_model('inmobiliaria', 'Disponibilidad')

    prop = Propiedad.objects.filter(pk=PROPIEDAD_ID).first()
    if not prop:
        return

    Disponibilidad.objects.filter(
        propiedad=prop,
        fecha_inicio__lte=FIN_REST,
        fecha_fin__gte=INICIO_ASEG,
    ).delete()
    Disponibilidad.objects.create(
        propiedad=prop,
        fecha_inicio=date(2027, 1, 2),
        fecha_fin=FIN_REST,
        es_manual=True,
        asegurado=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0233_reserva_2157_moneda_a_pesos'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
