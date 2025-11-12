from django.core.management.base import BaseCommand, CommandError
from django.db import connection
import json
import os
import requests

class Command(BaseCommand):
    help = 'Migra datos desde MySQL de Heroku a PostgreSQL de Railway'

    def add_arguments(self, parser):
        parser.add_argument(
            '--archivo',
            help='Ruta local o URL (HTTP/HTTPS) del backup JSON a importar'
        )

    def handle(self, *args, **options):
        self.stdout.write("🔄 MIGRACIÓN MYSQL → POSTGRESQL")
        self.stdout.write("=" * 60)
        
        origen = options.get('archivo') or \
            'https://raw.githubusercontent.com/FranSalvatierra16/sistema-gonnet/finalizacion10/backup_heroku_20251111_213534.json'
        
        self.stdout.write(f"\n📥 Cargando backup desde: {origen}")
        
        all_data = None
        try:
            if origen.startswith('http://') or origen.startswith('https://'):
                response = requests.get(origen, timeout=120)
                response.raise_for_status()
                all_data = response.json()
                self.stdout.write(f"✅ Backup descargado ({len(response.content) / 1024 / 1024:.2f} MB)")
            else:
                ruta = os.path.abspath(origen)
                if not os.path.exists(ruta):
                    raise CommandError(f"El archivo '{ruta}' no existe")
                with open(ruta, 'r', encoding='utf-8') as f:
                    all_data = json.load(f)
                size_mb = os.path.getsize(ruta) / 1024 / 1024
                self.stdout.write(f"✅ Backup leído localmente ({size_mb:.2f} MB)")
        except Exception as e:
            raise CommandError(f"No se pudo cargar el backup: {e}")
        
        # Migrar datos
        results = {}
        total_migrated = 0
        
        for table_name, rows in all_data.items():
            try:
                if not rows:
                    results[table_name] = 0
                    continue
                
                self.stdout.write(f"\n📋 Migrando {table_name}: {len(rows)} registros...")
                
                # Preparar INSERT para PostgreSQL
                columns = list(rows[0].keys())
                placeholders = ', '.join(['%s'] * len(columns))
                columns_str = ', '.join([f'"{col}"' for col in columns])
                
                insert_sql = f'INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
                
                migrated = 0
                with connection.cursor() as postgres_cursor:
                    for row in rows:
                        try:
                            values = [row[col] for col in columns]
                            postgres_cursor.execute(insert_sql, values)
                            migrated += 1
                            
                            if migrated % 100 == 0:
                                self.stdout.write(f"   ✅ {migrated}/{len(rows)}...")
                                connection.commit()
                                
                        except Exception as row_error:
                            pass  # Ignorar errores de FK
                    
                    connection.commit()
                
                results[table_name] = migrated
                total_migrated += migrated
                self.stdout.write(self.style.SUCCESS(f"✅ {table_name}: {migrated} registros"))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error en {table_name}: {str(e)[:100]}"))
                results[table_name] = 0
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("✅ MIGRACIÓN COMPLETADA"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"\n🎯 Total migrado: {total_migrated} registros")

