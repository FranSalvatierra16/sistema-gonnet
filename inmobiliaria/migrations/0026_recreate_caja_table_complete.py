# Generated manually to recreate Caja table with all correct fields

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0024_create_basic_caja_table'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DROP TABLE IF EXISTS inmobiliaria_caja;
            CREATE TABLE inmobiliaria_caja (
                id bigint NOT NULL AUTO_INCREMENT,
                numero int NOT NULL,
                sucursal_id bigint NOT NULL,
                fecha_apertura datetime(6) NOT NULL,
                fecha_cierre datetime(6) NULL,
                saldo_inicial decimal(10,2) NOT NULL,
                saldo_final decimal(10,2) NULL,
                estado varchar(20) NOT NULL DEFAULT 'abierta',
                usuario_apertura_id bigint NOT NULL,
                usuario_cierre_id bigint NULL,
                observaciones_apertura longtext NOT NULL DEFAULT '',
                observaciones_cierre longtext NOT NULL DEFAULT '',
                PRIMARY KEY (id),
                UNIQUE KEY inmobiliaria_caja_numero_sucursal_id_uniq (numero, sucursal_id)
            );
            """,
            reverse_sql="DROP TABLE IF EXISTS inmobiliaria_caja;"
        ),
    ] 