#!/usr/bin/env python3
"""
Script para obtener información de la base de datos de Railway
"""
import os
from urllib.parse import urlparse

def parse_database_url(database_url):
    """Parsea DATABASE_URL y extrae información"""
    try:
        parsed = urlparse(database_url)
        
        info = {
            'engine': parsed.scheme.replace('postgresql', 'postgresql'),
            'host': parsed.hostname,
            'port': parsed.port or 5432,  # PostgreSQL default
            'database': parsed.path.lstrip('/'),
            'user': parsed.username,
            'password': '***'  # No mostrar contraseña
        }
        
        return info
    except Exception as e:
        return {'error': str(e)}

# Intentar obtener DATABASE_URL
database_url = os.environ.get('DATABASE_URL')

if database_url:
    print("=" * 60)
    print("📊 INFORMACIÓN DE BASE DE DATOS RAILWAY")
    print("=" * 60)
    print()
    
    info = parse_database_url(database_url)
    
    if 'error' in info:
        print(f"❌ Error al parsear DATABASE_URL: {info['error']}")
    else:
        print("🔍 Datos extraídos de DATABASE_URL:")
        print()
        print(f"  Host:     {info['host']}")
        print(f"  Puerto:   {info['port']}")
        print(f"  Base de datos: {info['database']}")
        print(f"  Usuario:  {info['user']}")
        print(f"  Contraseña: {info['password']}")
        print()
        print("=" * 60)
        print("📝 Para conectarte desde fuera de Railway:")
        print("=" * 60)
        print()
        print(f"  psql -h {info['host']} -p {info['port']} -U {info['user']} -d {info['database']}")
        print()
else:
    print("=" * 60)
    print("⚠️  DATABASE_URL no encontrada en variables de entorno")
    print("=" * 60)
    print()
    print("Para obtener la información de la base de datos:")
    print()
    print("1. Ve a Railway Dashboard: https://railway.app")
    print("2. Selecciona tu proyecto")
    print("3. Click en el servicio PostgreSQL")
    print("4. Ve a la pestaña 'Variables'")
    print("5. Busca 'DATABASE_URL'")
    print()
    print("O ve a 'Connect' → 'Connection Details' para ver:")
    print("  - Host")
    print("  - Port")
    print("  - Database")
    print("  - User")
    print()
    print("=" * 60)
    print("📋 Formato típico de Railway PostgreSQL:")
    print("=" * 60)
    print()
    print("  Host: containers-us-west-xxx.railway.app")
    print("  Puerto: 5432 (o el que Railway asigne)")
    print("  Database: railway")
    print("  User: postgres")
    print()

