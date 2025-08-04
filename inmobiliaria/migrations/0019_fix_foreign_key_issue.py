# Generated manually to fix foreign key issue

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0015_add_confirmada_no_pagada_state'),
    ]

    operations = [
        migrations.RunSQL(
            # Eliminar la foreign key problemática si existe
            sql="""
            SET @constraint_exists = (
                SELECT COUNT(*)
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'inmobiliaria_movimientocaja'
                AND CONSTRAINT_NAME = 'inmobiliaria_movimie_caja_id_8fbc19e2_fk_inmobilia'
            );
            SET @sql = IF(@constraint_exists > 0, 
                'ALTER TABLE inmobiliaria_movimientocaja DROP FOREIGN KEY inmobiliaria_movimie_caja_id_8fbc19e2_fk_inmobilia', 
                'SELECT "Foreign key does not exist"'
            );
            PREPARE stmt FROM @sql;
            EXECUTE stmt;
            DEALLOCATE PREPARE stmt;
            """,
            reverse_sql="",
        ),
        migrations.RunSQL(
            # Eliminar la columna caja_id si existe
            sql="""
            SET @column_exists = (
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'inmobiliaria_movimientocaja'
                AND COLUMN_NAME = 'caja_id'
            );
            SET @sql = IF(@column_exists > 0, 
                'ALTER TABLE inmobiliaria_movimientocaja DROP COLUMN caja_id', 
                'SELECT "Column caja_id does not exist"'
            );
            PREPARE stmt FROM @sql;
            EXECUTE stmt;
            DEALLOCATE PREPARE stmt;
            """,
            reverse_sql="",
        ),
        migrations.RunSQL(
            # Recrear la tabla caja con la nueva estructura
            sql="""
            DROP TABLE IF EXISTS inmobiliaria_caja;
            CREATE TABLE inmobiliaria_caja (
                numero int NOT NULL,
                sucursal_id bigint NOT NULL,
                fecha_apertura datetime(6) NOT NULL,
                fecha_cierre datetime(6) NULL,
                saldo_inicial decimal(10,2) NOT NULL,
                saldo_final decimal(10,2) NULL,
                estado varchar(20) NOT NULL,
                empleado_id bigint NOT NULL,
                id bigint NOT NULL AUTO_INCREMENT,
                PRIMARY KEY (id),
                UNIQUE KEY inmobiliaria_caja_numero_sucursal_id_b8c8a663_uniq (numero, sucursal_id),
                KEY inmobiliaria_caja_sucursal_id_86d7c9b7_fk_inmobilia (sucursal_id),
                KEY inmobiliaria_caja_empleado_id_f3f1b5d7_fk_auth_user_id (empleado_id),
                CONSTRAINT inmobiliaria_caja_empleado_id_f3f1b5d7_fk_auth_user_id FOREIGN KEY (empleado_id) REFERENCES auth_user (id),
                CONSTRAINT inmobiliaria_caja_sucursal_id_86d7c9b7_fk_inmobilia FOREIGN KEY (sucursal_id) REFERENCES inmobiliaria_sucursal (id)
            );
            """,
            reverse_sql="",
        ),
        migrations.RunSQL(
            # Agregar de vuelta la columna caja_id a movimientocaja si no existe
            sql="""
            SET @column_exists = (
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'inmobiliaria_movimientocaja'
                AND COLUMN_NAME = 'caja_id'
            );
            SET @sql = IF(@column_exists = 0, 
                'ALTER TABLE inmobiliaria_movimientocaja ADD COLUMN caja_id bigint NULL', 
                'SELECT "Column caja_id already exists"'
            );
            PREPARE stmt FROM @sql;
            EXECUTE stmt;
            DEALLOCATE PREPARE stmt;
            """,
            reverse_sql="",
        ),
        migrations.RunSQL(
            # Crear la nueva foreign key que funciona si no existe
            sql="""
            SET @constraint_exists = (
                SELECT COUNT(*)
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'inmobiliaria_movimientocaja'
                AND CONSTRAINT_NAME = 'inmobiliaria_movimie_caja_id_new_fk'
            );
            SET @sql = IF(@constraint_exists = 0, 
                'ALTER TABLE inmobiliaria_movimientocaja ADD CONSTRAINT inmobiliaria_movimie_caja_id_new_fk FOREIGN KEY (caja_id) REFERENCES inmobiliaria_caja (id)', 
                'SELECT "Foreign key already exists"'
            );
            PREPARE stmt FROM @sql;
            EXECUTE stmt;
            DEALLOCATE PREPARE stmt;
            """,
            reverse_sql="",
        ),
    ] 