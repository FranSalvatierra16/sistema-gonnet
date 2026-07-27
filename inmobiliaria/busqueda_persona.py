"""Filtros reutilizables para buscar propietarios, inquilinos y personas por nombre/apellido."""
from django.db.models import Case, IntegerField, Q, Value, When


def partes_termino_busqueda_persona(termino):
    """Parte el término ignorando comas (formato «Apellido, Nombre»)."""
    termino = (termino or '').strip()
    if not termino:
        return []
    normalizado = termino.replace(',', ' ')
    return [p for p in normalizado.split() if p]


def q_busqueda_persona(termino, *, incluir_id=True, prefix=''):
    """Q para nombre, apellido, DNI e ID; soporta «G, G» y apellidos de una letra."""

    def campo(nombre):
        return f'{prefix}{nombre}' if prefix else nombre

    termino = (termino or '').strip()
    if not termino:
        return Q()

    q = (
        Q(**{f'{campo("nombre")}__icontains': termino})
        | Q(**{f'{campo("apellido")}__icontains': termino})
        | Q(**{f'{campo("dni")}__icontains': termino})
    )
    if incluir_id and not prefix:
        try:
            q |= Q(id=int(termino))
        except (TypeError, ValueError):
            pass

    partes = partes_termino_busqueda_persona(termino)
    if len(partes) == 1:
        p = partes[0]
        q |= (
            Q(**{f'{campo("nombre")}__icontains': p})
            | Q(**{f'{campo("apellido")}__icontains': p})
        )
    elif len(partes) >= 2:
        # Coincidencia apellido + nombre (y al revés).
        q |= (
            Q(**{f'{campo("apellido")}__icontains': partes[0]})
            & Q(**{f'{campo("nombre")}__icontains': partes[1]})
        )
        if len(partes) == 2:
            q |= (
                Q(**{f'{campo("apellido")}__icontains': partes[1]})
                & Q(**{f'{campo("nombre")}__icontains': partes[0]})
            )
        # "todas las partes en algún campo" solo con tokens ≥ 3 chars
        # (evita falsos positivos tipo "DI lo" → Capelo / Claudia).
        if all(len(p) >= 3 for p in partes):
            q_todas = Q()
            for parte in partes:
                q_todas &= (
                    Q(**{f'{campo("nombre")}__icontains': parte})
                    | Q(**{f'{campo("apellido")}__icontains': parte})
                )
            q |= q_todas
        else:
            # Tokens cortos: todas las partes deben aparecer en el mismo campo
            # (ej. nombre "Di Lorenzo" con "DI lo").
            q_nombre = Q()
            q_apellido = Q()
            for parte in partes:
                q_nombre &= Q(**{f'{campo("nombre")}__icontains': parte})
                q_apellido &= Q(**{f'{campo("apellido")}__icontains': parte})
            q |= q_nombre | q_apellido

    return q


def ordenar_queryset_persona_por_termino(
    qs, termino, apellido_field='apellido', nombre_field='nombre'
):
    """Prioriza coincidencias exactas (útil con nombres de una sola letra)."""
    termino = (termino or '').strip()
    if not termino:
        return qs.order_by(apellido_field, nombre_field)

    partes = partes_termino_busqueda_persona(termino)
    prim = partes[0] if partes else termino

    return qs.annotate(
        _rank_busqueda=Case(
            When(**{f'{apellido_field}__iexact': prim}, then=Value(0)),
            When(**{f'{nombre_field}__iexact': prim}, then=Value(1)),
            When(**{f'{apellido_field}__istartswith': prim}, then=Value(2)),
            When(**{f'{nombre_field}__istartswith': prim}, then=Value(3)),
            When(**{f'{apellido_field}__icontains': prim}, then=Value(4)),
            When(**{f'{nombre_field}__icontains': prim}, then=Value(5)),
            default=Value(10),
            output_field=IntegerField(),
        )
    ).order_by('_rank_busqueda', apellido_field, nombre_field)
