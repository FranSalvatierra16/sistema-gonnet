"""
Django management command para diagnosticar imágenes de propiedades específicas
"""
import os
import boto3
from django.core.management.base import BaseCommand
from inmobiliaria.models.propiedad import Propiedad


class Command(BaseCommand):
    help = 'Diagnostica qué imágenes hay en S3 para propiedades específicas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--propiedad-id',
            type=int,
            help='ID de una propiedad específica para diagnosticar',
        )
        parser.add_argument(
            '--limite',
            type=int,
            default=5,
            help='Número de propiedades a diagnosticar (default: 5)',
        )

    def handle(self, *args, **options):
        self.stdout.write("🔍 DIAGNÓSTICO DE IMÁGENES EN S3")
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
        
        # Obtener propiedades a diagnosticar
        if options['propiedad_id']:
            propiedades = Propiedad.objects.filter(id=options['propiedad_id'])
        else:
            # Tomar las primeras propiedades sin imágenes
            from django.db.models import Count
            propiedades = Propiedad.objects.annotate(
                num_imagenes=Count('imagenes')
            ).filter(num_imagenes=0).order_by('id')[:options['limite']]
        
        if not propiedades.exists():
            self.stdout.write("❌ No se encontraron propiedades para diagnosticar")
            return
        
        for propiedad in propiedades:
            self.stdout.write("\n" + "=" * 60)
            self.stdout.write(f"🏠 Propiedad ID: {propiedad.id}")
            self.stdout.write(f"   Dirección: {propiedad.direccion}")
            self.stdout.write(f"   Ficha: {propiedad.numero_por_propietario}")
            self.stdout.write("=" * 60)
            
            prop_id_str = str(propiedad.id)
            ficha = str(propiedad.numero_por_propietario) if propiedad.numero_por_propietario else None
            
            # Buscar con diferentes patrones
            patrones_a_probar = [
                f'media/propiedades/{prop_id_str}',  # Búsqueda amplia por ID
            ]
            
            if ficha and ficha != prop_id_str:
                patrones_a_probar.append(f'media/propiedades/{ficha}')  # Búsqueda amplia por ficha
            
            todas_imagenes = []
            
            for patron in patrones_a_probar:
                try:
                    self.stdout.write(f"\n🔍 Buscando con patrón: {patron}")
                    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=patron, MaxKeys=100)
                    
                    if 'Contents' in response:
                        imagenes_encontradas = []
                        for obj in response['Contents']:
                            key = obj['Key']
                            nombre_archivo = os.path.basename(key)
                            
                            if key.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                                imagenes_encontradas.append({
                                    'key': key,
                                    'name': nombre_archivo,
                                    'size': obj['Size']
                                })
                        
                        self.stdout.write(f"   ✅ Encontradas {len(imagenes_encontradas)} imágenes")
                        
                        # Mostrar primeras 10
                        for img in imagenes_encontradas[:10]:
                            self.stdout.write(f"      - {img['name']} ({img['size']} bytes)")
                        
                        if len(imagenes_encontradas) > 10:
                            self.stdout.write(f"      ... y {len(imagenes_encontradas) - 10} más")
                        
                        todas_imagenes.extend(imagenes_encontradas)
                    else:
                        self.stdout.write(f"   ❌ No se encontraron imágenes con este patrón")
                        
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"   ⚠️  Error: {e}"))
            
            # Resumen
            if todas_imagenes:
                # Eliminar duplicados
                imagenes_unicas = {}
                for img in todas_imagenes:
                    if img['key'] not in imagenes_unicas:
                        imagenes_unicas[img['key']] = img
                
                self.stdout.write(f"\n📊 RESUMEN:")
                self.stdout.write(f"   Total imágenes encontradas: {len(imagenes_unicas)}")
                
                # Analizar patrones de nombres
                patrones_nombres = {}
                for img in imagenes_unicas.values():
                    nombre = img['name']
                    # Detectar patrón
                    if nombre.startswith(prop_id_str):
                        patron = f"Empieza con ID ({prop_id_str})"
                    elif ficha and nombre.startswith(ficha):
                        patron = f"Empieza con ficha ({ficha})"
                    else:
                        patron = "Otro patrón"
                    
                    if patron not in patrones_nombres:
                        patrones_nombres[patron] = []
                    patrones_nombres[patron].append(nombre)
                
                self.stdout.write(f"\n📋 Patrones de nombres detectados:")
                for patron, nombres in patrones_nombres.items():
                    self.stdout.write(f"   {patron}: {len(nombres)} imágenes")
                    if len(nombres) <= 5:
                        for nombre in nombres:
                            self.stdout.write(f"      - {nombre}")
                    else:
                        for nombre in nombres[:3]:
                            self.stdout.write(f"      - {nombre}")
                        self.stdout.write(f"      ... y {len(nombres) - 3} más")
            else:
                self.stdout.write(f"\n❌ No se encontraron imágenes para esta propiedad")
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("✅ Diagnóstico completado!")

