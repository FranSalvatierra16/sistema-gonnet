# Generated manually to create basic Caja table

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0023_add_fecha_operacion_to_contrato'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE TABLE IF NOT EXISTS inmobiliaria_caja (
                id bigint NOT NULL AUTO_INCREMENT,
                numero int NOT NULL,
                sucursal_id bigint NOT NULL,
                fecha_apertura datetime(6) NOT NULL,
                fecha_cierre datetime(6) NULL,
                saldo_inicial decimal(10,2) NOT NULL,
                saldo_final decimal(10,2) NULL,
                estado varchar(20) NOT NULL DEFAULT 'abierta',
                empleado_id bigint NOT NULL,
                PRIMARY KEY (id),
                UNIQUE KEY inmobiliaria_caja_numero_sucursal_id_uniq (numero, sucursal_id)
            );
            """,
            reverse_sql="DROP TABLE IF EXISTS inmobiliaria_caja;"
        ),
    ] 