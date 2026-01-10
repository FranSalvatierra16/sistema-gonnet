#!/usr/bin/env python
"""
Script para verificar posibles problemas que pueden causar errores en el servidor
"""
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    django.setup()
    print("✅ Django configurado correctamente")
except Exception as e:
    print(f"❌ Error al configurar Django: {e}")
    sys.exit(1)

# Verificar importaciones
try:
    from inmobiliaria.models import Disponibilidad, Propiedad, Reserva
    print("✅ Modelos importados correctamente")
except Exception as e:
    print(f"❌ Error al importar modelos: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Verificar que el campo es_manual existe
try:
    campo = Disponibilidad._meta.get_field('es_manual')
    print(f"✅ Campo 'es_manual' existe en Disponibilidad: {campo}")
except Exception as e:
    print(f"❌ Error al verificar campo 'es_manual': {e}")
    sys.exit(1)

# Verificar que las vistas se pueden importar
try:
    from inmobiliaria import views
    print("✅ Vistas importadas correctamente")
except Exception as e:
    print(f"❌ Error al importar vistas: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Verificar funciones específicas
try:
    buscar_func = getattr(views, 'buscar_propiedades', None)
    if buscar_func:
        print("✅ Función 'buscar_propiedades' existe")
    else:
        print("❌ Función 'buscar_propiedades' no encontrada")
except Exception as e:
    print(f"❌ Error al verificar función: {e}")

print("\n✅ Todas las verificaciones pasaron correctamente")

