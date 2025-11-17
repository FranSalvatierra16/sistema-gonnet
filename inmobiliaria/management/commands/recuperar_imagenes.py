"""
Django management command para recuperar imágenes de todas las propiedades
"""
import os
import re
import boto3
from django.core.management.base import BaseCommand
from inmobiliaria.models.propiedad import ImagenPropiedad, Propiedad
from django.db.models import Count


class Command(BaseCommand):
    help = 'Recupera las imágenes de todas las propiedades desde S3'

    def add_arguments(self, parser):
        parser.add_argument(
            '--propiedad-id',
            type=int,
            help='ID de una propiedad específica para procesar',
        )

    def obtener_imagenes_s3_por_propiedad(self, propiedad, s3_client, bucket_name):
        """Busca las imágenes en S3 que realmente pertenecen a una propiedad"""
        prop_id_str = str(propiedad.id)
        ficha = str(propiedad.numero_por_propietario) if propiedad.numero_por_propietario else None
        
        imagenes_encontradas = []
        
        # Buscar por ID de propiedad
        patrones_id = [
            f'media/propiedades/{prop_id_str}00',  # Ej: 120000.jpg
            f'media/propiedades/{prop_id_str}01',  # Ej: 120001.jpg
            f'media/propiedades/{prop_id_str}0',   # Ej: 12000.jpg, 12001.jpg
            f'media/propiedades/{prop_id_str}_',   # Ej: 1200_xxx.jpg
        ]
        
        # Buscar por ficha si es diferente del ID
        patrones_ficha = []
        if ficha and ficha != prop_id_str:
            patrones_ficha = [
                f'media/propiedades/{ficha}00',
                f'media/propiedades/{ficha}01',
                f'media/propiedades/{ficha}0',
                f'media/propiedades/{ficha}_',
            ]
        
        todos_patrones = patrones_id + patrones_ficha
        
        for patron in todos_patrones:
            try:
                response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=patron)
                if 'Contents' in response:
                    for obj in response['Contents']:
                        key = obj['Key']
                        nombre_archivo = os.path.basename(key)
                        
                        if not key.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                            continue
                        
                        # Verificar que realmente pertenece a esta propiedad
                        if nombre_archivo.startswith(prop_id_str):
                            # Si el ID tiene menos de 4 dígitos, verificar que no sea de otra propiedad
                            if len(prop_id_str) < 4:
                                match = re.match(r'^(\d+)', nombre_archivo)
                                if match:
                                    primeros_digitos = match.group(1)
                                    if not (primeros_digitos == prop_id_str or primeros_digitos.startswith(prop_id_str + '0')):
                                        continue
                            
                            if key not in [img['key'] for img in imagenes_encontradas]:
                                imagenes_encontradas.append({
                                    'key': key,
                                    'name': nombre_archivo,
                                    'size': obj['Size']
                                })
                        
                        # También verificar por ficha
                        if ficha and nombre_archivo.startswith(ficha) and ficha != prop_id_str:
                            if len(ficha) < 4:
                                match = re.match(r'^(\d+)', nombre_archivo)
                                if match:
                                    primeros_digitos = match.group(1)
                                    if not (primeros_digitos == ficha or primeros_digitos.startswith(ficha + '0')):
                                        continue
                            
                            if key not in [img['key'] for img in imagenes_encontradas]:
                                imagenes_encontradas.append({
                                    'key': key,
                                    'name': nombre_archivo,
                                    'size': obj['Size']
                                })
            except Exception:
                pass
        
        return imagenes_encontradas

    def handle(self, *args, **options):
        self.stdout.write("🚀 RECUPERANDO IMÁGENES DE TODAS LAS PROPIEDADES")
        self.stdout.write("=" * 60)
        
        # Configurar S3
        bucket_name = os.environ.get('AWS_STORAGE_BUCKET_NAME', 'gonnet-interno-media17')
        access_key = os.environ.get('AWS_ACCESS_KEY_ID')
        secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
        region = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
        
        if not access_key or not secret_key:
            self.stdout.write(self.style.ERROR('❌ Error: AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY deben estar configurados'))
            return
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        
        # Obtener propiedades
        if options['propiedad_id']:
            propiedades = Propiedad.objects.filter(id=options['propiedad_id'])
        else:
            propiedades = Propiedad.objects.all().order_by('id')
        
        total_propiedades = propiedades.count()
        self.stdout.write(f"📦 Total de propiedades: {total_propiedades}")
        self.stdout.write("=" * 60)
        
        estadisticas = {
            'procesadas': 0,
            'con_imagenes': 0,
            'sin_imagenes': 0,
            'imagenes_creadas': 0,
            'imagenes_ya_existentes': 0,
            'errores': 0
        }
        
        # Procesar cada propiedad
        for idx, propiedad in enumerate(propiedades, 1):
            try:
                if idx % 10 == 0:
                    self.stdout.write(f"\n📊 Progreso: {idx}/{total_propiedades} ({idx*100//total_propiedades}%)")
                    self.stdout.write(f"   ✅ Con imágenes: {estadisticas['con_imagenes']}")
                    self.stdout.write(f"   ⏭️  Sin imágenes: {estadisticas['sin_imagenes']}")
                    self.stdout.write(f"   📸 Imágenes creadas: {estadisticas['imagenes_creadas']}")
                
                # Buscar imágenes en S3
                imagenes_s3 = self.obtener_imagenes_s3_por_propiedad(propiedad, s3_client, bucket_name)
                
                if not imagenes_s3:
                    estadisticas['sin_imagenes'] += 1
                    estadisticas['procesadas'] += 1
                    continue
                
                # Ordenar imágenes por nombre
                imagenes_s3.sort(key=lambda x: x['name'])
                
                # Crear registros para las imágenes encontradas
                creadas_en_esta = 0
                ya_existentes_en_esta = 0
                
                for img_idx, img_info in enumerate(imagenes_s3, start=1):
                    nombre_archivo = img_info['key'].replace('media/propiedades/', '')
                    
                    # Verificar si ya existe
                    existe = ImagenPropiedad.objects.filter(
                        propiedad=propiedad,
                        imagen__icontains=nombre_archivo
                    ).exists()
                    
                    if existe:
                        ya_existentes_en_esta += 1
                        continue
                    
                    # Crear registro
                    try:
                        ImagenPropiedad.objects.create(
                            propiedad=propiedad,
                            imagen=f'propiedades/{nombre_archivo}',
                            orden=img_idx
                        )
                        creadas_en_esta += 1
                    except Exception:
                        pass
                
                if creadas_en_esta > 0 or ya_existentes_en_esta > 0:
                    estadisticas['con_imagenes'] += 1
                    estadisticas['imagenes_creadas'] += creadas_en_esta
                    estadisticas['imagenes_ya_existentes'] += ya_existentes_en_esta
                
                estadisticas['procesadas'] += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"\n❌ Error con propiedad {propiedad.id} ({propiedad.direccion}): {e}"))
                estadisticas['errores'] += 1
                estadisticas['procesadas'] += 1
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("📊 RESUMEN FINAL")
        self.stdout.write("=" * 60)
        self.stdout.write(f"   ✅ Propiedades procesadas: {estadisticas['procesadas']}")
        self.stdout.write(f"   📸 Propiedades con imágenes: {estadisticas['con_imagenes']}")
        self.stdout.write(f"   ⏭️  Propiedades sin imágenes: {estadisticas['sin_imagenes']}")
        self.stdout.write(f"   🖼️  Imágenes creadas: {estadisticas['imagenes_creadas']}")
        self.stdout.write(f"   ⏭️  Imágenes ya existentes: {estadisticas['imagenes_ya_existentes']}")
        self.stdout.write(f"   ❌ Errores: {estadisticas['errores']}")
        
        # Estadísticas finales
        total_imagenes_bd = ImagenPropiedad.objects.count()
        propiedades_con_imagenes = Propiedad.objects.annotate(
            num_imagenes=Count('imagenes')
        ).filter(num_imagenes__gt=0).count()
        
        self.stdout.write(f"\n📊 Estado final de la base de datos:")
        self.stdout.write(f"   🖼️  Total imágenes en BD: {total_imagenes_bd}")
        self.stdout.write(f"   🏠 Propiedades con imágenes: {propiedades_con_imagenes}")
        
        self.stdout.write(self.style.SUCCESS("\n✅ Proceso completado!"))

