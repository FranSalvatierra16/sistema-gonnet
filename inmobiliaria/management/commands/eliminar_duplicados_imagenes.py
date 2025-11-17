"""
Django management command para eliminar imágenes duplicadas
"""
from django.core.management.base import BaseCommand
from inmobiliaria.models.propiedad import ImagenPropiedad
from django.db.models import Count


class Command(BaseCommand):
    help = 'Elimina imágenes duplicadas de las propiedades'

    def handle(self, *args, **options):
        self.stdout.write("🧹 ELIMINANDO IMÁGENES DUPLICADAS")
        self.stdout.write("=" * 60)
        
        # Encontrar duplicados: imágenes que aparecen múltiples veces en la misma propiedad
        duplicados_por_propiedad = {}
        total_duplicados = 0
        
        # Agrupar por propiedad e imagen
        todas_imagenes = ImagenPropiedad.objects.all().order_by('propiedad', 'imagen', 'id')
        
        propiedad_actual = None
        imagen_actual = None
        ids_duplicados = []
        
        for img in todas_imagenes:
            if propiedad_actual != img.propiedad.id or imagen_actual != img.imagen:
                # Nueva propiedad o imagen, procesar duplicados anteriores
                if len(ids_duplicados) > 1:
                    # Mantener el primero, eliminar los demás
                    id_a_mantener = ids_duplicados[0]
                    ids_a_eliminar = ids_duplicados[1:]
                    
                    if propiedad_actual not in duplicados_por_propiedad:
                        duplicados_por_propiedad[propiedad_actual] = []
                    
                    duplicados_por_propiedad[propiedad_actual].extend(ids_a_eliminar)
                    total_duplicados += len(ids_a_eliminar)
                
                # Resetear para la nueva propiedad/imagen
                propiedad_actual = img.propiedad.id
                imagen_actual = img.imagen
                ids_duplicados = [img.id]
            else:
                # Misma propiedad e imagen, agregar a duplicados
                ids_duplicados.append(img.id)
        
        # Procesar el último grupo
        if len(ids_duplicados) > 1:
            ids_a_eliminar = ids_duplicados[1:]
            if propiedad_actual not in duplicados_por_propiedad:
                duplicados_por_propiedad[propiedad_actual] = []
            duplicados_por_propiedad[propiedad_actual].extend(ids_a_eliminar)
            total_duplicados += len(ids_a_eliminar)
        
        if total_duplicados == 0:
            self.stdout.write(self.style.SUCCESS("✅ No se encontraron duplicados"))
            return
        
        self.stdout.write(f"📊 Duplicados encontrados: {total_duplicados}")
        self.stdout.write(f"📦 Propiedades afectadas: {len(duplicados_por_propiedad)}")
        self.stdout.write("=" * 60)
        
        # Eliminar duplicados
        eliminados = 0
        for prop_id, ids_eliminar in duplicados_por_propiedad.items():
            ImagenPropiedad.objects.filter(id__in=ids_eliminar).delete()
            eliminados += len(ids_eliminar)
        
        self.stdout.write(f"✅ Eliminados {eliminados} duplicados")
        
        # Reordenar imágenes restantes
        self.stdout.write("\n🔄 Reordenando imágenes...")
        from inmobiliaria.models.propiedad import Propiedad
        
        propiedades_con_imagenes = Propiedad.objects.annotate(
            num_imagenes=Count('imagenes')
        ).filter(num_imagenes__gt=0)
        
        reordenadas = 0
        for propiedad in propiedades_con_imagenes:
            imagenes = propiedad.imagenes.all().order_by('id')
            for idx, img in enumerate(imagenes, start=1):
                if img.orden != idx:
                    img.orden = idx
                    img.save(update_fields=['orden'])
                    reordenadas += 1
        
        if reordenadas > 0:
            self.stdout.write(f"✅ Reordenadas {reordenadas} imágenes")
        
        # Estadísticas finales
        total_imagenes = ImagenPropiedad.objects.count()
        propiedades_con_imagenes_final = Propiedad.objects.annotate(
            num_imagenes=Count('imagenes')
        ).filter(num_imagenes__gt=0).count()
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("📊 ESTADÍSTICAS FINALES")
        self.stdout.write("=" * 60)
        self.stdout.write(f"   🖼️  Total imágenes en BD: {total_imagenes}")
        self.stdout.write(f"   🏠 Propiedades con imágenes: {propiedades_con_imagenes_final}")
        
        self.stdout.write(self.style.SUCCESS("\n✅ Proceso completado!"))

