from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Arregla la secuencia de IDs de la tabla inmobiliaria_vendedor en PostgreSQL'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # Obtener el máximo ID actual en la tabla
            cursor.execute("SELECT MAX(id) FROM inmobiliaria_vendedor;")
            max_id = cursor.fetchone()[0] or 0
            
            self.stdout.write(f"ID máximo encontrado en la tabla: {max_id}")
            
            # Obtener el nombre de la secuencia desde la tabla directamente
            cursor.execute("""
                SELECT pg_get_serial_sequence('inmobiliaria_vendedor', 'id');
            """)
            sequence_result = cursor.fetchone()
            
            if sequence_result and sequence_result[0]:
                sequence_name = sequence_result[0]
            else:
                # Fallback: intentar con el nombre estándar de Django
                sequence_name = 'inmobiliaria_vendedor_id_seq'
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️ No se pudo obtener el nombre de la secuencia automáticamente. '
                        f'Usando: {sequence_name}'
                    )
                )
            
            self.stdout.write(f"Secuencia encontrada: {sequence_name}")
            
            # Obtener el valor actual de la secuencia
            cursor.execute(f"SELECT last_value FROM {sequence_name};")
            current_value = cursor.fetchone()[0]
            
            self.stdout.write(f"Valor actual de la secuencia: {current_value}")
            
            # Verificar todos los IDs existentes para encontrar gaps
            cursor.execute("SELECT id FROM inmobiliaria_vendedor ORDER BY id;")
            existing_ids = [row[0] for row in cursor.fetchall()]
            
            if existing_ids:
                self.stdout.write(f"IDs existentes: {existing_ids}")
            
            # Establecer el siguiente valor de la secuencia
            # Usar 'true' significa que el próximo nextval() devolverá el valor que establecimos
            # Usar 'false' significa que el próximo nextval() devolverá el valor + 1
            # Queremos que el próximo ID sea max_id + 1, así que usamos max_id con 'true'
            next_value = max_id + 1
            cursor.execute(f"SELECT setval('{sequence_name}', {max_id}, true);")
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Secuencia actualizada correctamente. '
                    f'El próximo ID será: {next_value}'
                )
            )
            
            # Verificar el nuevo valor
            cursor.execute(f"SELECT last_value FROM {sequence_name};")
            new_value = cursor.fetchone()[0]
            self.stdout.write(f"Valor verificado de la secuencia: {new_value}")
            
            # Verificar que el próximo valor será correcto (sin consumirlo)
            # Usamos currval para ver el valor actual sin avanzar
            try:
                cursor.execute(f"SELECT currval('{sequence_name}');")
                curr_val = cursor.fetchone()[0]
                self.stdout.write(f"Valor actual de la secuencia (currval): {curr_val}")
            except:
                # Si currval falla (porque nunca se ha llamado nextval), está bien
                pass

