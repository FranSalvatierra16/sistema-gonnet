"""Importación de Excel de Gery 1759 piso 12 al libro (facturado / en negro)."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.db.models import Q

from inmobiliaria.models import FilaManualLibroPropiedad, Propiedad

DATA_DIR = Path(__file__).resolve().parent / 'data'
DATA_PATH_FACTURADO = DATA_DIR / 'gery_1759_facturado_excel.json'
DATA_PATH_NEGRO = DATA_DIR / 'gery_1759_negro_excel.json'
# alias retrocompatible
DATA_PATH = DATA_PATH_FACTURADO

CENT = Decimal('0.01')
MAX_MONTO = Decimal('999999999999.99')
MAX_TIPO_CAMBIO = Decimal('100000.00')


def _q2(value) -> Decimal:
    if value is None or value == '':
        return Decimal('0.00')
    try:
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal('0.00')


def _monto_seguro(value) -> Decimal:
    monto = _q2(value)
    if monto < 0:
        monto = abs(monto)
    if monto > MAX_MONTO:
        return Decimal('0.00')
    return monto


def _tipo_cambio_seguro(value):
    if value is None or value == '':
        return None
    try:
        tc = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except Exception:
        return None
    if tc <= 0 or tc > MAX_TIPO_CAMBIO:
        return None
    return tc


def _parse_fecha_raw(fecha_raw: str):
    raw = (fecha_raw or '').strip()
    if not raw:
        return None
    for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    m = re.match(r'^(\d{1,2})/(\d{1,2})$', raw)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None


def resolver_anios_filas(filas: list[dict]) -> list[dict]:
    """Completa fechas DD/MM sin año con el año del movimiento datado más cercano."""
    parsed = []
    for fila in filas:
        valor = _parse_fecha_raw((fila.get('fecha_raw') or '').strip())
        parsed.append({**fila, '_fecha_parsed': valor})

    n = len(parsed)
    for i, item in enumerate(parsed):
        valor = item['_fecha_parsed']
        if isinstance(valor, date) or valor is None:
            continue
        day, month = valor
        candidatos = []
        for j in range(i - 1, -1, -1):
            v = parsed[j]['_fecha_parsed']
            if isinstance(v, date):
                candidatos.append((i - j, v.year))
                break
        for j in range(i + 1, n):
            v = parsed[j]['_fecha_parsed']
            if isinstance(v, date):
                candidatos.append((j - i, v.year))
                break
        if not candidatos:
            item['_fecha_parsed'] = None
            continue
        candidatos.sort(key=lambda x: x[0])
        year = candidatos[0][1]
        try:
            item['_fecha_parsed'] = date(year, month, day)
        except ValueError:
            item['_fecha_parsed'] = None
            continue
        item['fecha_raw'] = item['_fecha_parsed'].strftime('%d/%m/%Y')
    return parsed


def descripcion_fila_excel(fila: dict, clasificacion: str = 'facturado') -> str:
    proveedor = (fila.get('proveedor') or '').strip()
    concepto = (fila.get('concepto') or '').strip()
    comprobante = (fila.get('comprobante') or '').strip()
    if proveedor and concepto:
        texto = f'{proveedor} — {concepto}'
    elif concepto:
        texto = concepto
    elif proveedor:
        texto = proveedor
    else:
        texto = (
            'Gasto en negro (Excel)'
            if clasificacion == 'negro'
            else 'Gasto facturado (Excel)'
        )
    if comprobante:
        texto = f'{texto} [{comprobante}]'
    return texto[:255]


def encontrar_propiedad_gery() -> Propiedad | None:
    prop = Propiedad.objects.filter(pk='1759').first()
    if prop:
        return prop
    qs = Propiedad.objects.filter(piso__iexact='12').filter(
        Q(direccion__icontains='gery') | Q(direccion__icontains='1759')
    )
    return qs.filter(departamento__iexact='1').first() or qs.first()


def _match_existente(propiedad, fecha, gastos_ars, gastos_usd, descripcion, clasificacion):
    qs = FilaManualLibroPropiedad.objects.filter(
        propiedad=propiedad,
        fecha=fecha,
        clasificacion_libro=clasificacion,
    )
    for fila in qs:
        if _q2(fila.gastos_ars) == gastos_ars and _q2(fila.gastos_usd) == gastos_usd:
            return fila
        if (fila.descripcion or '').strip() == descripcion and (
            _q2(fila.gastos_ars) == gastos_ars or _q2(fila.gastos_usd) == gastos_usd
        ):
            return fila
    return None


def importar_gery_1759_excel(
    *,
    clasificacion: str = 'facturado',
    dry_run: bool = False,
    force: bool = False,
    json_path: Path | None = None,
    propiedad: Propiedad | None = None,
) -> dict:
    """
    Carga un Excel al libro como filas manuales con clasificación facturado|negro.
    Ajusta el Inicio de caja a la primera fecha importada si hace falta.
    """
    from inmobiliaria.models import InicioCajaLibroPropiedad

    if clasificacion not in ('facturado', 'negro'):
        return {'ok': False, 'mensaje': 'Clasificación inválida.'}

    if json_path is None:
        path = DATA_PATH_NEGRO if clasificacion == 'negro' else DATA_PATH_FACTURADO
    else:
        path = Path(json_path)

    if not path.exists():
        return {'ok': False, 'mensaje': f'No existe el archivo {path.name}.'}

    with path.open(encoding='utf-8') as fh:
        raw_rows = json.load(fh)
    if not isinstance(raw_rows, list):
        return {'ok': False, 'mensaje': 'El JSON debe ser una lista de filas.'}

    filas = resolver_anios_filas(raw_rows)
    if propiedad is None:
        propiedad = encontrar_propiedad_gery()
    if not propiedad:
        return {'ok': False, 'mensaje': 'No se encontró la propiedad Gery 1759 piso 12.'}

    label = 'en negro' if clasificacion == 'negro' else 'facturado'
    creadas = actualizadas = omitidas = sin_fecha = 0
    fechas_ok: list[date] = []

    for item in filas:
        fecha = item.get('_fecha_parsed')
        if not isinstance(fecha, date):
            sin_fecha += 1
            continue

        gastos_ars = _monto_seguro(item.get('gastos_ars'))
        gastos_usd = _monto_seguro(item.get('gastos_usd'))
        if gastos_ars == 0 and gastos_usd == 0:
            omitidas += 1
            continue

        fechas_ok.append(fecha)
        descripcion = descripcion_fila_excel(item, clasificacion=clasificacion)
        tipo_cambio = _tipo_cambio_seguro(item.get('tipo_cambio'))

        existente = _match_existente(
            propiedad, fecha, gastos_ars, gastos_usd, descripcion, clasificacion
        )
        if existente:
            needs = (
                force
                or existente.clasificacion_libro != clasificacion
                or (existente.descripcion or '') != descripcion
                or existente.tipo_cambio != tipo_cambio
            )
            if needs:
                if not dry_run:
                    existente.clasificacion_libro = clasificacion
                    existente.descripcion = descripcion
                    existente.gastos_ars = gastos_ars
                    existente.gastos_usd = gastos_usd
                    existente.tipo_cambio = tipo_cambio
                    existente.save(
                        update_fields=[
                            'clasificacion_libro',
                            'descripcion',
                            'gastos_ars',
                            'gastos_usd',
                            'tipo_cambio',
                            'actualizado_en',
                        ]
                    )
                actualizadas += 1
            else:
                omitidas += 1
            continue

        if not dry_run:
            FilaManualLibroPropiedad.objects.create(
                propiedad=propiedad,
                fecha=fecha,
                descripcion=descripcion,
                gastos_ars=gastos_ars,
                gastos_usd=gastos_usd,
                alquileres_ars=Decimal('0.00'),
                ingreso_usd=Decimal('0.00'),
                tipo_cambio=tipo_cambio,
                clasificacion_libro=clasificacion,
            )
        creadas += 1

    inicio_ajustado = None
    if fechas_ok and not dry_run:
        fecha_min = min(fechas_ok)
        inicio, _ = InicioCajaLibroPropiedad.objects.get_or_create(
            propiedad=propiedad,
            defaults={
                'fecha': fecha_min,
                'gastos_ars': Decimal('0'),
                'alquileres_ars': Decimal('0'),
                'gastos_usd': Decimal('0'),
                'ingreso_usd': Decimal('0'),
            },
        )
        if inicio.fecha is None or inicio.fecha > fecha_min:
            inicio.fecha = fecha_min
            inicio.save(update_fields=['fecha', 'actualizado_en'])
            inicio_ajustado = fecha_min
        else:
            inicio_ajustado = inicio.fecha

    extras = ''
    if inicio_ajustado:
        extras = (
            f' Inicio de caja movido a {inicio_ajustado.strftime("%d/%m/%Y")} '
            f'para que se vean en el libro.'
        )

    return {
        'ok': True,
        'propiedad_id': str(propiedad.id),
        'clasificacion': clasificacion,
        'creadas': creadas,
        'actualizadas': actualizadas,
        'omitidas': omitidas,
        'sin_fecha': sin_fecha,
        'total_json': len(filas),
        'dry_run': dry_run,
        'fecha_inicio_caja': inicio_ajustado.isoformat() if inicio_ajustado else None,
        'mensaje': (
            f'Importación {label}: {creadas} creadas, {actualizadas} actualizadas, '
            f'{omitidas} omitidas, {sin_fecha} sin fecha '
            f'({len(filas)} filas en Excel).{extras}'
        ),
    }


def importar_gery_1759_facturado(**kwargs) -> dict:
    kwargs.setdefault('clasificacion', 'facturado')
    return importar_gery_1759_excel(**kwargs)


def importar_gery_1759_negro(**kwargs) -> dict:
    kwargs.setdefault('clasificacion', 'negro')
    return importar_gery_1759_excel(**kwargs)
