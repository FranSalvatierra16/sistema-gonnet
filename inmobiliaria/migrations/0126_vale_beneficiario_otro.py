from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0125_caja_arqueo_anteriores_json'),
    ]

    operations = [
        migrations.AddField(
            model_name='valevendedor',
            name='beneficiario_apellido',
            field=models.CharField(blank=True, max_length=100, verbose_name='Apellido beneficiario'),
        ),
        migrations.AddField(
            model_name='valevendedor',
            name='beneficiario_dni',
            field=models.CharField(blank=True, max_length=20, verbose_name='DNI beneficiario'),
        ),
        migrations.AddField(
            model_name='valevendedor',
            name='beneficiario_nombre',
            field=models.CharField(blank=True, max_length=100, verbose_name='Nombre beneficiario'),
        ),
        migrations.AddField(
            model_name='valevendedor',
            name='tipo_beneficiario',
            field=models.CharField(
                choices=[('vendedor', 'Vendedor / productor'), ('otro', 'Otra persona')],
                default='vendedor',
                max_length=20,
                verbose_name='Tipo de beneficiario',
            ),
        ),
        migrations.AlterField(
            model_name='valevendedor',
            name='vendedor',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vales',
                to='inmobiliaria.vendedor',
                verbose_name='Vendedor',
            ),
        ),
    ]
