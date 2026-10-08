from decimal import Decimal

from django.db import migrations
from django.db.models import Q


def invierno_sin_precio_toma_estudiante(apps, schema_editor):
    """Invierno sin precio cargado (vacío o $1 de relleno): tomar el mensual de Estudiante."""
    Precio = apps.get_model('inmobiliaria', 'Precio')
    AlquilerInvierno = apps.get_model('inmobiliaria', 'AlquilerInvierno')
    for p in Precio.objects.filter(tipo_precio='ESTUDIANTE', precio_total__gt=Decimal('1')):
        AlquilerInvierno.objects.filter(propiedad_id=p.propiedad_id).filter(
            Q(precio_mensual__isnull=True) | Q(precio_mensual__lte=Decimal('1'))
        ).update(precio_mensual=p.precio_total)


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0216_liquidacion_flag_y_total_gral_por_mes'),
    ]

    operations = [
        migrations.RunPython(invierno_sin_precio_toma_estudiante, migrations.RunPython.noop),
    ]
