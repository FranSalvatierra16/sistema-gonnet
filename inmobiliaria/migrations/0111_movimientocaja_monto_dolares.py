from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inmobiliaria", "0110_backfill_neto_a_posesion_contratos"),
    ]

    operations = [
        migrations.AddField(
            model_name="movimientocaja",
            name="monto_dolares",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Dólares (USD) del movimiento: ingreso o egreso en efectivo dólar; no suma al total en ARS.",
                max_digits=14,
            ),
        ),
    ]
