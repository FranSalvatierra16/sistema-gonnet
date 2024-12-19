from django.db import migrations

def crear_conceptos_pago(apps, schema_editor):
    ConceptoPago = apps.get_model('inmobiliaria', 'ConceptoPago')
    
    conceptos = [
        ('96', 'A cta. locación y/o honorarios'),
        ('103', 'Total locación y/o honorarios'),
        ('94', 'Depósito de garantía'),
        ('95', 'Saldo locación'),
        ('97', 'Gastos bancarios'),
        ('4', 'Expensas'),
        ('5', 'Edea'),
        ('7', 'Camuzzi'),
        ('1', 'Osse'),
        ('10', 'Ingresos varios'),
        ('13', 'Gastos varios'),
        ('102', 'Refuerzo de seña'),
    ]
    
    for codigo, nombre in conceptos:
        ConceptoPago.objects.get_or_create(
            codigo=codigo,
            defaults={'nombre': nombre}
        )

def eliminar_conceptos_pago(apps, schema_editor):
    ConceptoPago = apps.get_model('inmobiliaria', 'ConceptoPago')
    ConceptoPago.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('inmobiliaria', '0017_historialdisponibilidad'),  # Reemplaza con la migración anterior
    ]

    operations = [
        migrations.RunPython(crear_conceptos_pago, eliminar_conceptos_pago),
    ]
