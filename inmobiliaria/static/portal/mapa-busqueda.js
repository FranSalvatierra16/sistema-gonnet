(function () {
  var MDP = { lat: -38.0038, lng: -57.5486 };
  var MDP_BOX = { south: -38.12, north: -37.93, west: -57.64, east: -57.534 };
  var MDP_BOUNDS = {
    south: MDP_BOX.south,
    west: MDP_BOX.west,
    north: MDP_BOX.north,
    east: MDP_BOX.east
  };

  // Intersecciones / calles de MdP con punto aproximado (solo fallback).
  // Clave: "calle1|calle2" ordenada alfabéticamente.
  var ESQUINAS = {
    'belgrano|corrientes': [-38.0038, -57.5488],
    'corrientes|gascon': [-38.0085, -57.5420],
    'corrientes|gascón': [-38.0085, -57.5420],
    'corrientes|moreno': [-38.0048, -57.5490],
    '3 de febrero|mitre': [-38.0015, -57.5428],
    'mitre|3 de febrero': [-38.0015, -57.5428],
    'gascon|la costa': [-38.0120, -57.5355],
    'gascón|la costa': [-38.0120, -57.5355],
    'moreno|santa fe': [-38.0058, -57.5485],
    'colon|santa fe': [-38.0040, -57.5475],
    'colón|santa fe': [-38.0040, -57.5475],
    'luro|san martin': [-38.0035, -57.5495],
    'luro|san martín': [-38.0035, -57.5495]
  };

  var CALLES = [
    ['almirante brown', -38.0070, -57.5490],
    ['hipolito yrigoyen', -38.0030, -57.5478],
    ['hipólito yrigoyen', -38.0030, -57.5478],
    ['3 de febrero', -38.0018, -57.5435],
    ['la costa', -38.0125, -57.5348],
    ['santa fe', -38.0062, -57.5488],
    ['corrientes', -38.0036, -57.5494],
    ['rivadavia', -38.0026, -57.5496],
    ['belgrano', -38.0042, -57.5482],
    ['independencia', -38.0048, -57.5475],
    ['san martin', -38.0032, -57.5488],
    ['san martín', -38.0032, -57.5488],
    ['pueyrredon', -38.0008, -57.5555],
    ['pueyrredón', -38.0008, -57.5555],
    ['gascon', -38.0118, -57.5388],
    ['gascón', -38.0118, -57.5388],
    ['guemes', -38.0080, -57.5405],
    ['güemes', -38.0080, -57.5405],
    ['sarmiento', -38.0055, -57.5502],
    ['moreno', -38.0056, -57.5490],
    ['colon', -38.0018, -57.5480],
    ['colón', -38.0018, -57.5480],
    ['mitre', -38.0020, -57.5445],
    ['luro', -38.0038, -57.5502],
    ['alem', -37.9935, -57.5510]
  ];

  function fold(s) {
    return String(s || '').toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9ñ\s]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  /** Limpia y arma una dirección geocodable: «Corrientes al 2200» → «Corrientes 2200». */
  function normalizarDireccion(raw) {
    var t = String(raw || '');
    // Quitar piso/depto del final
    t = t.replace(/\s*[-–—]\s*piso\s+\S+.*/i, '');
    t = t.replace(/\s*[-–—]\s*dpto\.?\s+\S+.*/i, '');
    t = t.replace(/\s*piso\s+\S+/ig, '');
    t = t.replace(/\s*(dpto|depto|departamento)\.?\s+\S+/ig, '');
    // «al 2200» / «n° 2200» / «nro 2200»
    t = t.replace(/\b(?:al|n[°ºo.]?|nro\.?|num\.?|numero)\s*(\d{2,5})\b/ig, ' $1 ');
    // «X y Y» / «X e Y» → esquina
    t = t.replace(/\s+y\s+/ig, ' y ');
    t = t.replace(/\s+e\s+/ig, ' y ');
    t = t.replace(/\s+/g, ' ').trim();
    return t;
  }

  function parseDireccion(texto) {
    var limpio = normalizarDireccion(texto);
    var f = fold(limpio);
    var mNum = f.match(/\b(\d{2,5})\b/);
    var numero = mNum ? mNum[1] : '';
    var esquina = null;
    var mEsq = f.match(/^(.+?)\s+y\s+(.+)$/);
    if (mEsq && !numero) {
      esquina = [mEsq[1].trim(), mEsq[2].trim()];
    }
    var calle = '';
    if (esquina) {
      calle = esquina[0];
    } else if (numero) {
      calle = f.replace(numero, ' ').replace(/\s+/g, ' ').trim();
    } else {
      calle = f;
    }
    // Preferir nombre de calle conocido contenido en el texto
    var calleConocida = '';
    var largo = 0;
    CALLES.forEach(function (c) {
      var n = fold(c[0]);
      if ((' ' + f + ' ').indexOf(' ' + n + ' ') !== -1 && n.length >= largo) {
        largo = n.length;
        calleConocida = n;
      }
    });
    if (calleConocida) calle = calleConocida;
    return {
      original: limpio,
      fold: f,
      calle: calle,
      numero: numero,
      esquina: esquina
    };
  }

  function queryGeocode(parsed) {
    var partes = [];
    if (parsed.esquina) {
      partes.push(parsed.esquina[0] + ' y ' + parsed.esquina[1]);
      partes.push('esquina');
    } else if (parsed.calle && parsed.numero) {
      partes.push(parsed.calle + ' ' + parsed.numero);
    } else if (parsed.original) {
      partes.push(parsed.original);
    }
    partes.push('Mar del Plata');
    partes.push('Buenos Aires');
    partes.push('Argentina');
    return partes.filter(Boolean).join(', ');
  }

  function fallbackPos(parsed) {
    if (parsed.esquina) {
      var a = fold(parsed.esquina[0]);
      var b = fold(parsed.esquina[1]);
      var key = [a, b].sort().join('|');
      if (ESQUINAS[key]) {
        return { lat: ESQUINAS[key][0], lng: ESQUINAS[key][1] };
      }
      // Centro entre las dos calles si las conocemos
      var p1 = null;
      var p2 = null;
      CALLES.forEach(function (c) {
        var n = fold(c[0]);
        if (n === a || a.indexOf(n) !== -1 || n.indexOf(a) !== -1) p1 = c;
        if (n === b || b.indexOf(n) !== -1 || n.indexOf(b) !== -1) p2 = c;
      });
      if (p1 && p2) {
        return { lat: (p1[1] + p2[1]) / 2, lng: (p1[2] + p2[2]) / 2 };
      }
    }
    if (parsed.calle) {
      for (var i = 0; i < CALLES.length; i++) {
        var c = CALLES[i];
        var n = fold(c[0]);
        if (n === parsed.calle || parsed.calle.indexOf(n) !== -1) {
          // Con número: desplazar un poco a lo largo de la calle (aprox.)
          var lat = c[1];
          var lng = c[2];
          if (parsed.numero) {
            var nro = parseInt(parsed.numero, 10) || 0;
            // En MdP, números ~100 ≈ 1 cuadra (~0.001°). Anclar relativo a 2000.
            var delta = ((nro - 2000) / 100) * 0.0009;
            lng = lng + Math.max(-0.012, Math.min(0.012, delta * 0.15));
            lat = lat + Math.max(-0.02, Math.min(0.02, delta));
          }
          return { lat: lat, lng: lng };
        }
      }
    }
    return null;
  }

  function resultadoCoincide(result, parsed) {
    var txt = fold(result.formatted_address || '');
    (result.address_components || []).forEach(function (c) {
      txt += ' ' + fold(c.long_name || '') + ' ' + fold(c.short_name || '');
    });
    if (txt.indexOf('mar del plata') === -1 && txt.indexOf('mardelplata') === -1) {
      return false;
    }
    if (parsed.calle) {
      var calle = fold(parsed.calle);
      // Exigir que la calle pedida aparezca en el resultado
      if (txt.indexOf(calle) === -1) {
        // Permitir variantes cortas (luro ⊆ pedro luro)
        var ok = false;
        calle.split(' ').forEach(function (tok) {
          if (tok.length >= 4 && txt.indexOf(tok) !== -1) ok = true;
        });
        if (!ok) return false;
      }
    }
    if (parsed.numero) {
      // Preferir resultados que traen el número; no rechazar si Google omite altura
      return true;
    }
    if (parsed.esquina) {
      var e0 = fold(parsed.esquina[0]).split(' ').pop();
      var e1 = fold(parsed.esquina[1]).split(' ').pop();
      if (e0.length >= 4 && txt.indexOf(e0) === -1) return false;
      if (e1.length >= 4 && txt.indexOf(e1) === -1) return false;
    }
    return true;
  }

  function mejorTextoDireccion(direccion, ubicacion) {
    var d = normalizarDireccion(direccion);
    var u = normalizarDireccion(ubicacion);
    var pd = parseDireccion(d);
    var pu = parseDireccion(u);
    // Preferir el que tenga número de calle
    if (pd.numero && !pu.numero) return d;
    if (pu.numero && !pd.numero) return u;
    // Preferir el más específico (más largo / con esquina)
    if (pd.esquina && !pu.esquina) return d;
    if (pu.esquina && !pd.esquina) return u;
    if (d && u && d !== u) {
      // Si dirección es genérica y ubicación es esquina, usar ubicación
      if (!pd.numero && pu.esquina) return u;
      return d || u;
    }
    return d || u;
  }

  function markersFromCards() {
    return Array.prototype.map.call(document.querySelectorAll('.card[data-ficha]'), function (card) {
      var direccion = card.getAttribute('data-direccion') || '';
      var ubicacion = card.getAttribute('data-ubicacion') || '';
      var texto = mejorTextoDireccion(direccion, ubicacion);
      var parsed = parseDireccion(texto);
      return {
        id: card.getAttribute('data-ficha'),
        titulo: card.getAttribute('data-titulo') || '',
        ubicacion: ubicacion,
        direccion: direccion,
        textoMapa: texto,
        parsed: parsed,
        query: queryGeocode(parsed),
        lat: card.getAttribute('data-lat'),
        lng: card.getAttribute('data-lng'),
        precio: card.getAttribute('data-precio') || 'Consultar',
        url: card.getAttribute('href'),
        foto: card.getAttribute('data-foto') || ''
      };
    });
  }

  var markers = markersFromCards();
  if (!markers.length) {
    try {
      var el = document.getElementById('portal-markers');
      if (el && el.textContent) {
        markers = (JSON.parse(el.textContent) || []).map(function (m) {
          var texto = mejorTextoDireccion(m.direccion || '', m.ubicacion || m.query || '');
          var parsed = parseDireccion(texto);
          m.textoMapa = texto;
          m.parsed = parsed;
          m.query = queryGeocode(parsed);
          return m;
        });
      }
    } catch (e) {
      markers = [];
    }
  }

  var canvas = document.getElementById('portal-map');
  if (!canvas) return;

  function esc(s) {
    return String(s || '').replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]);
    });
  }
  function iwHtml(m) {
    var img = m.foto ? '<img src="' + esc(m.foto) + '" alt="">' : '';
    var donde = m.textoMapa || m.direccion || m.ubicacion;
    return '<div class="portal-iw">' + img +
      '<strong>' + esc(m.titulo) + '</strong>' +
      '<div style="font-size:0.78rem;color:#5d6b5c;margin:0.15rem 0">' + esc(donde) + '</div>' +
      '<div class="p">' + esc(m.precio) + '</div>' +
      '<a href="' + esc(m.url) + '">Ver ficha →</a></div>';
  }
  function highlight(id) {
    document.querySelectorAll('.card.is-map-active').forEach(function (c) { c.classList.remove('is-map-active'); });
    var card = document.getElementById('card-' + id);
    if (card) {
      card.classList.add('is-map-active');
      card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }
  function enTierra(lat, lng) {
    return Number.isFinite(lat) && Number.isFinite(lng) &&
      lat <= MDP_BOX.north && lat >= MDP_BOX.south &&
      lng >= MDP_BOX.west && lng <= MDP_BOX.east;
  }
  function hasSavedPos(m) {
    return enTierra(Number(m.lat), Number(m.lng));
  }
  /** Jitter mínimo solo para no tapar deptos del mismo edificio. */
  function jitterTiny(id, lat, lng) {
    var h = 0;
    var s = String(id || '');
    for (var i = 0; i < s.length; i++) h = (h * 33 + s.charCodeAt(i)) % 97;
    return {
      lat: lat + ((h % 3) - 1) * 0.00004,
      lng: lng + ((Math.floor(h / 3) % 3) - 1) * 0.00004
    };
  }
  function posicionInicial(m) {
    if (hasSavedPos(m)) return jitterTiny(m.id, Number(m.lat), Number(m.lng));
    var fb = fallbackPos(m.parsed || parseDireccion(m.textoMapa || m.direccion || m.ubicacion || ''));
    if (fb && enTierra(fb.lat, fb.lng)) return jitterTiny(m.id, fb.lat, fb.lng);
    return null;
  }

  function pintarLeaflet() {
    if (!window.L) return;
    var map = L.map(canvas).setView([MDP.lat, MDP.lng], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap'
    }).addTo(map);
    var group = [];
    markers.forEach(function (m) {
      var p = posicionInicial(m);
      if (!p) return;
      var mk = L.marker([p.lat, p.lng]).addTo(map);
      mk.bindPopup(iwHtml(m));
      mk.on('click', function () { highlight(m.id); });
      group.push(mk);
    });
    if (group.length) {
      map.fitBounds(L.featureGroup(group).getBounds().pad(0.18));
    }
  }

  window.initPortalLeaflet = pintarLeaflet;

  window.initPortalMap = function () {
    if (!window.google || !google.maps) return;
    var map = new google.maps.Map(canvas, {
      center: MDP,
      zoom: 13,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: true,
      restriction: {
        latLngBounds: MDP_BOUNDS,
        strictBounds: false
      }
    });
    var bounds = new google.maps.LatLngBounds();
    var info = new google.maps.InfoWindow();
    var placed = 0;
    var hint = document.querySelector('#portal-map-panel .map-count');
    var gMarkers = {};
    var mdpBias = new google.maps.LatLngBounds(
      { lat: MDP_BOX.south, lng: MDP_BOX.west },
      { lat: MDP_BOX.north, lng: MDP_BOX.east }
    );

    function addOrMove(m, lat, lng, exact) {
      if (!enTierra(lat, lng)) return;
      var pos = exact ? { lat: Number(lat), lng: Number(lng) } : jitterTiny(m.id, Number(lat), Number(lng));
      if (gMarkers[m.id]) {
        gMarkers[m.id].setPosition(pos);
        bounds.extend(pos);
        if (placed) map.fitBounds(bounds, 56);
        return;
      }
      var marker = new google.maps.Marker({
        map: map,
        position: pos,
        title: (m.titulo || ('Ficha ' + m.id)) + ' — ' + (m.textoMapa || m.direccion || '')
      });
      gMarkers[m.id] = marker;
      bounds.extend(pos);
      placed += 1;
      if (hint) hint.textContent = String(placed);
      marker.addListener('click', function () {
        info.setContent(iwHtml(m));
        info.open({ map: map, anchor: marker });
        highlight(m.id);
      });
      map.fitBounds(bounds, 56);
    }

    // Primero un pin aproximado por dirección parseada (para que se vean ya).
    markers.forEach(function (m) {
      var p = posicionInicial(m);
      if (p) addOrMove(m, p.lat, p.lng, false);
    });

    if (google.maps.Geocoder) {
      var geocoder = new google.maps.Geocoder();
      var cache = {};
      var i = 0;
      function next() {
        if (i >= markers.length) return;
        var m = markers[i];
        i += 1;
        var q = m.query || '';
        if (!q) {
          setTimeout(next, 15);
          return;
        }
        if (cache[q]) {
          addOrMove(m, cache[q].lat, cache[q].lng, true);
          setTimeout(next, 30);
          return;
        }
        geocoder.geocode({
          address: q,
          bounds: mdpBias,
          region: 'ar',
          componentRestrictions: { country: 'AR' }
        }, function (results, status) {
          if (status === 'OVER_QUERY_LIMIT') {
            i -= 1;
            setTimeout(next, 700);
            return;
          }
          var loc = null;
          var parsed = m.parsed || parseDireccion(m.textoMapa || '');
          if (status === 'OK' && results) {
            for (var r = 0; r < results.length; r++) {
              var g = results[r].geometry && results[r].geometry.location;
              if (!g) continue;
              var lat = g.lat();
              var lng = g.lng();
              if (!enTierra(lat, lng)) continue;
              if (!resultadoCoincide(results[r], parsed)) continue;
              loc = { lat: lat, lng: lng };
              break;
            }
          }
          if (loc) {
            cache[q] = loc;
            addOrMove(m, loc.lat, loc.lng, true);
          }
          setTimeout(next, 120);
        });
      }
      next();
    }

    var zona = document.getElementById('portal-zona');
    if (zona && google.maps.places) {
      var ac = new google.maps.places.Autocomplete(zona, {
        fields: ['geometry'],
        componentRestrictions: { country: 'ar' },
        bounds: mdpBias,
        strictBounds: false
      });
      ac.addListener('place_changed', function () {
        var place = ac.getPlace();
        if (!place || !place.geometry || !place.geometry.location) return;
        map.panTo(place.geometry.location);
        map.setZoom(15);
      });
    }
  };

  if (window.google && google.maps) window.initPortalMap();
})();
