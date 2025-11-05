#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')
django.setup()

from inmobiliaria.models import Propiedad, Precio

# Nuevos tipos de precio a agregar
nuevos_tipos = ['SEMANA_SANTA', 'CARNAVALES']

propiedades = Propiedad.objects.all()
total_propiedades = propiedades.count()
print(f"📊 Encontradas {total_propiedades} propiedades")

contador_creados = 0
for propiedad in propiedades:
    for tipo in nuevos_tipos:
        precio, created = Precio.objects.get_or_create(
            propiedad=propiedad,
            tipo_precio=tipo,
            defaults={
                'precio_toma': 0,
                'precio_dia_toma': 0,
                'precio_por_dia': 0,
                'precio_total': None,  # None para tipos sin quincena
                'ajuste_porcentaje': 0
            }
        )
        if created:
            contador_creados += 1
            print(f"✅ Creado {tipo} para propiedad {propiedad.id}")

print(f"\n�� Proceso completado: {contador_creados} precios creados")
