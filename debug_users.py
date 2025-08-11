#!/usr/bin/env python3

import os
import sys
import django

# Configurar Django
sys.path.append('/Users/fransalva/workspace/sistema-gonnet')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')
django.setup()

from django.contrib.auth import get_user_model

def main():
    User = get_user_model()
    usuarios = User.objects.all()
    
    print("=== USUARIOS EN EL SISTEMA ===")
    print(f"Modelo de usuario: {User.__name__}")
    print(f"Total de usuarios: {usuarios.count()}")
    print()
    
    if usuarios.count() == 0:
        print("❌ No hay usuarios en el sistema.")
        return
    
    for user in usuarios:
        print(f"ID: {user.id}")
        print(f"Username: {user.username}")
        print(f"Email: {user.email or '(Sin email)'}")
        print(f"Nombre: {user.first_name or '(Sin nombre)'} {user.last_name or '(Sin apellido)'}")
        print(f"Activo: {user.is_active}")
        print(f"Staff: {user.is_staff}")
        print(f"Superuser: {user.is_superuser}")
        print("---")
    
    # Buscar usuarios sin email
    sin_email = usuarios.filter(email__isnull=True) | usuarios.filter(email__exact='')
    if sin_email.exists():
        print(f"\n⚠️  Usuarios sin email configurado: {sin_email.count()}")
        for user in sin_email:
            print(f"  - {user.username} (ID: {user.id})")

if __name__ == "__main__":
    main() 