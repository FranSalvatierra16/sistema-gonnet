"""
Importa al libro de Gery 1759 piso 12 las filas del Excel de gastos
como clasificación «facturado».

Uso:
  python manage.py importar_gery_1759_facturado
  python manage.py importar_gery_1759_facturado --dry-run
"""
from django.core.management.base import BaseCommand

from inmobiliaria.gery_1759_facturado_import import importar_gery_1759_facturado


class Command(BaseCommand):
    help = (
        'Importa el Excel de gastos de Gery 1759 piso 12 al libro '
        'como filas manuales clasificadas «facturado».'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--force', action='store_true')
        parser.add_argument('--json', default=None)

    def handle(self, *args, **options):
        result = importar_gery_1759_facturado(
            dry_run=options['dry_run'],
            force=options['force'],
            json_path=options['json'],
        )
        if result['ok']:
            self.stdout.write(self.style.SUCCESS(result['mensaje']))
        else:
            self.stderr.write(self.style.ERROR(result['mensaje']))
