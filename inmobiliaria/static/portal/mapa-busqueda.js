(function () {
  var MDP = { lat: -38.0038, lng: -57.5486 };
  var MDP_BOX = { south: -38.12, north: -37.93, west: -57.64, east: -57.534 };
  var MDP_BOUNDS = {
    south: MDP_BOX.south,
    west: MDP_BOX.west,
    north: MDP_BOX.north,
    east: MDP_BOX.east
  };

  /**
   * Ejes de calles en Mar del Plata: [altura, lat, lng] de OpenStreetMap.
   * La ubicación de «Calle N» se interpola sobre este eje (no se inventa con Google).
   */
  var EJES = {
    'santa fe': [
      [1500, -37.9984392, -57.5431471],
      [1700, -38.0004018, -57.5446813],
      [2000, -38.0027694, -57.5466145],
      [2200, -38.0044579, -57.5479372],
      [2500, -38.0067920, -57.5499710]
    ],
    'corrientes': [
      [1700, -38.0009060, -57.5437024],
      [2000, -38.0032733, -57.5456220],
      [2200, -38.0049484, -57.5469686],
      [2500, -38.0073340, -57.5488950]
    ],
    'entre rios': [
      [1700, -38.0014443, -57.5427232],
      [2000, -38.0038055, -57.5446116],
      [2200, -38.0054320, -57.5459527],
      [2500, -38.0078440, -57.5479940]
    ],
    'colon': [
      [1200, -38.0107255, -57.5361157],
      [1500, -38.0092007, -57.5391691],
      [1700, -38.0082395, -57.5410839],
      [2000, -38.0066797, -57.5441389],
      [2200, -38.0057017, -57.5460663],
      [2500, -38.0041949, -57.5490748]
    ],
    'colón': null, // alias → colon
    'gascon': [
      [1200, -38.0131260, -57.5381140],
      [1500, -38.0115940, -57.5411390],
      [1700, -38.0106431, -57.5430366],
      [2000, -38.0090770, -57.5461080],
      [2200, -38.0080630, -57.5481310],
      [2500, -38.0065610, -57.5510970]
    ],
    'gascón': null,
    'mitre': [
      [1200, -37.9943396, -57.5454028],
      [1500, -37.9967315, -57.5473702],
      [1700, -37.9983736, -57.5488496],
      [2000, -38.0007585, -57.5506632],
      [2200, -38.0024121, -57.5519335],
      [2500, -38.0048470, -57.5539160]
    ],
    'independencia': [
      [1200, -37.9922480, -57.5494890],
      [1500, -37.9946760, -57.5514390],
      [1700, -37.9963911, -57.5527501],
      [2000, -37.9987656, -57.5546675],
      [2200, -38.0003532, -57.5559417],
      [2500, -38.0027810, -57.5579920]
    ],
    'almirante brown': [
      [1200, -38.0115642, -57.5368006],
      [1500, -38.0100950, -57.5399370],
      [1700, -38.0091120, -57.5418520],
      [2000, -38.0075590, -57.5448790],
      [2200, -38.0065473, -57.5467663],
      [2500, -38.0050040, -57.5498270]
    ],
    'luro': [
      [2200, -38.0008133, -57.5421639],
      [2500, -37.9993077, -57.5451388]
    ],
    'belgrano': [
      [1500, -38.0025601, -57.5451585],
      [2000, -38.0002738, -57.5496564],
      [2200, -38.0032298, -57.5440738],
      [2500, -38.0016565, -57.5471719]
    ],
    'rivadavia': [
      [1500, -38.0000165, -57.5480582],
      [2000, -38.0000165, -57.5480582],
      [2200, -38.0024729, -57.5434684],
      [2500, -38.0009534, -57.5464890]
    ],
    'moreno': [
      [2000, -38.0019024, -57.5487037],
      [2200, -38.0040412, -57.5447265],
      [2500, -38.0025406, -57.5477017]
    ],
    'san martin': [
      [2200, -38.0016392, -57.5428347],
      [2500, -38.0001254, -57.5458275]
    ],
    'san martín': null,
    'sarmiento': [
      [2200, -38.0084434, -57.5399439],
      [2500, -38.0108720, -57.5419930]
    ]
  };
  EJES['colón'] = EJES['colon'];
  EJES['gascón'] = EJES['gascon'];
  EJES['san martín'] = EJES['san martin'];

  var ESQUINAS = {
    'belgrano|corrientes': [-38.0038, -57.5488],
    'corrientes|gascon': [-38.0085, -57.5420],
    'corrientes|gascón': [-38.0085, -57.5420],
    'corrientes|moreno': [-38.0048, -57.5490],
    '3 de febrero|mitre': [-38.0015, -57.5428],
    'gascon|la costa': [-38.0120, -57.5355],
    'gascón|la costa': [-38.0120, -57.5355],
    'moreno|santa fe': [-38.0058, -57.5485],
    'colon|santa fe': [-38.0040, -57.5475],
    'colón|santa fe': [-38.0040, -57.5475],
    'luro|san martin': [-38.0035, -57.5495],
    'luro|san martín': [-38.0035, -57.5495]
  };

  function fold(s) {
    return String(s || '').toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9ñ\s]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function enTierra(lat, lng) {
    return Number.isFinite(lat) && Number.isFinite(lng) &&
      lat <= MDP_BOX.north && lat >= MDP_BOX.south &&
      lng >= MDP_BOX.west && lng <= MDP_BOX.east;
  }

  function normalizarDireccion(raw) {
    var t = String(raw || '');
    t = t.replace(/\s*[-–—]\s*piso\s+\S+.*/i, '');
    t = t.replace(/\s*[-–—]\s*dpto\.?\s+\S+.*/i, '');
    t = t.replace(/\s*piso\s+\S+/ig, '');
    t = t.replace(/\s*(dpto|depto|departamento)\.?\s+\S+/ig, '');
    t = t.replace(/\b(?:al|n[°ºo.]?|nro\.?|num\.?|numero)\s*(\d{2,5})\b/ig, ' $1 ');
    t = t.replace(/\s+e\s+/ig, ' y ');
    return t.replace(/\s+/g, ' ').trim();
  }

  function ejeDe(calle) {
    var k = fold(calle);
    if (EJES[k]) return EJES[k];
    var found = null;
    Object.keys(EJES).forEach(function (name) {
      if (!EJES[name]) return;
      if (k.indexOf(name) !== -1 || name.indexOf(k) !== -1) found = EJES[name];
    });
    return found;
  }

  /** Interpolar lat/lng por altura sobre el eje de la calle. */
  function posPorAltura(calle, numero) {
    var eje = ejeDe(calle);
    if (!eje || !eje.length) return null;
    var n = parseInt(numero, 10);
    if (!Number.isFinite(n)) return null;
    if (n <= eje[0][0]) return { lat: eje[0][1], lng: eje[0][2], exact: true };
    if (n >= eje[eje.length - 1][0]) {
      var last = eje[eje.length - 1];
      return { lat: last[1], lng: last[2], exact: true };
    }
    for (var i = 0; i < eje.length - 1; i++) {
      var a = eje[i];
      var b = eje[i + 1];
      if (n >= a[0] && n <= b[0]) {
        var t = (n - a[0]) / (b[0] - a[0]);
        return {
          lat: a[1] + (b[1] - a[1]) * t,
          lng: a[2] + (b[2] - a[2]) * t,
          exact: true
        };
      }
    }
    return null;
  }

  function parseDireccion(texto) {
    var limpio = normalizarDireccion(texto);
    var f = fold(limpio);
    var mNum = f.match(/\b(\d{2,5})\b/);
    var numero = mNum ? mNum[1] : '';
    var esquina = null;
    var mEsq = f.match(/^(.+?)\s+y\s+(.+)$/);
    if (mEsq && !numero) esquina = [mEsq[1].trim(), mEsq[2].trim()];

    var calle = '';
    var largo = 0;
    Object.keys(EJES).forEach(function (name) {
      if (!EJES[name]) return;
      if ((' ' + f + ' ').indexOf(' ' + name + ' ') !== -1 && name.length >= largo) {
        largo = name.length;
        calle = name;
      }
    });
    if (!calle) {
      if (esquina) calle = esquina[0];
      else if (numero) calle = f.replace(numero, ' ').replace(/\s+/g, ' ').trim();
      else calle = f;
    }
    return { original: limpio, fold: f, calle: calle, numero: numero, esquina: esquina };
  }

  function queryGeocode(parsed) {
    var partes = [];
    if (parsed.esquina) {
      partes.push(parsed.esquina[0] + ' y ' + parsed.esquina[1]);
    } else if (parsed.calle && parsed.numero) {
      partes.push(parsed.calle + ' ' + parsed.numero);
    } else if (parsed.original) {
      partes.push(parsed.original);
    }
    partes.push('Mar del Plata', 'Buenos Aires', 'Argentina');
    return partes.filter(Boolean).join(', ');
  }

  function posEsquina(parsed) {
    if (!parsed.esquina) return null;
    var a = fold(parsed.esquina[0]);
    var b = fold(parsed.esquina[1]);
    var key = [a, b].sort().join('|');
    if (ESQUINAS[key]) return { lat: ESQUINAS[key][0], lng: ESQUINAS[key][1], exact: false };
    return null;
  }

  function posicionDesdeDireccion(parsed) {
    if (parsed.calle && parsed.numero) {
      var p = posPorAltura(parsed.calle, parsed.numero);
      if (p && enTierra(p.lat, p.lng)) return p;
    }
    var e = posEsquina(parsed);
    if (e && enTierra(e.lat, e.lng)) return e;
    // Sin número: punto medio del eje
    var eje = ejeDe(parsed.calle);
    if (eje && eje.length) {
      var mid = eje[Math.floor(eje.length / 2)];
      return { lat: mid[1], lng: mid[2], exact: false };
    }
    return null;
  }

  function metrosAprox(lat1, lng1, lat2, lng2) {
    var dlat = (lat1 - lat2) * 111320;
    var dlng = (lng1 - lng2) * 111320 * Math.cos((lat1 + lat2) * Math.PI / 360);
    return Math.sqrt(dlat * dlat + dlng * dlng);
  }

  function mejorTextoDireccion(direccion, ubicacion) {
    var d = normalizarDireccion(direccion);
    var u = normalizarDireccion(ubicacion);
    var pd = parseDireccion(d);
    var pu = parseDireccion(u);
    if (pd.numero && ejeDe(pd.calle)) return d;
    if (pu.numero && ejeDe(pu.calle)) return u;
    if (pd.numero && !pu.numero) return d;
    if (pu.numero && !pd.numero) return u;
    if (pd.esquina && !pu.esquina) return d;
    if (pu.esquina && !pd.esquina) return u;
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
          var texto = mejorTextoDireccion(m.direccion || '', m.ubicacion || '');
          var parsed = parseDireccion(texto);
          m.textoMapa = texto;
          m.parsed = parsed;
          m.query = queryGeocode(parsed);
          return m;
        });
      }
    } catch (e) { markers = []; }
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
  function jitterTiny(id, lat, lng) {
    var h = 0;
    var s = String(id || '');
    for (var i = 0; i < s.length; i++) h = (h * 33 + s.charCodeAt(i)) % 97;
    return {
      lat: lat + ((h % 3) - 1) * 0.00003,
      lng: lng + ((Math.floor(h / 3) % 3) - 1) * 0.00003
    };
  }

  function posicionFinal(m) {
    var parsed = m.parsed || parseDireccion(m.textoMapa || m.direccion || '');
    var fromStreet = posicionDesdeDireccion(parsed);
    // Si tenemos eje+altura, ESA es la verdad (Santa Fe 1715 ≠ Entre Ríos).
    if (fromStreet && fromStreet.exact) return fromStreet;
    var savedLat = Number(m.lat);
    var savedLng = Number(m.lng);
    if (enTierra(savedLat, savedLng)) {
      if (fromStreet && metrosAprox(savedLat, savedLng, fromStreet.lat, fromStreet.lng) > 120) {
        return fromStreet; // coords guardadas/Google estaban en otra calle
      }
      if (!fromStreet) return { lat: savedLat, lng: savedLng, exact: false };
    }
    return fromStreet;
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
      var p = posicionFinal(m);
      if (!p) return;
      var pos = jitterTiny(m.id, p.lat, p.lng);
      var mk = L.marker([pos.lat, pos.lng]).addTo(map);
      mk.bindPopup(iwHtml(m));
      mk.on('click', function () { highlight(m.id); });
      group.push(mk);
    });
    if (group.length) map.fitBounds(L.featureGroup(group).getBounds().pad(0.18));
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
      restriction: { latLngBounds: MDP_BOUNDS, strictBounds: false }
    });
    var bounds = new google.maps.LatLngBounds();
    var info = new google.maps.InfoWindow();
    var placed = 0;
    var hint = document.querySelector('#portal-map-panel .map-count');
    var gMarkers = {};

    function addOrMove(m, lat, lng) {
      if (!enTierra(lat, lng)) return;
      var pos = jitterTiny(m.id, Number(lat), Number(lng));
      if (gMarkers[m.id]) {
        gMarkers[m.id].setPosition(pos);
        bounds.extend(pos);
        if (placed) map.fitBounds(bounds, 56);
        return;
      }
      var marker = new google.maps.Marker({
        map: map,
        position: pos,
        title: (m.titulo || ('Ficha ' + m.id)) + ' — ' + (m.textoMapa || '')
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

    markers.forEach(function (m) {
      var p = posicionFinal(m);
      if (p) addOrMove(m, p.lat, p.lng);
    });

    // Google solo afina si el resultado cae cerca del eje de la misma calle.
    if (google.maps.Geocoder) {
      var geocoder = new google.maps.Geocoder();
      var i = 0;
      var mdpBias = new google.maps.LatLngBounds(
        { lat: MDP_BOX.south, lng: MDP_BOX.west },
        { lat: MDP_BOX.north, lng: MDP_BOX.east }
      );
      function next() {
        if (i >= markers.length) return;
        var m = markers[i++];
        var parsed = m.parsed || parseDireccion(m.textoMapa || '');
        var base = posicionDesdeDireccion(parsed);
        // Si ya interpolamos por altura, no dejamos que Google lo mueva a otra calle.
        if (base && base.exact) {
          setTimeout(next, 10);
          return;
        }
        if (!m.query) {
          setTimeout(next, 10);
          return;
        }
        geocoder.geocode({
          address: m.query,
          bounds: mdpBias,
          region: 'ar',
          componentRestrictions: { country: 'AR' }
        }, function (results, status) {
          if (status === 'OK' && results && results[0] && results[0].geometry) {
            var loc = results[0].geometry.location;
            var lat = loc.lat();
            var lng = loc.lng();
            var txt = fold(results[0].formatted_address || '');
            var calleOk = !parsed.calle || txt.indexOf(fold(parsed.calle)) !== -1;
            var cerca = !base || metrosAprox(lat, lng, base.lat, base.lng) < 150;
            if (enTierra(lat, lng) && calleOk && cerca && txt.indexOf('mar del plata') !== -1) {
              addOrMove(m, lat, lng);
            }
          }
          setTimeout(next, 100);
        });
      }
      next();
    }

    var zona = document.getElementById('portal-zona');
    if (zona && google.maps.places) {
      var ac = new google.maps.places.Autocomplete(zona, {
        fields: ['geometry'],
        componentRestrictions: { country: 'ar' },
        bounds: new google.maps.LatLngBounds(
          { lat: MDP_BOX.south, lng: MDP_BOX.west },
          { lat: MDP_BOX.north, lng: MDP_BOX.east }
        )
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
