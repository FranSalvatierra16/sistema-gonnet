"""Convierte el Excel/Numbers de Gery 1759 a los JSON del libro."""
from __future__ import annotations

import json
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
NS_R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

MESES = {
    'ene': 1, 'enero': 1, 'jan': 1,
    'feb': 2, 'febrero': 2,
    'mar': 3, 'marzo': 3,
    'abr': 4, 'abril': 4, 'apr': 4,
    'may': 5, 'mayo': 5,
    'jun': 6, 'junio': 6,
    'jul': 7, 'julio': 7,
    'ago': 8, 'agosto': 8, 'aug': 8,
    'sep': 9, 'sept': 9, 'septiembre': 9,
    'oct': 10, 'octubre': 10,
    'nov': 11, 'noviembre': 11,
    'dic': 12, 'diciembre': 12, 'dec': 12,
}

SKIP_TEXT = re.compile(
    r'^(total|totales|saldo|saldos|fecha|comprobante|proveedor|concepto|'
    r'ingresos|gastos|pesos|dolares|dolares|u\$s)$',
    re.I,
)


def _col_row(ref: str) -> tuple[int, int]:
    col = ''.join(c for c in ref if c.isalpha())
    row = int(''.join(c for c in ref if c.isdigit()))
    n = 0
    for c in col:
        n = n * 26 + (ord(c.upper()) - 64)
    return n, row


def _num(value) -> float | None:
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(' ', '').replace('$', '')
    if not s or s in {'.', '-'}:
        return None
    s = s.replace('.', '').replace(',', '.') if s.count(',') == 1 and s.count('.') > 1 else s
    try:
        return float(s)
    except ValueError:
        return None


def _q2(value) -> float:
    n = _num(value)
    if n is None:
        return 0.0
    return float(Decimal(str(abs(n))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _serial_a_fecha(serial: float) -> date | None:
    try:
        n = int(round(serial))
    except (TypeError, ValueError):
        return None
    if n < 20000 or n > 60000:
        return None
    try:
        return date(1899, 12, 30) + timedelta(days=n)
    except OverflowError:
        return None


def _parse_fecha_celda(raw) -> str:
    """Devuelve DD/MM/YYYY, DD/MM o string vacío. No inventa año acá."""
    if raw is None:
        return ''
    if isinstance(raw, (int, float)) or (
        isinstance(raw, str) and re.fullmatch(r'\d+(\.\d+)?', raw.strip())
    ):
        n = float(raw)
        as_int = int(round(n))
        s_int = str(as_int)
        if len(s_int) == 8 and 1 <= int(s_int[:2]) <= 31 and 1 <= int(s_int[2:4]) <= 12:
            try:
                return date(int(s_int[4:]), int(s_int[2:4]), int(s_int[:2])).strftime('%d/%m/%Y')
            except ValueError:
                pass
        d = _serial_a_fecha(n)
        return d.strftime('%d/%m/%Y') if d else ''

    s = str(raw).strip()
    if not s or s in {'/', '.', '-'}:
        return ''

    s = re.sub(r'\s+', ' ', s)

    # 26/62020 → 26/06/2020 ; 2302/2026 → 23/02/2026
    m = re.fullmatch(r'(\d{1,2})/(\d)(\d{4})', s)
    if m:
        return f'{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}'
    m = re.fullmatch(r'(\d{2})(\d{2})/(\d{4})', s)
    if m and 1 <= int(m.group(1)) <= 31 and 1 <= int(m.group(2)) <= 12:
        return f'{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}'

    m = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        elif y < 1990:
            # 21/11/0204 → año inválido; se rellena después con vecinos
            return f'{d:02d}/{mo:02d}'
        try:
            return date(y, mo, d).strftime('%d/%m/%Y')
        except ValueError:
            return f'{d:02d}/{mo:02d}'

    m = re.fullmatch(r'(\d{1,2})/(\d{1,2})', s)
    if m:
        return f'{int(m.group(1)):02d}/{int(m.group(2)):02d}'

    m = re.search(
        r'(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|'
        r'octubre|noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|'
        r'sept|sep|oct|nov|dic)\s*[-.]?\s*(\d{4})',
        s,
        re.I,
    )
    if m:
        key = m.group(1).lower()
        mes = MESES.get(key) or MESES.get(key[:3])
        if mes:
            return date(int(m.group(2)), mes, 1).strftime('%d/%m/%Y')

    m = re.fullmatch(r'(20\d{2})\s*-\s*(20\d{2})', s)
    if m:
        # Temporada 2010-2011 → 15/12/2010 (antes del verano siguiente)
        return date(int(m.group(1)), 12, 15).strftime('%d/%m/%Y')

    return ''


def _es_fila_util(fecha_raw, comprobante, proveedor, concepto, montos) -> bool:
    textos = [str(x or '').strip() for x in (fecha_raw, comprobante, proveedor, concepto)]
    if all(not t or SKIP_TEXT.match(t) for t in textos) and not any(montos):
        return False
    blob = ' '.join(textos)
    if re.search(r'\bTOTAL(ES)?\b', blob, re.I) and not concepto:
        return False
    # Fila 3 del Excel: totales de la hoja, sin descripción.
    if not proveedor and not concepto and not comprobante and not fecha_raw:
        return False
    if all(m == 0 for m in montos):
        return False
    if not any(textos) and not any(montos):
        return False
    return True


def _load_shared(z: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(z.read('xl/sharedStrings.xml'))
    out = []
    for si in root.findall('m:si', NS):
        out.append(''.join(t.text or '' for t in si.findall('.//m:t', NS)))
    return out


def _load_sheet_rows(z: zipfile.ZipFile, target: str, shared: list[str]) -> dict[int, dict[int, str | None]]:
    root = ET.fromstring(z.read(target))
    rows: dict[int, dict[int, str | None]] = {}
    for c in root.findall('.//m:c', NS):
        ref = c.attrib.get('r')
        if not ref:
            continue
        col, row = _col_row(ref)
        t = c.attrib.get('t')
        v = c.find('m:v', NS)
        isel = c.find('m:is', NS)
        val = None
        if t == 's' and v is not None and v.text is not None:
            val = shared[int(v.text)]
        elif t == 'inlineStr' and isel is not None:
            val = ''.join(tt.text or '' for tt in isel.findall('.//m:t', NS))
        elif v is not None:
            val = v.text
        rows.setdefault(row, {})[col] = val
    return rows


def _sheet_target(z: zipfile.ZipFile, sheet_name: str) -> str:
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    rid_to_target = {r.attrib['Id']: r.attrib['Target'] for r in rels}
    for sh in wb.findall('m:sheets/m:sheet', NS):
        if sh.attrib.get('name') == sheet_name:
            target = rid_to_target[sh.attrib[f'{NS_R}id']]
            if not target.startswith('xl/'):
                target = 'xl/' + target.lstrip('/')
            return target
    raise KeyError(sheet_name)


def _fila_desde_cells(cells: dict) -> dict | None:
    fecha_raw = _parse_fecha_celda(cells.get(1))
    comprobante = str(cells.get(2) or '').strip()
    proveedor = str(cells.get(3) or '').strip()
    concepto = str(cells.get(4) or '').strip()
    ingresos_ars = _q2(cells.get(5))
    ingresos_usd = _q2(cells.get(6))
    gastos_ars = _q2(cells.get(7))
    gastos_usd = _q2(cells.get(8))
    tc = _num(cells.get(9))
    montos = (ingresos_ars, ingresos_usd, gastos_ars, gastos_usd)
    if not _es_fila_util(fecha_raw, comprobante, proveedor, concepto, montos):
        return None
    if SKIP_TEXT.match(concepto) or SKIP_TEXT.match(proveedor):
        if gastos_ars == 0 and gastos_usd == 0 and ingresos_ars == 0 and ingresos_usd == 0:
            return None
    return {
        'fecha_raw': fecha_raw,
        'comprobante': comprobante,
        'proveedor': proveedor,
        'concepto': concepto,
        'gastos_ars': gastos_ars,
        'gastos_usd': gastos_usd,
        'ingresos_ars': ingresos_ars,
        'ingresos_usd': ingresos_usd,
        'tipo_cambio': None if tc is None else round(tc, 4),
    }


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


def _anio_desde_texto(*textos) -> int | None:
    blob = ' '.join(t or '' for t in textos)
    m = re.search(
        r'(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre'
        r'|cuota|periodo|mes|año|ano)\s+(?:de\s+)?(\d{4})\b',
        blob,
        flags=re.I,
    )
    if m:
        y = int(m.group(1))
        if 2000 <= y <= 2100:
            return y
    m = re.search(r'\bde\s+(\d{4})\b', blob, flags=re.I)
    if m:
        y = int(m.group(1))
        if 2000 <= y <= 2100:
            return y
    return None


def _fecha_antes_de(day: int, month: int, siguiente: date) -> date | None:
    try:
        candidata = date(siguiente.year, month, day)
    except ValueError:
        return None
    if candidata > siguiente:
        try:
            candidata = date(siguiente.year - 1, month, day)
        except ValueError:
            return None
    return candidata


def _swap_md(d: date) -> date | None:
    if d.day <= 12:
        try:
            return date(d.year, d.day, d.month)
        except ValueError:
            return None
    return None


def resolver_anios_filas(filas: list[dict]) -> list[dict]:
    """
    Completa DD/MM sin año con el orden del Excel.
    18/12 antes de 10/01/2021 → 2020.
    17/02 después de 24/02/2021 y antes de 05/03/2021 → 2021 (no salta de año).
    """
    parsed = []
    for fila in filas:
        valor = _parse_fecha_raw((fila.get('fecha_raw') or '').strip())
        anio_txt = _anio_desde_texto(fila.get('concepto'), fila.get('proveedor'))
        parsed.append({**fila, '_fecha_parsed': valor, '_anio_texto': anio_txt})

    n = len(parsed)

    def _proxima_con_anio(idx: int) -> date | None:
        for j in range(idx + 1, n):
            v = parsed[j]['_fecha_parsed']
            ay = parsed[j].get('_anio_texto')
            if isinstance(v, date):
                return v
            if isinstance(v, tuple) and ay:
                try:
                    return date(ay, v[1], v[0])
                except ValueError:
                    continue
        return None

    def _completa(idx: int) -> date | None:
        v = parsed[idx]['_fecha_parsed']
        return v if isinstance(v, date) else None

    def _prev_completa(idx: int) -> date | None:
        for j in range(idx - 1, -1, -1):
            d = _completa(j)
            if d:
                return d
        return None

    def _next_completa(idx: int) -> date | None:
        for j in range(idx + 1, n):
            d = _completa(j)
            if d:
                return d
        return None

    # Fechas completas fuera de la ventana local (31/8/2019 en bloque 2018,
    # 10/1 leído como 1/10, 31/12/2026 entre dic-2025 y ene-2026).
    for i, item in enumerate(parsed):
        valor = item['_fecha_parsed']
        if not isinstance(valor, date):
            continue
        prev = _prev_completa(i)
        nxt = _next_completa(i)
        if prev is None or nxt is None:
            continue
        if (nxt - prev).days > 120:
            continue
        lo, hi = prev - timedelta(days=7), nxt + timedelta(days=7)
        if lo <= valor <= hi:
            continue
        candidatos = [valor, _swap_md(valor)]
        for anio in {prev.year, nxt.year, prev.year - 1, prev.year + 1, nxt.year - 1}:
            try:
                candidatos.append(date(anio, valor.month, valor.day))
            except ValueError:
                pass
            swapped = _swap_md(valor)
            if swapped is not None:
                try:
                    candidatos.append(date(anio, swapped.month, swapped.day))
                except ValueError:
                    pass
        mejores = [c for c in candidatos if c is not None and lo <= c <= hi]
        if not mejores:
            continue
        elegida = min(mejores, key=lambda c: abs((c - prev).days))
        if elegida != valor:
            item['_fecha_parsed'] = elegida
            item['fecha_raw'] = elegida.strftime('%d/%m/%Y')

    ultima = None
    for i, item in enumerate(parsed):
        valor = item['_fecha_parsed']
        if isinstance(valor, date):
            ultima = valor
            continue
        if not isinstance(valor, tuple):
            continue
        day, month = valor
        nueva = None
        anio_txt = item.get('_anio_texto')
        if anio_txt:
            try:
                nueva = date(anio_txt, month, day)
            except ValueError:
                nueva = None

        ref = _proxima_con_anio(i)
        if nueva is None and ref is not None:
            nueva = _fecha_antes_de(day, month, ref)
            if (
                nueva is not None
                and ultima is not None
                and (nueva - ultima).days > 180
            ):
                try:
                    alt = date(ultima.year, month, day)
                except ValueError:
                    alt = None
                if alt is not None:
                    if alt < ultima and (ultima - alt).days > 45:
                        try:
                            alt = date(ultima.year + 1, month, day)
                        except ValueError:
                            alt = None
                    nueva = alt

        if nueva is None and ultima is not None:
            try:
                misma = date(ultima.year, month, day)
            except ValueError:
                misma = None
            if misma is not None and misma < ultima and (ultima - misma).days <= 45:
                nueva = misma
            elif misma is not None and misma >= ultima:
                nueva = misma
            else:
                try:
                    nueva = date(ultima.year + 1, month, day)
                except ValueError:
                    nueva = None

        if nueva is None:
            continue
        item['_fecha_parsed'] = nueva
        item['fecha_raw'] = nueva.strftime('%d/%m/%Y')
        ultima = nueva

    proxima: date | None = None
    for i in range(n - 1, -1, -1):
        item = parsed[i]
        valor = item['_fecha_parsed']
        if isinstance(valor, date):
            proxima = valor
            continue
        if not isinstance(valor, tuple) or proxima is None:
            continue
        day, month = valor
        nueva = _fecha_antes_de(day, month, proxima)
        if nueva is None:
            continue
        item['_fecha_parsed'] = nueva
        item['fecha_raw'] = nueva.strftime('%d/%m/%Y')
        proxima = nueva

    ultima = None
    for item in parsed:
        valor = item['_fecha_parsed']
        if isinstance(valor, date):
            ultima = valor
        elif valor is None and ultima is not None:
            item['_fecha_parsed'] = ultima
            item['fecha_raw'] = ultima.strftime('%d/%m/%Y')

    for item in parsed:
        item.pop('_anio_texto', None)
        fp = item.pop('_fecha_parsed', None)
        if isinstance(fp, date):
            item['fecha_raw'] = fp.strftime('%d/%m/%Y')
    return parsed


def extraer_hoja(xlsx: Path, sheet_name: str) -> list[dict]:
    with zipfile.ZipFile(xlsx) as z:
        shared = _load_shared(z)
        target = _sheet_target(z, sheet_name)
        rows = _load_sheet_rows(z, target, shared)
    filas = []
    for r in range(1, (max(rows) if rows else 0) + 1):
        fila = _fila_desde_cells(rows.get(r, {}))
        if fila:
            filas.append(fila)
    return resolver_anios_filas(filas)


def convertir(xlsx: Path, data_dir: Path) -> dict:
    facturado = extraer_hoja(xlsx, 'GENERAL Facturado')
    negro = extraer_hoja(xlsx, 'GENERAL. Sin Facturar')
    data_dir.mkdir(parents=True, exist_ok=True)
    out_f = data_dir / 'gery_1759_facturado_excel.json'
    out_n = data_dir / 'gery_1759_negro_excel.json'
    for path, filas in ((out_f, facturado), (out_n, negro)):
        if path.exists():
            bak = path.with_suffix('.backup.json')
            bak.write_bytes(path.read_bytes())
        path.write_text(json.dumps(filas, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {
        'facturado': len(facturado),
        'negro': len(negro),
        'facturado_sin_fecha': sum(1 for f in facturado if not f.get('fecha_raw') or len(f['fecha_raw']) < 8),
        'negro_sin_fecha': sum(1 for f in negro if not f.get('fecha_raw') or len(f['fecha_raw']) < 8),
        'facturado_ingresos': sum(1 for f in facturado if f.get('ingresos_ars') or f.get('ingresos_usd')),
        'negro_ingresos': sum(1 for f in negro if f.get('ingresos_ars') or f.get('ingresos_usd')),
    }


if __name__ == '__main__':
    base = Path(__file__).resolve().parent
    xlsx = base / 'data' / 'excel_fuente' / 'sinfacturar.xlsx'
    stats = convertir(xlsx, base / 'data')
    print(json.dumps(stats, indent=2))
