/**
 * Formato argentino para inputs de montos: miles con punto, decimales con coma.
 */
(function (global) {
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

    function formatMontoAR(num, dec) {
        dec = dec === undefined ? 2 : Math.max(0, dec);
        var n = typeof num === 'number' ? num : parseMontoAR(num);
        if (dec === 0) {
            return Math.round(n).toLocaleString('es-AR', { maximumFractionDigits: 0 });
        }
        return n.toLocaleString('es-AR', { minimumFractionDigits: dec, maximumFractionDigits: dec });
    }

    /** Formato mientras se escribe: miles con punto (70.000), decimales opcionales con coma. */
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
            var formatted = intN.toLocaleString('es-AR', { maximumFractionDigits: 0 });
            if (t.endsWith(',') && !decRaw) {
                return (neg ? '-' : '') + formatted + ',';
            }
            return (neg ? '-' : '') + formatted + ',' + decRaw;
        }

        var digits = t.replace(/\D/g, '');
        if (!digits) return neg ? '-' : '';
        var n = parseInt(digits, 10);
        return (neg ? '-' : '') + n.toLocaleString('es-AR', { maximumFractionDigits: 0 });
    }

    function initMontoARInputs(root) {
        root = root || document;
        root.querySelectorAll('input.input-monto-ar').forEach(function (el) {
            if (el.dataset.montoArInit) return;
            el.dataset.montoArInit = '1';
            if (el.value && el.value.trim() !== '') {
                el.value = formatMontoAR(el.value);
            }
            el.addEventListener('input', function () {
                var pos = el.selectionStart;
                var oldLen = (el.value || '').length;
                el.value = formatMontoARTyping(el.value);
                var newLen = (el.value || '').length;
                if (typeof pos === 'number') {
                    var newPos = Math.max(0, pos + (newLen - oldLen));
                    try {
                        el.setSelectionRange(newPos, newPos);
                    } catch (e) { /* input no soporta selección */ }
                }
            });
            el.addEventListener('blur', function () {
                if (el.value.trim() !== '') {
                    el.value = formatMontoAR(el.value);
                }
            });
            el.addEventListener('focus', function () {
                el.select();
            });
        });
    }

    global.parseMontoAR = parseMontoAR;
    global.formatMontoAR = formatMontoAR;
    global.formatMontoARTyping = formatMontoARTyping;
    global.initMontoARInputs = initMontoARInputs;

    document.addEventListener('DOMContentLoaded', function () {
        initMontoARInputs();
    });
})(window);
