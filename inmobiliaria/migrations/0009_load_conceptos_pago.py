from django.db import migrations

def cargar_conceptos_iniciales(apps, schema_editor):
    ConceptoPago = apps.get_model('inmobiliaria', 'ConceptoPago')
    
    conceptos = [
        {'codigo': '50', 'nombre': 'Locación', 'descripcion': 'Pago por locación de propiedad'},
        {'codigo': '20', 'nombre': 'Saldo', 'descripcion': 'Pago de saldo pendiente'},
        {'codigo': '10', 'nombre': 'Seña', 'descripcion': 'Pago de seña inicial'},
        {'codigo': '30', 'nombre': 'Depósito', 'descripcion': 'Pago de depósito'},
        {'codigo': '40', 'nombre': 'Garantía', 'descripcion': 'Pago de garantía'},
        {'codigo': '60', 'nombre': 'Comisión', 'descripcion': 'Pago de comisión'},
    ]
    
    for concepto in conceptos:
        ConceptoPago.objects.create(**concepto)

def revertir_conceptos(apps, schema_editor):
    ConceptoPago = apps.get_model('inmobiliaria', 'ConceptoPago')
    ConceptoPago.objects.all().delete()

class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0008_vendedor_password_temporal'),  # Reemplazar con la migración anterior
    ]

    operations = [
        migrations.RunPython(cargar_conceptos_iniciales, revertir_conceptos),
    ] 