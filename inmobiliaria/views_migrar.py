"""
Vista temporal para migrar datos de Heroku a Railway
ELIMINAR DESPUÉS DE LA MIGRACIÓN
"""
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
from django.contrib.auth import get_user_model
import json
import os

@csrf_exempt
def migrar_desde_heroku(request):
    """
    Vista temporal para migrar datos de MySQL (Heroku) a PostgreSQL (Railway)
    Acceder a: /migrar-desde-heroku-SECRETO123/
    """
    if request.user.is_authenticated and request.user.nivel >= 4:
        pass  # OK
    else:
        return HttpResponse("❌ No autorizado", status=403)
    
    html = """
    <html>
    <head><title>Migración Heroku → Railway</title></head>
    <body style="font-family: monospace; padding: 20px; background: #1a1a1a; color: #00ff00;">
        <h1>🔄 Migración de Datos: Heroku → Railway</h1>
        <div id="output">Iniciando migración...</div>
        <script>
            fetch('/api/ejecutar-migracion/', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    document.getElementById('output').innerHTML = 
                        '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                });
        </script>
    </body>
    </html>
    """
    return HttpResponse(html)


@csrf_exempt
def ejecutar_migracion_api(request):
    """
    API que ejecuta la migración desde el backup JSON
    """
    # ✅ Usar el backup JSON que ya está en el código
    backup_file = 'backup_heroku_20251106_124257.json'
    
    if not os.path.exists(backup_file):
        return JsonResponse({
            'success': False,
            'error': f'Archivo {backup_file} no encontrado. Archivos disponibles: {os.listdir(".")[:20]}'
        })
    
    try:
        # Leer backup JSON
        with open(backup_file, 'r', encoding='utf-8') as f:
            all_data = json.load(f)

        # Orden recomendado para respetar dependencias FK
        orden_prioritario = [
            'inmobiliaria_sucursal',
            'inmobiliaria_vendedor',
            'inmobiliaria_concepto',
            'inmobiliaria_cuentabancaria',
            'inmobiliaria_propietario',
            'inmobiliaria_inquilino',
            'inmobiliaria_propiedad',
            'inmobiliaria_disponibilidad',
            'inmobiliaria_historialdisponibilidad',
            'inmobiliaria_precio',
            'inmobiliaria_reserva',
            'inmobiliaria_contratoalquiler',
            'inmobiliaria_cuotamensual',
            'inmobiliaria_caja',
            'inmobiliaria_movimientocaja',
            'inmobiliaria_recibo',
            'inmobiliaria_comisionvendedor',
            'inmobiliaria_valevendedor',
        ]

        # Añadir cualquier otra tabla que no esté en la lista manteniendo el orden original
        tablas_ordenadas = []
        for tabla in orden_prioritario:
            if tabla in all_data:
                tablas_ordenadas.append(tabla)
        for tabla in all_data.keys():
            if tabla not in tablas_ordenadas:
                tablas_ordenadas.append(tabla)

        results = {}
        total_migrated = 0
        errores_por_tabla = {}

        table_columns_cache = {}
        boolean_columns_cache = {}

        def obtener_columnas_validas(nombre_tabla):
            if nombre_tabla in table_columns_cache:
                return table_columns_cache[nombre_tabla]
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = %s AND table_schema = 'public'
                """, [nombre_tabla])
                columnas = []
                booleanos = set()
                for column_name, data_type in cursor.fetchall():
                    columnas.append(column_name)
                    if data_type == 'boolean':
                        booleanos.add(column_name)
            table_columns_cache[nombre_tabla] = columnas
            boolean_columns_cache[nombre_tabla] = booleanos
            return columnas

        def limpiar_valor(columna, valor, booleanos):
            if columna in booleanos and valor is not None:
                if isinstance(valor, bool):
                    return valor
                if isinstance(valor, (int, float)):
                    return bool(valor)
                valor_str = str(valor).strip().lower()
                if valor_str in ('1', 'true', 't', 'yes', 'si'):
                    return True
                if valor_str in ('0', 'false', 'f', 'no'):
                    return False
            return valor

        for table_name in tablas_ordenadas:
            rows = all_data.get(table_name, [])
            try:
                if not rows:
                    results[table_name] = 0
                    continue

                columnas_validas = obtener_columnas_validas(table_name)
                booleanos = boolean_columns_cache.get(table_name, set())

                columnas_presentes = [c for c in rows[0].keys() if c in columnas_validas]
                if not columnas_presentes:
                    results[table_name] = 0
                    continue

                placeholders = ', '.join(['%s'] * len(columnas_presentes))
                columnas_str = ', '.join([f'"{col}"' for col in columnas_presentes])

                insert_sql = f'INSERT INTO {table_name} ({columnas_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

                migrated = 0
                with connection.cursor() as postgres_cursor:
                    for row in rows:
                        try:
                            valores = []
                            for col in columnas_presentes:
                                valor = row.get(col)
                                valor_limpio = limpiar_valor(col, valor, booleanos)
                                valores.append(valor_limpio)
                            postgres_cursor.execute(insert_sql, valores)
                            migrated += 1
                        except Exception as row_error:
                            lista = errores_por_tabla.setdefault(table_name, [])
                            if len(lista) < 5:
                                lista.append(str(row_error))
                    connection.commit()

                results[table_name] = migrated
                total_migrated += migrated

            except Exception as e:
                lista = errores_por_tabla.setdefault(table_name, [])
                if len(lista) < 5:
                    lista.append(str(e))
                results[table_name] = f"Error: {str(e)[:100]}"

        return JsonResponse({
            'success': True,
            'total_migrated': total_migrated,
            'results': results,
            'errores': errores_por_tabla
        })
        
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        })


@csrf_exempt
def resetear_password_temp(request):
    """
    Endpoint temporal para resetear la contraseña de un usuario.
    Acceder con GET: /resetear-password-temp-SECRETO123/?username=prueba&password=MiClave123
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    secreto = request.headers.get('X-Migracion-Secret') or request.POST.get('secret')
    if secreto != 'RESET-SECRET-123':
        return JsonResponse({'success': False, 'error': 'No autorizado'}, status=403)

    username = request.POST.get('username', 'prueba').strip()
    nuevo_password = request.POST.get('password', 'Temporal123!').strip()

    if not nuevo_password:
        return JsonResponse({'success': False, 'error': 'Password vacío'}, status=400)

    User = get_user_model()

    try:
        usuario = User.objects.get(username=username)
        usuario.set_password(nuevo_password)
        usuario.password_temporal = True
        usuario.save(update_fields=['password', 'password_temporal'])

        return JsonResponse({'success': True, 'message': f'Contraseña actualizada para {username}'})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': f'Usuario {username} no encontrado'}, status=404)


@csrf_exempt
def debug_usuarios(request):
    """Endpoint temporal para listar usuarios disponibles"""
    secreto = request.headers.get('X-Migracion-Secret') or request.GET.get('secret')
    if secreto != 'RESET-SECRET-123':
        return JsonResponse({'success': False, 'error': 'No autorizado'}, status=403)

    User = get_user_model()
    datos = list(User.objects.values('id', 'username', 'email', 'nivel')[:20])
    return JsonResponse({'success': True, 'total': User.objects.count(), 'usuarios': datos})

