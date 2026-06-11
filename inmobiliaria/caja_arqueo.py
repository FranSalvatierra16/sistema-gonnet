"""Helpers compartidos para arqueo de caja (apertura, cierre, reparación)."""
from decimal import Decimal

from django.db import transaction

from inmobiliaria.models.caja import Caja, CajaArqueoCierre, CajaArqueoManual


def deposito_total_desde_arqueo_dict(data):
    total = Decimal('0')
    for val in (data.get('cuentas_json') or {}).values():
        total += Decimal(str(val or 0))
    total += Decimal(str(data.get('deposito_galicia') or 0))
    total += Decimal(str(data.get('deposito_mp') or 0))
    return total


def total_ars_desde_arqueo_dict(data):
    total = Decimal('0')
    for key in ('efectivo', 'cheque', 'tarjeta'):
        total += Decimal(str(data.get(key) or 0))
    for val in (data.get('cuentas_json') or {}).values():
        total += Decimal(str(val or 0))
    total += Decimal(str(data.get('deposito_galicia') or 0))
    total += Decimal(str(data.get('deposito_mp') or 0))
    return total


def arqueo_dict_desde_registro(arqueo):
    cuentas_json = arqueo.cuentas_json or {}
    if isinstance(cuentas_json, dict):
        cuentas_json = {str(k): str(v) for k, v in cuentas_json.items()}
    else:
        cuentas_json = {}
    return {
        'efectivo': Decimal(str(getattr(arqueo, 'efectivo', None) or 0)),
        'cheque': Decimal(str(getattr(arqueo, 'cheque', None) or 0)),
        'tarjeta': Decimal(str(getattr(arqueo, 'tarjeta', None) or 0)),
        'dolares': Decimal(str(getattr(arqueo, 'dolares', None) or 0)),
        'cuentas_json': cuentas_json,
        'deposito_galicia': Decimal(str(getattr(arqueo, 'deposito_galicia', None) or 0)),
        'deposito_mp': Decimal(str(getattr(arqueo, 'deposito_mp', None) or 0)),
    }


def anteriores_json_desde_apertura(saldos_dict):
    dep = deposito_total_desde_arqueo_dict(saldos_dict)
    return {
        'efectivo': str(saldos_dict.get('efectivo') or 0),
        'cheque': str(saldos_dict.get('cheque') or 0),
        'tarjeta': str(saldos_dict.get('tarjeta') or 0),
        'deposito': str(dep),
        'usd': str(saldos_dict.get('dolares') or 0),
    }


def apertura_dict_desde_caja_cerrada(caja_cerrada):
    """Saldos de apertura = arqueo de cierre registrado o saldo final de la caja."""
    arqueo = CajaArqueoCierre.objects.filter(caja=caja_cerrada).first()
    if arqueo:
        return arqueo_dict_desde_registro(arqueo)
    return {
        'efectivo': Decimal(str(caja_cerrada.saldo_final or caja_cerrada.saldo_inicial or 0)),
        'cheque': Decimal('0'),
        'tarjeta': Decimal('0'),
        'dolares': Decimal('0'),
        'cuentas_json': {},
        'deposito_galicia': Decimal('0'),
        'deposito_mp': Decimal('0'),
    }


@transaction.atomic
def aplicar_apertura_a_caja_abierta(caja_abierta, apertura_dict, usuario, *, nota=None):
    """
    Deja la caja abierta con los saldos por medio de una apertura (p. ej. cierre previo).
    Ajusta saldo_inicial (efectivo) y reemplaza el arqueo manual de apertura.
    """
    if caja_abierta.estado != 'abierta':
        raise ValueError(f'La caja #{caja_abierta.numero} no está abierta.')

    cuentas_json = apertura_dict.get('cuentas_json') or {}
    if isinstance(cuentas_json, dict):
        cuentas_json = {str(k): str(v) for k, v in cuentas_json.items()}
    else:
        cuentas_json = {}

    efectivo = Decimal(str(apertura_dict.get('efectivo') or 0))
    caja_abierta.saldo_inicial = efectivo
    if nota:
        prev = (caja_abierta.observaciones_apertura or '').strip()
        caja_abierta.observaciones_apertura = f'{prev}\n{nota}'.strip() if prev else nota
        caja_abierta.save(update_fields=['saldo_inicial', 'observaciones_apertura'])
    else:
        caja_abierta.save(update_fields=['saldo_inicial'])

    CajaArqueoManual.objects.filter(caja=caja_abierta).delete()
    arqueo = CajaArqueoManual.objects.create(
        caja=caja_abierta,
        efectivo=efectivo,
        cheque=Decimal(str(apertura_dict.get('cheque') or 0)),
        tarjeta=Decimal(str(apertura_dict.get('tarjeta') or 0)),
        dolares=Decimal(str(apertura_dict.get('dolares') or 0)),
        deposito_galicia=Decimal(str(apertura_dict.get('deposito_galicia') or 0)),
        deposito_mp=Decimal(str(apertura_dict.get('deposito_mp') or 0)),
        cuentas_json=cuentas_json,
        anteriores_json=anteriores_json_desde_apertura(apertura_dict),
        registrado_por=usuario,
    )
    return caja_abierta, arqueo, total_ars_desde_arqueo_dict(apertura_dict)


@transaction.atomic
def reparar_apertura_desde_caja_anterior(sucursal, numero_origen, numero_destino, usuario):
    """Copia saldos del cierre de `numero_origen` a la caja abierta `numero_destino`."""
    caja_origen = Caja.objects.get(numero=numero_origen, sucursal=sucursal)
    caja_destino = Caja.objects.get(numero=numero_destino, sucursal=sucursal)
    if caja_origen.estado != 'cerrada':
        raise ValueError(f'La caja origen #{numero_origen} debe estar cerrada.')
    if caja_destino.estado != 'abierta':
        raise ValueError(f'La caja destino #{numero_destino} debe estar abierta.')

    from inmobiliaria.decimal_utils import format_monto_argentino

    apertura = apertura_dict_desde_caja_cerrada(caja_origen)
    total_txt = format_monto_argentino(total_ars_desde_arqueo_dict(apertura))
    nota = (
        f'[Reparación] Apertura corregida desde arqueo de cierre de Caja #{numero_origen} '
        f'(total ARS ${total_txt}).'
    )
    caja, arqueo, total = aplicar_apertura_a_caja_abierta(
        caja_destino, apertura, usuario, nota=nota
    )
    return caja, arqueo, apertura, total
