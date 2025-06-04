import os

def init_media_dirs():
    # Obtener el directorio base del proyecto
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Definir las rutas de los directorios
    media_root = os.path.join(base_dir, 'media')
    propiedades_dir = os.path.join(media_root, 'propiedades')
    static_root = os.path.join(base_dir, 'staticfiles')
    static_images = os.path.join(static_root, 'images')
    
    # Lista de directorios a crear
    dirs_to_create = [
        media_root,
        propiedades_dir,
        static_root,
        static_images
    ]
    
    # Crear directorios si no existen
    for directory in dirs_to_create:
        if not os.path.exists(directory):
            os.makedirs(directory, mode=0o755)
            print(f"Directorio creado: {directory}")
        else:
            print(f"Directorio ya existe: {directory}")
        
        # Asegurar permisos correctos
        os.chmod(directory, 0o755)
    
    # Crear archivo placeholder.jpg si no existe
    placeholder_path = os.path.join(static_images, 'placeholder.jpg')
    if not os.path.exists(placeholder_path):
        # Crear un archivo de imagen vacío como placeholder
        with open(placeholder_path, 'wb') as f:
            f.write(b'')
        print(f"Archivo placeholder creado: {placeholder_path}")
        os.chmod(placeholder_path, 0o644)
    else:
        print(f"Archivo placeholder ya existe: {placeholder_path}")

if __name__ == '__main__':
    init_media_dirs() 