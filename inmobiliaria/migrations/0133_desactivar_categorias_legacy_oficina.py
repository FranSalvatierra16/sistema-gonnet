from django.db import migrations


class Migration(migrations.Migration):
    """
    Las categorías del resumen de cierre se sincronizan al entrar a Oficina
    (asegurar_estructura_cierre_oficina + desactivar_categorias_legacy_oficina).
    Sin RunPython: evita fallos del pre-deploy en Railway.
    """

    dependencies = [
        ('inmobiliaria', '0132_categoria_gasto_vendedor_cierre_oficina'),
    ]

    operations = []
