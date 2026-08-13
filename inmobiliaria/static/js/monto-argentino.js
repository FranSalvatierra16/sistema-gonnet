/**
 * Formato argentino en tiempo real: miles con punto al escribir (10.000), decimales con coma.
 * Se aplica automáticamente a inputs de montos en todo el sistema (base.html).
 */
(function (global) {
    if (global.__montoARInit) {
        return;
    }
    global.__montoARInit = true;

    var MONEY_ATTR_RE = /(monto|importe|precio|honorario|comision|cochera|fondo|saldo|ajuste|tarifa|alquiler|deposito|dolares|participacion|proporcional|sellado|ganancia|arqueo|senia|locacion|expensa|venta|valor|pago|cobro|asegurado|refuerzo|precio_mes)/i;

    var EXCLUDE_ATTR_RE = /(carpeta|cuit|dni|telefono|celular|codigo_postal|vendedor_id|duracion_meses|duracion|ambientes|habitaciones|banos|prefijo_recibo|ultimo_numero|numero_recibo|numero_movimiento|numero_liquidacion|numero_cheque|numero_tarjeta|page\b|operacion\b|propiedad_id|cliente_id|inquilino_id|metros_cuadrados|porcentaje|nro_cheque|id_nuevo|concepto_id|idNuevoConcepto)/i;

    function parseMontoAR(str) {
        if (str === null || str === undefined) return 0;
        var t = String(str).trim();
        if (!t) return 0;
        t = t.replace(/[^\d.,-]/g, '');
        var neg = t.charAt(0) === '-';
        if (neg) t = t.slice(1);
        if (!t) return 0;

        if (t.indexOf(',') >= 0) {
            if (t.indexOf('.') >= 0) {
                t = t.replace(/\./g, '').replace(',', '.');
            } else {
                var parts = t.split(',');
                var last = parts[parts.length - 1];
                if (last.length <= 2) {
                    t = parts.slice(0, -1).join('') + '.' + last;
                } else if (last.length === 3 && parts.length === 2 && parts[0] === '0') {
                    t = parts[0] + '.' + last;
                } else {
                    t = parts.join('');
                }
            }
        } else if (t.indexOf('.') >= 0) {
            var segs = t.split('.');
            if (!(segs.length === 2 && segs[1].length <= 2)) {
                t = t.replace(/\./g, '');
            }
        }

        var n = parseFloat((neg ? '-' : '') + t);
        return isNaN(n) ? 0 : n;
    }

    function formatEnteroConPuntos(n) {
        var neg = n < 0;
        var s = String(Math.abs(parseInt(n, 10) || 0));
        var out = '';
        for (var i = 0; i < s.length; i++) {
            if (i > 0 && (s.length - i) % 3 === 0) {
                out += '.';
            }
            out += s.charAt(i);
        }
        return (neg ? '-' : '') + out;
    }

    function formatMontoAR(num, dec) {
        dec = dec === undefined ? 2 : Math.max(0, dec);
        var n = typeof num === 'number' ? num : parseMontoAR(num);
        if (dec === 0) {
            return formatEnteroConPuntos(Math.round(n));
        }
        var ent = Math.trunc(Math.abs(n));
        var frac = Math.round((Math.abs(n) - ent) * Math.pow(10, dec));
        if (frac >= Math.pow(10, dec)) {
            ent += 1;
            frac = 0;
        }
        var fracStr = String(frac);
        while (fracStr.length < dec) {
            fracStr = '0' + fracStr;
        }
        var sign = n < 0 ? '-' : '';
        return sign + formatEnteroConPuntos(ent) + ',' + fracStr;
    }

    function formatMontoARTyping(str) {
        if (str === null || str === undefined) return '';
        var raw = String(str);
        var neg = raw.trim().charAt(0) === '-';
        var t = raw.replace(/[^\d,]/g, '');
        if (!t) return neg ? '-' : '';

        if (t.indexOf(',') >= 0) {
            var parts = t.split(',');
            var intDigits = (parts[0] || '').replace(/\D/g, '');
            var decRaw = parts.slice(1).join('').replace(/\D/g, '').slice(0, 2);
            var intN = parseInt(intDigits || '0', 10);
            var formatted = formatEnteroConPuntos(intN);
            if (t.endsWith(',') && !decRaw) {
                return (neg ? '-' : '') + formatted + ',';
            }
            return (neg ? '-' : '') + formatted + ',' + decRaw;
        }

        var digits = t.replace(/\D/g, '');
        if (!digits) return neg ? '-' : '';
        return (neg ? '-' : '') + formatEnteroConPuntos(parseInt(digits, 10));
    }

    function esInputMonto(el) {
        if (!el || el.tagName !== 'INPUT') return false;
        if (el.dataset.noMontoAr === '1' || el.classList.contains('no-monto-ar')) return false;
        if (el.dataset.montoAr === '1') return true;

        var type = (el.type || 'text').toLowerCase();
        if (
            type === 'hidden' || type === 'checkbox' || type === 'radio' || type === 'file'
            || type === 'date' || type === 'email' || type === 'password' || type === 'search'
            || type === 'time' || type === 'datetime-local' || type === 'month' || type === 'week'
        ) {
            return false;
        }

        // Clases de monto: tienen prioridad (no las excluye el regex de name/id).
        if (
            el.classList.contains('input-monto-ar')
            || el.classList.contains('monto')
            || el.classList.contains('importe-pago')
            || el.classList.contains('mes-precio-input')
            || el.classList.contains('input-precio-cuota-mes')
            || el.classList.contains('caratula-input-edit')
            || el.classList.contains('monto-edit')
        ) {
            return true;
        }

        var name = el.name || '';
        var id = el.id || '';
        if (EXCLUDE_ATTR_RE.test(name) || EXCLUDE_ATTR_RE.test(id)) {
            return false;
        }

        if (!(type === 'text' || type === 'tel' || type === 'number' || type === '')) {
            return false;
        }

        var im = (el.getAttribute('inputmode') || '').toLowerCase();
        if (im === 'decimal' || im === 'numeric') {
            return true;
        }

        if (MONEY_ATTR_RE.test(name) || MONEY_ATTR_RE.test(id)) {
            return true;
        }

        if (type === 'number' && (el.step === '0.01' || el.step === 'any' || el.getAttribute('step') === '0.01')) {
            return true;
        }

        return false;
    }

    function prepararInputMonto(el) {
        if (!esInputMonto(el)) return;
        if (!el.classList.contains('input-monto-ar')) {
            el.classList.add('input-monto-ar');
        }
        var type = (el.type || 'text').toLowerCase();
        if (type === 'number') {
            el.type = 'text';
            if (!el.getAttribute('inputmode')) {
                el.setAttribute('inputmode', 'decimal');
            }
            if (!el.getAttribute('autocomplete')) {
                el.setAttribute('autocomplete', 'off');
            }
        }
    }

    function posicionCursorTrasFormato(oldVal, newVal, selStart) {
        if (typeof selStart !== 'number') return newVal.length;
        var digitsBefore = String(oldVal || '').slice(0, selStart).replace(/[^\d]/g, '').length;
        if (digitsBefore <= 0) return 0;
        var digitCount = 0;
        for (var i = 0; i < newVal.length; i++) {
            if (/\d/.test(newVal.charAt(i))) {
                digitCount++;
                if (digitCount >= digitsBefore) {
                    return i + 1;
                }
            }
        }
        return newVal.length;
    }

    function aplicarFormatoTyping(el) {
        if (!el || !esInputMonto(el) || el.readOnly || el.disabled) return;
        prepararInputMonto(el);
        var selStart = el.selectionStart;
        var oldVal = el.value;
        var nuevo = formatMontoARTyping(oldVal);
        if (nuevo === oldVal) return;
        el.value = nuevo;
        try {
            var pos = posicionCursorTrasFormato(oldVal, nuevo, selStart);
            el.setSelectionRange(pos, pos);
        } catch (e) { /* readonly, etc. */ }
    }

    function limpiarCeroAlEnfocar(el) {
        if (!el) return;
        var t = String(el.value || '').trim();
        if (!t || t === '0' || t === '0,00' || t === '0.00' || t === '0,0' || t === '0,') {
            el.value = '';
        } else if (parseMontoAR(t) === 0) {
            el.value = '';
        }
    }

    function formatearValorInicial(el) {
        if (!el || !esInputMonto(el)) return;
        prepararInputMonto(el);
        if (el.readOnly || el.disabled) return;
        var raw = String(el.value || '').trim();
        if (!raw) return;
        if (parseMontoAR(raw) !== 0 || raw === '0' || raw === '0,00' || raw === '0.00') {
            el.value = formatMontoAR(raw);
        }
    }

    function initMontoARInputs(root) {
        root = root || document;
        var nodes = root.querySelectorAll ? root.querySelectorAll('input') : [];
        nodes.forEach(function (el) {
            formatearValorInicial(el);
        });
    }

    document.addEventListener('input', function (e) {
        if (esInputMonto(e.target)) {
            aplicarFormatoTyping(e.target);
        }
    }, true);

    document.addEventListener('paste', function (e) {
        if (esInputMonto(e.target)) {
            setTimeout(function () {
                aplicarFormatoTyping(e.target);
            }, 0);
        }
    }, true);

    document.addEventListener('focusin', function (e) {
        if (esInputMonto(e.target)) {
            prepararInputMonto(e.target);
            limpiarCeroAlEnfocar(e.target);
        }
    }, true);

    document.addEventListener('blur', function (e) {
        if (esInputMonto(e.target) && String(e.target.value || '').trim() !== '') {
            e.target.value = formatMontoAR(e.target.value);
        }
    }, true);

    global.parseMontoAR = parseMontoAR;
    global.formatMontoAR = formatMontoAR;
    global.formatMontoARTyping = formatMontoARTyping;
    global.initMontoARInputs = initMontoARInputs;
    global.aplicarFormatoMontoAR = aplicarFormatoTyping;
    global.esInputMontoAR = esInputMonto;

    function boot() {
        initMontoARInputs();
        if (typeof MutationObserver !== 'undefined' && document.body) {
            var obs = new MutationObserver(function (mutations) {
                mutations.forEach(function (m) {
                    m.addedNodes.forEach(function (node) {
                        if (!node || node.nodeType !== 1) return;
                        if (node.tagName === 'INPUT') {
                            formatearValorInicial(node);
                        }
                        initMontoARInputs(node);
                    });
                });
            });
            obs.observe(document.body, { childList: true, subtree: true });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})(window);
