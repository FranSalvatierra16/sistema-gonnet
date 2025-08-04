# Generated manually to recreate Caja table

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0016_caja_id_alter_caja_numero'),
    ]

    operations = [
        # Paso 1: Eliminar todas las foreign keys hacia la tabla Caja
        migrations.RunSQL(
            """
            SET @fk_exists = 0;
            SELECT COUNT(*) INTO @fk_exists 
            FROM information_schema.table_constraints 
            WHERE table_schema = DATABASE() 
            AND table_name = 'inmobiliaria_movimientocaja' 
            AND constraint_name = 'inmobiliaria_movimie_caja_id_8fbc19e2_fk_inmobilia';
            
            SET @sql = IF(@fk_exists > 0, 'ALTER TABLE inmobiliaria_movimientocaja DROP FOREIGN KEY inmobiliaria_movimie_caja_id_8fbc19e2_fk_inmobilia;', 'SELECT "FK already dropped";');
            PREPARE stmt FROM @sql;
            EXECUTE stmt;
            DEALLOCATE PREPARE stmt;
            """,
            reverse_sql=""
        ),
        
        # Paso 2: Eliminar todos los datos
        migrations.RunSQL(
            "DELETE FROM inmobiliaria_movimientocaja;",
            reverse_sql=""
        ),
        migrations.RunSQL(
            "DELETE FROM inmobiliaria_caja;",
            reverse_sql=""
        ),
        
        # Paso 3: Eliminar la tabla Caja completamente
        migrations.RunSQL(
            "DROP TABLE IF EXISTS inmobiliaria_caja;",
            reverse_sql=""
        ),
        
        # Paso 4: Recrear la tabla Caja con la estructura correcta
        migrations.RunSQL(
            """
            CREATE TABLE inmobiliaria_caja (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                numero INT NOT NULL,
                sucursal_id BIGINT NOT NULL,
                fecha_apertura DATETIME(6) NOT NULL,
                fecha_cierre DATETIME(6) NULL,
                saldo_inicial DECIMAL(10,2) NOT NULL,
                saldo_final DECIMAL(10,2) NULL,
                estado VARCHAR(10) NOT NULL DEFAULT 'abierta',
                usuario_apertura_id INT NOT NULL,
                usuario_cierre_id INT NULL,
                observaciones_apertura LONGTEXT NOT NULL,
                observaciones_cierre LONGTEXT NOT NULL,
                UNIQUE KEY unique_numero_sucursal (numero, sucursal_id),
                KEY inmobiliaria_caja_sucursal_id_idx (sucursal_id),
                KEY inmobiliaria_caja_usuario_apertura_id_idx (usuario_apertura_id),
                KEY inmobiliaria_caja_usuario_cierre_id_idx (usuario_cierre_id),
                CONSTRAINT inmobiliaria_caja_sucursal_id_fk FOREIGN KEY (sucursal_id) REFERENCES inmobiliaria_sucursal (id),
                CONSTRAINT inmobiliaria_caja_usuario_apertura_id_fk FOREIGN KEY (usuario_apertura_id) REFERENCES auth_user (id),
                CONSTRAINT inmobiliaria_caja_usuario_cierre_id_fk FOREIGN KEY (usuario_cierre_id) REFERENCES auth_user (id)
            );
            """,
            reverse_sql="DROP TABLE inmobiliaria_caja;"
        ),
        
        # Paso 5: Recrear la foreign key en MovimientoCaja
        migrations.RunSQL(
            "ALTER TABLE inmobiliaria_movimientocaja ADD CONSTRAINT inmobiliaria_movimie_caja_id_8fbc19e2_fk_inmobilia FOREIGN KEY (caja_id) REFERENCES inmobiliaria_caja (id);",
            reverse_sql="ALTER TABLE inmobiliaria_movimientocaja DROP FOREIGN KEY inmobiliaria_movimie_caja_id_8fbc19e2_fk_inmobilia;"
        ),
    ] 