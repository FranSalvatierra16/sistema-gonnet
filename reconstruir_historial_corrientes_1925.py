#!/usr/bin/env python
"""
Script para reconstruir el historial de la propiedad Corrientes 1925
"""
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')
django.setup()

from inmobiliaria.models import Propiedad, HistorialDisponibilidad, Reserva

print("🔍 Buscando propiedad Corrientes 1925...")
print("=" * 60)

# Buscar la propiedad por dirección
propiedades = Propiedad.objects.filter(
    direccion__icontains='corrientes'
).filter(
    direccion__icontains='1925'
)

if not propiedades.exists():
    # Intentar buscar solo por "corrientes" y mostrar todas
    print("⚠️  No se encontró exactamente 'Corrientes 1925'")
    print("\n🔍 Buscando todas las propiedades en Corrientes...")
    propiedades_corrientes = Propiedad.objects.filter(direccion__icontains='corrientes')
    print(f"\n📋 Propiedades encontradas en Corrientes ({propiedades_corrientes.count()}):")
    for p in propiedades_corrientes[:10]:
        print(f"   - ID: {p.id} | Dirección: {p.direccion}")
    if propiedades_corrientes.count() > 10:
        print(f"   ... y {propiedades_corrientes.count() - 10} más")
    exit(1)

propiedad = propiedades.first()
print(f"✅ Propiedad encontrada:")
print(f"   - ID: {propiedad.id}")
print(f"   - Dirección: {propiedad.direccion}")
print(f"   - Ubicación: {propiedad.ubicacion}")
print("=" * 60)

# Verificar estado actual
historial_actual = HistorialDisponibilidad.objects.filter(propiedad=propiedad).count()
disponibilidades = propiedad.disponibilidades.filter(es_manual=True).count()
reservas_activas = propiedad.reservas.filter(eliminada=False).count()

print(f"\n📊 Estado actual:")
print(f"   - Historial actual: {historial_actual} registros")
print(f"   - Disponibilidades manuales: {disponibilidades}")
print(f"   - Reservas activas: {reservas_activas}")

# Reconstruir historial
print(f"\n🔄 Reconstruyendo historial...")
print("=" * 60)

# Buscar una reserva activa para usar su método de reconstrucción
reservas_activas_queryset = propiedad.reservas.filter(eliminada=False)
if reservas_activas_queryset.exists():
    primera_reserva = reservas_activas_queryset.first()
    print(f"📋 Usando método de reconstrucción desde reserva #{primera_reserva.id}")
    primera_reserva.reconstruir_historial_cronologico()
else:
    # Si no hay reservas, crear historial básico con disponibilidades
    print("📋 No hay reservas activas, creando historial básico desde disponibilidades...")
    HistorialDisponibilidad.objects.filter(propiedad=propiedad).delete()
    for disp in propiedad.disponibilidades.filter(es_manual=True).order_by('fecha_inicio'):
        HistorialDisponibilidad.objects.create(
            propiedad=propiedad,
            fecha_inicio=disp.fecha_inicio,
            fecha_fin=disp.fecha_fin,
            estado='libre'
        )
        print(f"   ✅ Período libre: {disp.fecha_inicio} al {disp.fecha_fin}")

# Verificar resultado
historial_nuevo = HistorialDisponibilidad.objects.filter(propiedad=propiedad).count()
print("\n" + "=" * 60)
print(f"✅ Historial reconstruido exitosamente!")
print(f"   - Registros creados: {historial_nuevo}")
print("=" * 60)

# Mostrar resumen del historial
print("\n📋 Resumen del historial:")
historiales = HistorialDisponibilidad.objects.filter(propiedad=propiedad).order_by('fecha_inicio')[:10]
for h in historiales:
    reserva_info = f" (Reserva #{h.reserva.id})" if h.reserva else ""
    print(f"   - {h.fecha_inicio} al {h.fecha_fin} - {h.estado}{reserva_info}")
if historial_nuevo > 10:
    print(f"   ... y {historial_nuevo - 10} más")

print("\n✅ ¡Listo! El historial ha sido reconstruido.")

