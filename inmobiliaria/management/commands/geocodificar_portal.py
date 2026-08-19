from django.core.management.base import BaseCommand
from django.db.models import Q

from inmobiliaria.models import Propiedad
from inmobiliaria.portal_geo import actualizar_coordenadas_propiedad, google_maps_api_key


class Command(BaseCommand):
    help = 'Geocodifica propiedades publicadas en la web para mostrarlas en el mapa.'

    def add_arguments(self, parser):
        parser.add_argument('--todas', action='store_true', help='También las que no están publicadas.')
        parser.add_argument('--force', action='store_true', help='Recalcular aunque ya tengan coordenadas.')
        parser.add_argument('--limit', type=int, default=0)

    def handle(self, *args, **options):
        qs = Propiedad.objects.all().order_by('id')
        if not options['todas']:
            qs = qs.filter(publicar_web=True)
        if not options['force']:
            qs = qs.filter(Q(latitud__isnull=True) | Q(longitud__isnull=True))
        limit = options['limit']
        if limit:
            qs = qs[:limit]
        ok = fail = 0
        usar_sleep = not google_maps_api_key()
        if usar_sleep:
            self.stdout.write('Sin GOOGLE_MAPS_API_KEY: se usa Nominatim (1 pedido/seg).')
        for prop in qs.iterator():
            try:
                saved = actualizar_coordenadas_propiedad(
                    prop,
                    force=options['force'],
                    sleep_nominatim=usar_sleep,
                )
            except Exception as exc:
                fail += 1
                self.stderr.write(f'Error ficha {prop.id}: {exc}')
                continue
            if saved:
                ok += 1
                self.stdout.write(f'OK {prop.id} → {prop.latitud}, {prop.longitud}')
            else:
                fail += 1
                self.stdout.write(self.style.WARNING(f'Sin coords {prop.id} ({prop.direccion})'))
        self.stdout.write(self.style.SUCCESS(f'Listo. Geocodificadas: {ok}. Sin resultado: {fail}.'))
