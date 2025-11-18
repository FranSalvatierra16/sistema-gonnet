"""
Django management command para verificar propiedades sin imágenes
"""
import os
import re
import boto3
from django.core.management.base import BaseCommand
from inmobiliaria.models.propiedad import ImagenPropiedad, Propiedad
from django.db.models import Count


class Command(BaseCommand):
    help = 'Verifica qué propiedades no tienen imágenes y por qué'

    def obtener_imagenes_s3_por_propiedad(self, propiedad, s3_client, bucket_name):
        """Busca las imágenes en S3 que realmente pertenecen a una propiedad"""
        prop_id_str = str(propiedad.id)
        ficha = str(propiedad.numero_por_propietario) if propiedad.numero_por_propietario else None
        
        imagenes_encontradas = []
        
        # Verificar si la imagen ya está asociada a otra propiedad
        todas_imagenes_bd = set(
            ImagenPropiedad.objects.exclude(propiedad=propiedad)
            .values_list('imagen', flat=True)
        )
        
        # Buscar imágenes que empiecen exactamente con el ID seguido de números o guión bajo
        # Patrones más específicos para evitar falsos positivos
        patrones_especificos = [
            f'media/propiedades/{prop_id_str}00',  # Ej: 120000.jpg
            f'media/propiedades/{prop_id_str}01',  # Ej: 120001.jpg
            f'media/propiedades/{prop_id_str}02',  # Ej: 120002.jpg
            f'media/propiedades/{prop_id_str}03',  # Ej: 120003.jpg
            f'media/propiedades/{prop_id_str}04',  # Ej: 120004.jpg
            f'media/propiedades/{prop_id_str}05',  # Ej: 120005.jpg
            f'media/propiedades/{prop_id_str}06',  # Ej: 120006.jpg
            f'media/propiedades/{prop_id_str}07',  # Ej: 120007.jpg
            f'media/propiedades/{prop_id_str}08',  # Ej: 120008.jpg
            f'media/propiedades/{prop_id_str}09',  # Ej: 120009.jpg
            f'media/propiedades/{prop_id_str}_',   # Ej: 1200_xxx.jpg
        ]
        
        # Si el ID tiene 4 o más dígitos, también buscar con un solo dígito adicional
        if len(prop_id_str) >= 4:
            patrones_especificos.extend([
                f'media/propiedades/{prop_id_str}0',  # Ej: 12000.jpg, 12001.jpg
                f'media/propiedades/{prop_id_str}1',  # Ej: 120010.jpg, 120011.jpg
            ])
        
        # Buscar por ficha solo si es diferente del ID y tiene al menos 4 caracteres
        # (para evitar falsos positivos con fichas cortas como "1", "2", etc.)
        # Si la ficha es muy corta, solo buscar imágenes con formato específico (ej: "1_xxx.jpg")
        if ficha and ficha != prop_id_str:
            if len(ficha) >= 4:
                # Ficha larga: buscar normalmente
                patrones_ficha = [
                    f'media/propiedades/{ficha}00',
                    f'media/propiedades/{ficha}01',
                    f'media/propiedades/{ficha}_',
                    f'media/propiedades/{ficha}0',
                ]
                patrones_especificos.extend(patrones_ficha)
            elif len(ficha) >= 2:
                # Ficha corta (1-3 caracteres): solo buscar con guión bajo o punto
                # Esto evita encontrar imágenes de otras propiedades (ej: "10002000.jpg" cuando ficha es "1")
                patrones_ficha = [
                    f'media/propiedades/{ficha}_',  # Ej: 1_xxx.jpg
                    f'media/propiedades/{ficha}.',  # Ej: 1.xxx.jpg
                ]
                patrones_especificos.extend(patrones_ficha)
        
        # Obtener todos los IDs de propiedades para validación
        todos_ids_propiedades = set(
            Propiedad.objects.values_list('id', flat=True)
        )
        
        for patron in patrones_especificos:
            try:
                response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=patron)
                if 'Contents' in response:
                    for obj in response['Contents']:
                        key = obj['Key']
                        nombre_archivo = os.path.basename(key)
                        
                        if not key.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                            continue
                        
                        # Verificar que no esté ya asociada a otra propiedad
                        nombre_relativo = key.replace('media/', '')
                        if nombre_relativo in todas_imagenes_bd:
                            continue
                        
                        # Validación estricta: debe empezar exactamente con el ID o ficha
                        es_valida = False
                        
                        # Verificar por ID
                        if nombre_archivo.startswith(prop_id_str):
                            # Si el siguiente carácter es un dígito, debe ser parte del orden (00-99)
                            if len(nombre_archivo) > len(prop_id_str):
                                siguiente = nombre_archivo[len(prop_id_str):]
                                # Debe ser: números seguidos de extensión, o guión bajo
                                # Aceptar: 00.jpeg, 01.jpg, 0.jpg, _xxx.jpg, etc.
                                # La regex busca: dígitos seguidos de punto (extensión) o guión bajo
                                if re.match(r'^\d+\.', siguiente) or re.match(r'^_', siguiente) or re.match(r'^\d{2,}', siguiente):
                                    es_valida = True
                            else:
                                # Nombre exacto como "1200.jpg"
                                es_valida = True
                        
                        # Verificar por ficha si no pasó la validación por ID
                        if not es_valida and ficha and ficha != prop_id_str:
                            if nombre_archivo.startswith(ficha):
                                # Si la ficha es corta (1-3 caracteres), solo aceptar si sigue con guión bajo o punto
                                if len(ficha) < 4:
                                    if len(nombre_archivo) > len(ficha):
                                        siguiente_char = nombre_archivo[len(ficha)]
                                        # Solo aceptar si sigue con guión bajo o punto (no números)
                                        if siguiente_char in ['_', '.']:
                                            es_valida = True
                                    else:
                                        # Nombre exacto como "1.jpg"
                                        es_valida = True
                                else:
                                    # Ficha larga: validación normal
                                    # Verificar que no sea de otra propiedad
                                    match = re.match(r'^(\d+)', nombre_archivo)
                                    if match:
                                        primeros_digitos = match.group(1)
                                        if len(primeros_digitos) >= 4:
                                            es_otra_propiedad = False
                                            for longitud in range(4, min(len(primeros_digitos) + 1, 7)):
                                                posible_id = int(primeros_digitos[:longitud])
                                                if posible_id in todos_ids_propiedades and posible_id != propiedad.id:
                                                    es_otra_propiedad = True
                                                    break
                                            
                                            if es_otra_propiedad:
                                                continue
                                    
                                    if len(nombre_archivo) > len(ficha):
                                        siguiente = nombre_archivo[len(ficha):]
                                        # Aceptar: dígitos seguidos de punto (extensión) o guión bajo
                                        if re.match(r'^\d+\.', siguiente) or re.match(r'^_', siguiente) or re.match(r'^\d{2,}', siguiente):
                                            es_valida = True
                                    else:
                                        es_valida = True
                        
                        if es_valida and key not in [img['key'] for img in imagenes_encontradas]:
                            imagenes_encontradas.append({
                                'key': key,
                                'name': nombre_archivo,
                                'size': obj['Size']
                            })
            except Exception:
                pass
        
        return imagenes_encontradas

    def handle(self, *args, **options):
        self.stdout.write("🔍 VERIFICANDO PROPIEDADES SIN IMÁGENES")
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
        
        # Obtener propiedades sin imágenes
        propiedades_sin_imagenes = Propiedad.objects.annotate(
            num_imagenes=Count('imagenes')
        ).filter(num_imagenes=0).order_by('id')
        
        total_sin_imagenes = propiedades_sin_imagenes.count()
        self.stdout.write(f"📦 Propiedades sin imágenes en BD: {total_sin_imagenes}")
        self.stdout.write("=" * 60)
        
        propiedades_con_imagenes_en_s3 = []
        propiedades_sin_imagenes_en_s3 = []
        
        # Verificar cada propiedad
        for idx, propiedad in enumerate(propiedades_sin_imagenes, 1):
            if idx % 20 == 0:
                self.stdout.write(f"   Verificando... {idx}/{total_sin_imagenes}")
            
            imagenes_s3 = self.obtener_imagenes_s3_por_propiedad(propiedad, s3_client, bucket_name)
            
            if imagenes_s3:
                propiedades_con_imagenes_en_s3.append({
                    'propiedad': propiedad,
                    'imagenes': imagenes_s3
                })
            else:
                propiedades_sin_imagenes_en_s3.append(propiedad)
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("📊 RESULTADOS")
        self.stdout.write("=" * 60)
        self.stdout.write(f"   ✅ Propiedades con imágenes en S3 (pero no en BD): {len(propiedades_con_imagenes_en_s3)}")
        self.stdout.write(f"   ❌ Propiedades sin imágenes en S3: {len(propiedades_sin_imagenes_en_s3)}")
        
        if propiedades_con_imagenes_en_s3:
            self.stdout.write("\n📸 PROPIEDADES CON IMÁGENES EN S3 (pero no en BD):")
            self.stdout.write("=" * 60)
            for item in propiedades_con_imagenes_en_s3[:20]:  # Mostrar primeras 20
                prop = item['propiedad']
                imagenes = item['imagenes']
                self.stdout.write(f"   ID: {prop.id} - {prop.direccion} (Ficha: {prop.numero_por_propietario})")
                self.stdout.write(f"      Imágenes encontradas: {len(imagenes)}")
                for img in imagenes[:3]:  # Mostrar primeras 3
                    self.stdout.write(f"         - {img['name']}")
                if len(imagenes) > 3:
                    self.stdout.write(f"         ... y {len(imagenes) - 3} más")
            
            if len(propiedades_con_imagenes_en_s3) > 20:
                self.stdout.write(f"\n   ... y {len(propiedades_con_imagenes_en_s3) - 20} más")
            
            self.stdout.write("\n💡 Estas propiedades tienen imágenes en S3 pero no están asociadas en la BD.")
            self.stdout.write("   Podés ejecutar: python manage.py recuperar_imagenes para asociarlas.")
        
        if propiedades_sin_imagenes_en_s3:
            self.stdout.write("\n❌ PROPIEDADES SIN IMÁGENES EN S3:")
            self.stdout.write("=" * 60)
            for prop in propiedades_sin_imagenes_en_s3[:20]:  # Mostrar primeras 20
                self.stdout.write(f"   ID: {prop.id} - {prop.direccion} (Ficha: {prop.numero_por_propietario})")
            
            if len(propiedades_sin_imagenes_en_s3) > 20:
                self.stdout.write(f"\n   ... y {len(propiedades_sin_imagenes_en_s3) - 20} más")
            
            self.stdout.write("\n💡 Estas propiedades realmente no tienen imágenes en S3.")
        
        self.stdout.write("\n✅ Verificación completada!")

