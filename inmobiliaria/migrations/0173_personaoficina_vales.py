# Generated manually for PersonaOficina + vínculo en vales

from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


def _tokenizar(ap, nom):
    raw = f'{ap or ""} {nom or ""}'.casefold()
    for a, b in (('á', 'a'), ('é', 'e'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'), ('ü', 'u'), ('ñ', 'n')):
        raw = raw.replace(a, b)
    return {t for t in ''.join(c if c.isalnum() or c.isspace() else ' ' for c in raw).split() if t}


def _cluster_key(ap, nom):
    tokens = _tokenizar(ap, nom)
    if not tokens:
        return ('sin_nombre',)
    if tokens <= {'cacho', 'ruben'}:
        return ('cacho_ruben',)
    # Marta sola o Marta Gómez / Gómez Marta
    if tokens == {'marta'} or tokens == {'marta', 'gomez'}:
        return ('marta_gomez',)
    # Sergio solo o Sergio Ponce / Ponce Sergio
    if tokens == {'sergio'} or tokens == {'sergio', 'ponce'}:
        return ('sergio_ponce',)
    if tokens <= {'colon'}:
        return ('colon',)
    return (tuple(sorted(tokens)),)


def _canonical(cluster, sample_ap, sample_nom, sample_dni):
    if cluster == ('cacho_ruben',):
        return 'Cacho / Rubén', '', (sample_dni or '').strip()
    if cluster == ('marta_gomez',):
        return 'Gómez', 'Marta', (sample_dni or '').strip()
    if cluster == ('sergio_ponce',):
        return 'Ponce', 'Sergio', (sample_dni or '').strip()
    if cluster == ('colon',):
        return 'Colon', '', (sample_dni or '').strip()
    ap = (sample_ap or '').strip()
    nom = (sample_nom or '').strip()
    if ap and nom and ap.casefold() == nom.casefold():
        return ap.title(), '', (sample_dni or '').strip()
    return (ap.title() if ap else ap), (nom.title() if nom else nom), (sample_dni or '').strip()


def vincular_personas_oficina(apps, schema_editor):
    ValeVendedor = apps.get_model('inmobiliaria', 'ValeVendedor')
    PersonaOficina = apps.get_model('inmobiliaria', 'PersonaOficina')
    Sucursal = apps.get_model('inmobiliaria', 'Sucursal')

    for suc in Sucursal.objects.all():
        vales = list(
            ValeVendedor.objects.filter(tipo_beneficiario='otro')
            .filter(Q(movimiento_caja__sucursal_id=suc.id) | Q(usuario_creador__sucursal_id=suc.id))
            .distinct()
        )
        if not vales:
            continue
        clusters = {}
        for v in vales:
            key = _cluster_key(v.beneficiario_apellido, v.beneficiario_nombre)
            clusters.setdefault(key, []).append(v)
        for key, group in clusters.items():
            sample = group[0]
            ap, nom, dni = _canonical(
                key,
                sample.beneficiario_apellido,
                sample.beneficiario_nombre,
                sample.beneficiario_dni,
            )
            persona = PersonaOficina.objects.create(
                sucursal_id=suc.id,
                apellido=ap,
                nombre=nom,
                dni=dni,
                activa=True,
            )
            ValeVendedor.objects.filter(pk__in=[v.pk for v in group]).update(
                persona_oficina_id=persona.pk,
                beneficiario_apellido=ap,
                beneficiario_nombre=nom,
                beneficiario_dni=dni,
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0172_sucursal_comision_minima_operacion'),
    ]

    operations = [
        migrations.CreateModel(
            name='PersonaOficina',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('apellido', models.CharField(blank=True, max_length=100)),
                ('nombre', models.CharField(blank=True, max_length=100)),
                ('dni', models.CharField(blank=True, max_length=20)),
                ('activa', models.BooleanField(default=True)),
                ('notas', models.CharField(blank=True, max_length=255)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                (
                    'sucursal',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='personas_oficina',
                        to='inmobiliaria.sucursal',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Persona de oficina (vales)',
                'verbose_name_plural': 'Personas de oficina (vales)',
                'ordering': ['apellido', 'nombre', 'id'],
            },
        ),
        migrations.AddField(
            model_name='valevendedor',
            name='persona_oficina',
            field=models.ForeignKey(
                blank=True,
                help_text='Beneficiario guardado en Oficina (otras personas).',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='vales',
                to='inmobiliaria.personaoficina',
                verbose_name='Persona de oficina',
            ),
        ),
        migrations.RunPython(vincular_personas_oficina, noop_reverse),
    ]
