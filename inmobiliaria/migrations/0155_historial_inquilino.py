from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def backfill_historial_inquilino(apps, schema_editor):
    Reserva = apps.get_model('inmobiliaria', 'Reserva')
    HistorialInquilino = apps.get_model('inmobiliaria', 'HistorialInquilino')

    for reserva in Reserva.objects.filter(cliente_id__isnull=False, eliminada=True).iterator():
        if HistorialInquilino.objects.filter(reserva_id=reserva.id, tipo='operacion_anulada').exists():
            continue
        HistorialInquilino.objects.create(
            inquilino_id=reserva.cliente_id,
            reserva_id=reserva.id,
            tipo='operacion_anulada',
            detalle='Anulación o eliminación registrada retroactivamente.',
            usuario_id=reserva.usuario_eliminacion_id,
            creado=reserva.fecha_eliminacion or reserva.fecha_creacion,
        )

    for reserva in Reserva.objects.filter(cliente_id__isnull=False, fue_editada=True).iterator():
        if not reserva.fecha_inicio_original or not reserva.fecha_fin_original:
            continue
        if HistorialInquilino.objects.filter(reserva_id=reserva.id, tipo='fechas_modificadas').exists():
            continue
        HistorialInquilino.objects.create(
            inquilino_id=reserva.cliente_id,
            reserva_id=reserva.id,
            tipo='fechas_modificadas',
            detalle='Modificación de fechas registrada retroactivamente.',
            fecha_inicio_anterior=reserva.fecha_inicio_original,
            fecha_fin_anterior=reserva.fecha_fin_original,
            fecha_inicio_nueva=reserva.fecha_inicio,
            fecha_fin_nueva=reserva.fecha_fin,
            creado=reserva.fecha_creacion,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0154_performance_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='HistorialInquilino',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(
                    choices=[
                        ('reserva_creada', 'Reserva creada'),
                        ('operacion_anulada', 'Operación anulada'),
                        ('vuelta_a_reserva', 'Vuelta a reserva pendiente'),
                        ('montos_modificados', 'Montos modificados'),
                        ('fechas_modificadas', 'Fechas modificadas'),
                        ('estado_modificado', 'Estado modificado'),
                    ],
                    max_length=32,
                )),
                ('detalle', models.TextField(blank=True)),
                ('precio_anterior', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('precio_nuevo', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('senia_anterior', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('senia_nueva', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('fecha_inicio_anterior', models.DateField(blank=True, null=True)),
                ('fecha_fin_anterior', models.DateField(blank=True, null=True)),
                ('fecha_inicio_nueva', models.DateField(blank=True, null=True)),
                ('fecha_fin_nueva', models.DateField(blank=True, null=True)),
                ('estado_anterior', models.CharField(blank=True, max_length=32)),
                ('estado_nuevo', models.CharField(blank=True, max_length=32)),
                ('creado', models.DateTimeField(default=django.utils.timezone.now)),
                ('contrato', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='historial_inquilino_eventos',
                    to='inmobiliaria.contratoalquiler',
                )),
                ('inquilino', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='historial_eventos',
                    to='inmobiliaria.inquilino',
                )),
                ('reserva', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='historial_inquilino_eventos',
                    to='inmobiliaria.reserva',
                )),
                ('usuario', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='historial_inquilino_registrado',
                    to='inmobiliaria.vendedor',
                )),
            ],
            options={
                'verbose_name': 'Historial de inquilino',
                'verbose_name_plural': 'Historial de inquilinos',
                'ordering': ['-creado', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='historialinquilino',
            index=models.Index(fields=['inquilino', '-creado'], name='hist_inq_inq_creado_idx'),
        ),
        migrations.AddIndex(
            model_name='historialinquilino',
            index=models.Index(fields=['reserva', '-creado'], name='hist_inq_res_creado_idx'),
        ),
        migrations.RunPython(backfill_historial_inquilino, migrations.RunPython.noop),
    ]
