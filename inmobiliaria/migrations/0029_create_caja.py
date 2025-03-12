from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0028_your_previous_migration'),  # Ajusta este número
    ]

    operations = [
        # Primero eliminamos la tabla si existe
        migrations.RunSQL(
            "DROP TABLE IF EXISTS inmobiliaria_caja;",
            reverse_sql=None
        ),
        
        # Luego creamos la tabla con la estructura correcta
        migrations.RunSQL(
            """
            CREATE TABLE inmobiliaria_caja (
                id bigint AUTO_INCREMENT PRIMARY KEY,
                fecha_apertura datetime(6) NOT NULL,
                fecha_cierre datetime(6) NULL,
                saldo_inicial decimal(10,2) NOT NULL,
                saldo_final decimal(10,2) NULL,
                estado varchar(10) NOT NULL,
                observaciones longtext NOT NULL,
                empleado_apertura_id bigint NOT NULL,
                empleado_cierre_id bigint NULL,
                sucursal_id bigint NOT NULL,
                FOREIGN KEY (sucursal_id) REFERENCES inmobiliaria_sucursal(id),
                FOREIGN KEY (empleado_apertura_id) REFERENCES auth_user(id),
                FOREIGN KEY (empleado_cierre_id) REFERENCES auth_user(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            reverse_sql="DROP TABLE inmobiliaria_caja;"
        )
    ] 