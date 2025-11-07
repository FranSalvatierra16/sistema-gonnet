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
        
        results = {}
        total_migrated = 0
        
        for table_name, rows in all_data.items():
            try:
                if not rows:
                    results[table_name] = 0
                    continue
                
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
                        except Exception as row_error:
                            pass  # Ignorar errores de FK
                    
                    connection.commit()
                
                results[table_name] = migrated
                total_migrated += migrated
                
            except Exception as e:
                results[table_name] = f"Error: {str(e)[:100]}"
        
        return JsonResponse({
            'success': True,
            'total_migrated': total_migrated,
            'results': results
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

