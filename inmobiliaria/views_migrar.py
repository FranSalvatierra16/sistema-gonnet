"""
Vista temporal para migrar datos de Heroku a Railway
ELIMINAR DESPUÉS DE LA MIGRACIÓN
"""
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import mysql.connector
from django.db import connection

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
    API que ejecuta la migración real
    """
    import mysql.connector
    
    # Configuración MySQL (Heroku)
    mysql_config = {
        'host': 'tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com',
        'user': 'oaai2ab9qsc7xvyn',
        'password': 'it2cxhq71iiubhlj',
        'database': 'vgd8ktskappw7cmj',
        'port': 3306,
        'use_pure': True
    }
    
    # Tablas a migrar
    tables = [
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
    
    try:
        mysql_conn = mysql.connector.connect(**mysql_config)
        mysql_cursor = mysql_conn.cursor(dictionary=True)
        
        results = {}
        total_migrated = 0
        
        for table in tables:
            try:
                mysql_cursor.execute(f"SELECT * FROM {table}")
                rows = mysql_cursor.fetchall()
                
                if not rows:
                    results[table] = 0
                    continue
                
                # Preparar INSERT para PostgreSQL
                columns = list(rows[0].keys())
                placeholders = ', '.join(['%s'] * len(columns))
                columns_str = ', '.join([f'"{col}"' for col in columns])
                
                insert_sql = f'INSERT INTO {table} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
                
                migrated = 0
                with connection.cursor() as postgres_cursor:
                    for row in rows:
                        try:
                            values = [row[col] for col in columns]
                            postgres_cursor.execute(insert_sql, values)
                            migrated += 1
                        except:
                            pass
                    
                    connection.commit()
                
                results[table] = migrated
                total_migrated += migrated
                
            except Exception as e:
                results[table] = f"Error: {str(e)[:100]}"
        
        mysql_cursor.close()
        mysql_conn.close()
        
        return JsonResponse({
            'success': True,
            'total_migrated': total_migrated,
            'results': results
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

