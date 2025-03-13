from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0030_your_previous_migration'),  # Ajusta este número
    ]

    operations = [
        migrations.RunSQL(
            # Primero eliminamos la tabla si existe
            "DROP TABLE IF EXISTS inmobiliaria_caja;",
            reverse_sql=None
        ),
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
                CONSTRAINT fk_caja_sucursal 
                    FOREIGN KEY (sucursal_id) 
                    REFERENCES inmobiliaria_sucursal(id),
                CONSTRAINT fk_caja_empleado_apertura 
                    FOREIGN KEY (empleado_apertura_id) 
                    REFERENCES inmobiliaria_vendedor(id),
                CONSTRAINT fk_caja_empleado_cierre 
                    FOREIGN KEY (empleado_cierre_id) 
                    REFERENCES inmobiliaria_vendedor(id),
                CONSTRAINT unique_sucursal_estado 
                    UNIQUE (sucursal_id, estado)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            reverse_sql="DROP TABLE IF EXISTS inmobiliaria_caja;"
        )
    ] 