"""
Comando de Django para mostrar la estructura completa de la base de datos
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django.apps import apps
from django.db import models


class Command(BaseCommand):
    help = 'Muestra la estructura completa de todas las tablas de la base de datos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--app',
            type=str,
            help='Mostrar solo las tablas de una app específica (ej: inmobiliaria)',
        )
        parser.add_argument(
            '--tabla',
            type=str,
            help='Mostrar solo una tabla específica',
        )
        parser.add_argument(
            '--formato',
            type=str,
            choices=['simple', 'detallado', 'sql'],
            default='detallado',
            help='Formato de salida (simple, detallado, sql)',
        )

    def handle(self, *args, **options):
        app_name = options.get('app')
        tabla_name = options.get('tabla')
        formato = options.get('formato')
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*80))
        self.stdout.write(self.style.SUCCESS('ESTRUCTURA DE LA BASE DE DATOS'))
        self.stdout.write(self.style.SUCCESS('='*80 + '\n'))
        
        # Obtener todas las apps instaladas
        if app_name:
            apps_to_check = [apps.get_app_config(app_name)]
        else:
            apps_to_check = apps.get_app_configs()
        
        # Obtener todas las tablas de la base de datos
        with connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                    ORDER BY table_name;
                """)
            elif connection.vendor == 'mysql':
                cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = DATABASE()
                    AND table_type = 'BASE TABLE'
                    ORDER BY table_name;
                """)
            else:
                # SQLite
                cursor.execute("""
                    SELECT name 
                    FROM sqlite_master 
                    WHERE type='table' 
                    AND name NOT LIKE 'sqlite_%'
                    ORDER BY name;
                """)
            
            db_tables = [row[0] for row in cursor.fetchall()]
        
        # Obtener todos los modelos de Django
        all_models = {}
        for app_config in apps_to_check:
            for model in app_config.get_models():
                table_name = model._meta.db_table
                all_models[table_name] = model
        
        # Filtrar por tabla si se especifica
        if tabla_name:
            db_tables = [t for t in db_tables if tabla_name.lower() in t.lower()]
        
        # Mostrar información
        for table_name in sorted(db_tables):
            # Buscar el modelo correspondiente
            model = all_models.get(table_name)
            
            if formato == 'sql':
                self.mostrar_estructura_sql(cursor, table_name)
            elif formato == 'simple':
                self.mostrar_estructura_simple(cursor, table_name, model)
            else:  # detallado
                self.mostrar_estructura_detallada(cursor, table_name, model)
            
            self.stdout.write('')
        
        self.stdout.write(self.style.SUCCESS('='*80))
        self.stdout.write(self.style.SUCCESS(f'Total de tablas: {len(db_tables)}'))
        self.stdout.write(self.style.SUCCESS('='*80 + '\n'))

    def mostrar_estructura_simple(self, cursor, table_name, model):
        """Muestra una versión simple de la estructura"""
        self.stdout.write(self.style.WARNING(f'\n📋 TABLA: {table_name}'))
        if model:
            self.stdout.write(f'   Modelo Django: {model.__name__}')
        
        # Obtener columnas
        if connection.vendor == 'postgresql':
            cursor.execute("""
                SELECT column_name, data_type, character_maximum_length, 
                       is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position;
            """, [table_name])
        elif connection.vendor == 'mysql':
            cursor.execute("""
                SELECT column_name, data_type, character_maximum_length,
                       is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                AND table_name = %s
                ORDER BY ordinal_position;
            """, [table_name])
        else:
            # SQLite
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            for col in columns:
                col_name = col[1]
                col_type = col[2]
                nullable = 'YES' if not col[3] else 'NO'
                default = col[4]
                self.stdout.write(f'   • {col_name}: {col_type} (NULL: {nullable})')
            return
        
        columns = cursor.fetchall()
        for col in columns:
            col_name, data_type, max_length, nullable, default = col
            length_info = f"({max_length})" if max_length else ""
            null_info = "NULL" if nullable == 'YES' else "NOT NULL"
            self.stdout.write(f'   • {col_name}: {data_type}{length_info} {null_info}')

    def mostrar_estructura_detallada(self, cursor, table_name, model):
        """Muestra una versión detallada de la estructura"""
        self.stdout.write(self.style.WARNING('\n' + '='*80))
        self.stdout.write(self.style.WARNING(f'📋 TABLA: {table_name}'))
        self.stdout.write(self.style.WARNING('='*80))
        
        if model:
            self.stdout.write(f'\n🔹 Modelo Django: {model.__name__}')
            self.stdout.write(f'🔹 App: {model._meta.app_label}')
            
            # Mostrar relaciones
            relaciones = []
            for field in model._meta.get_fields():
                if isinstance(field, models.ForeignKey):
                    relaciones.append(f'  → {field.name}: {field.related_model.__name__}')
                elif isinstance(field, models.ManyToManyField):
                    relaciones.append(f'  ↔ {field.name}: {field.related_model.__name__}')
                elif isinstance(field, models.OneToOneField):
                    relaciones.append(f'  ⇄ {field.name}: {field.related_model.__name__}')
            
            if relaciones:
                self.stdout.write('\n🔗 Relaciones:')
                for rel in relaciones:
                    self.stdout.write(rel)
        
        # Obtener columnas con más detalle
        self.stdout.write('\n📊 Columnas:')
        self.stdout.write('-' * 80)
        
        if connection.vendor == 'postgresql':
            cursor.execute("""
                SELECT 
                    column_name, 
                    data_type, 
                    character_maximum_length,
                    numeric_precision,
                    numeric_scale,
                    is_nullable, 
                    column_default,
                    ordinal_position
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position;
            """, [table_name])
        elif connection.vendor == 'mysql':
            cursor.execute("""
                SELECT 
                    column_name, 
                    data_type, 
                    character_maximum_length,
                    numeric_precision,
                    numeric_scale,
                    is_nullable, 
                    column_default,
                    ordinal_position
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                AND table_name = %s
                ORDER BY ordinal_position;
            """, [table_name])
        else:
            # SQLite
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            self.stdout.write(f"{'Nombre':<25} {'Tipo':<20} {'NULL':<8} {'Default':<15}")
            self.stdout.write('-' * 80)
            for col in columns:
                col_name = col[1]
                col_type = col[2]
                nullable = 'Sí' if not col[3] else 'No'
                default = str(col[4]) if col[4] else '-'
                self.stdout.write(f"{col_name:<25} {col_type:<20} {nullable:<8} {default:<15}")
            return
        
        columns = cursor.fetchall()
        self.stdout.write(f"{'Nombre':<25} {'Tipo':<25} {'NULL':<8} {'Default':<20}")
        self.stdout.write('-' * 80)
        
        for col in columns:
            col_name, data_type, max_length, precision, scale, nullable, default, pos = col
            
            # Formatear tipo
            if max_length:
                tipo_str = f"{data_type}({max_length})"
            elif precision and scale:
                tipo_str = f"{data_type}({precision},{scale})"
            elif precision:
                tipo_str = f"{data_type}({precision})"
            else:
                tipo_str = data_type
            
            null_str = 'Sí' if nullable == 'YES' else 'No'
            default_str = str(default)[:18] if default else '-'
            
            self.stdout.write(f"{col_name:<25} {tipo_str:<25} {null_str:<8} {default_str:<20}")
        
        # Obtener índices y constraints
        if connection.vendor == 'postgresql':
            cursor.execute("""
                SELECT 
                    indexname, 
                    indexdef
                FROM pg_indexes
                WHERE tablename = %s
                ORDER BY indexname;
            """, [table_name])
        elif connection.vendor == 'mysql':
            cursor.execute("""
                SELECT 
                    index_name,
                    GROUP_CONCAT(column_name ORDER BY seq_in_index) as columns
                FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                AND table_name = %s
                GROUP BY index_name
                ORDER BY index_name;
            """, [table_name])
        else:
            # SQLite
            cursor.execute(f"PRAGMA index_list({table_name})")
            indexes = cursor.fetchall()
            if indexes:
                self.stdout.write('\n🔑 Índices:')
                for idx in indexes:
                    self.stdout.write(f'  • {idx[1]}')
            return
        
        indexes = cursor.fetchall()
        if indexes:
            self.stdout.write('\n🔑 Índices y Constraints:')
            for idx in indexes:
                if connection.vendor == 'postgresql':
                    self.stdout.write(f'  • {idx[0]}: {idx[1][:70]}')
                else:
                    self.stdout.write(f'  • {idx[0]}: {idx[1]}')

    def mostrar_estructura_sql(self, cursor, table_name):
        """Muestra la estructura en formato SQL"""
        self.stdout.write(self.style.WARNING(f'\n-- TABLA: {table_name}'))
        
        if connection.vendor == 'postgresql':
            cursor.execute("""
                SELECT 
                    'CREATE TABLE ' || table_name || ' (' || 
                    string_agg(
                        column_name || ' ' || 
                        CASE 
                            WHEN data_type = 'character varying' THEN 'VARCHAR(' || character_maximum_length || ')'
                            WHEN data_type = 'character' THEN 'CHAR(' || character_maximum_length || ')'
                            WHEN data_type = 'numeric' THEN 'NUMERIC(' || numeric_precision || ',' || numeric_scale || ')'
                            ELSE UPPER(data_type)
                        END ||
                        CASE WHEN is_nullable = 'NO' THEN ' NOT NULL' ELSE '' END ||
                        CASE WHEN column_default IS NOT NULL THEN ' DEFAULT ' || column_default ELSE '' END,
                        ', '
                        ORDER BY ordinal_position
                    ) || ');'
                FROM information_schema.columns
                WHERE table_name = %s
                GROUP BY table_name;
            """, [table_name])
        else:
            self.stdout.write(f'-- Formato SQL no disponible para {connection.vendor}')
            return
        
        result = cursor.fetchone()
        if result:
            self.stdout.write(result[0])

