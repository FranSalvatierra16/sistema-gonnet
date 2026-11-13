"""
Operación 2157: estaba en U$S y debe figurar en pesos en el sistema.
Solo cambia la moneda (ARS); los importes numéricos se mantienen.
"""
from django.db import migrations


RESERVA_ID = 2157


def forwards(apps, schema_editor):
    Reserva = apps.get_model('inmobiliaria', 'Reserva')
    LiquidacionPropietario = apps.get_model('inmobiliaria', 'LiquidacionPropietario')

    updated = Reserva.objects.filter(pk=RESERVA_ID).exclude(moneda='ARS').update(moneda='ARS')
    if updated:
        LiquidacionPropietario.objects.filter(reserva_id=RESERVA_ID).exclude(
            moneda='ARS'
        ).update(moneda='ARS')


def backwards(apps, schema_editor):
    Reserva = apps.get_model('inmobiliaria', 'Reserva')
    LiquidacionPropietario = apps.get_model('inmobiliaria', 'LiquidacionPropietario')

    Reserva.objects.filter(pk=RESERVA_ID).update(moneda='USD')
    LiquidacionPropietario.objects.filter(reserva_id=RESERVA_ID).update(moneda='USD')


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0232_revertir_gestion_cobranza_solo_fotos'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
