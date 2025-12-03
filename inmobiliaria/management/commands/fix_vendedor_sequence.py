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
            
            # Establecer el siguiente valor de la secuencia al máximo ID + 1
            next_value = max_id + 1
            cursor.execute(f"SELECT setval('{sequence_name}', {next_value}, false);")
            
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

