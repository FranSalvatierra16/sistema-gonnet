(function () {
  var MDP = { lat: -38.0038, lng: -57.5486 };
  var MDP_BOX = { south: -38.12, north: -37.93, west: -57.64, east: -57.534 };
  var MDP_BOUNDS = {
    south: MDP_BOX.south,
    west: MDP_BOX.west,
    north: MDP_BOX.north,
    east: MDP_BOX.east
  };

  // Puntos en TIERRA (un poco al oeste de la costa). Nombres largos primero.
  var ZONAS = [
    ['punta mogotes', -38.0865, -57.5510],
    ['playa grande', -38.0165, -57.5378],
    ['playa chica', -38.0125, -57.5368],
    ['stella maris', -38.0185, -57.5365],
    ['la perla', -38.0005, -57.5455],
    ['los troncos', -38.0104, -57.5515],
    ['plaza mitre', -38.0024, -57.5488],
    ['parque luro', -38.0285, -57.5680],
    ['las américas', -37.9820, -57.5520],
    ['las americas', -37.9820, -57.5520],
    ['san carlos', -38.0380, -57.5580],
    ['constitución', -38.0205, -57.5510],
    ['constitucion', -38.0205, -57.5510],
    ['pueyrredón', -38.0008, -57.5555],
    ['pueyrredon', -38.0008, -57.5555],
    ['independencia', -38.0048, -57.5475],
    ['san martín', -38.0032, -57.5488],
    ['san martin', -38.0032, -57.5488],
    ['hipólito yrigoyen', -38.0030, -57.5478],
    ['hipolito yrigoyen', -38.0030, -57.5478],
    ['yrigoyen', -38.0030, -57.5478],
    ['corrientes', -38.0036, -57.5494],
    ['belgrano', -38.0042, -57.5482],
    ['gascón', -38.0118, -57.5388],
    ['gascon', -38.0118, -57.5388],
    ['güemes', -38.0080, -57.5405],
    ['guemes', -38.0080, -57.5405],
    ['santa fe', -38.0062, -57.5488],
    ['rivadavia', -38.0026, -57.5496],
    ['sarmiento', -38.0055, -57.5502],
    ['almirante brown', -38.0070, -57.5490],
    ['chauspe', -38.0240, -57.5530],
    ['colón', -38.0018, -57.5480],
    ['colon', -38.0018, -57.5480],
    ['moreno', -38.0056, -57.5490],
    ['luro', -38.0038, -57.5502],
    ['alem', -37.9935, -57.5510]
  ];

  function markersFromCards() {
    return Array.prototype.map.call(document.querySelectorAll('.card[data-ficha]'), function (card) {
      var direccion = card.getAttribute('data-direccion') || '';
      var ubicacion = card.getAttribute('data-ubicacion') || '';
      return {
        id: card.getAttribute('data-ficha'),
        titulo: card.getAttribute('data-titulo') || '',
        ubicacion: ubicacion,
        direccion: direccion,
        query: [direccion, 'Mar del Plata', 'Buenos Aires', 'Argentina'].filter(Boolean).join(', '),
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
      if (el && el.textContent) markers = JSON.parse(el.textContent) || [];
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
    return '<div class="portal-iw">' + img +
      '<strong>' + esc(m.titulo) + '</strong>' +
      '<div style="font-size:0.78rem;color:#5d6b5c;margin:0.15rem 0">' + esc(m.ubicacion || m.direccion) + '</div>' +
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
  function aTierra(lat, lng) {
    return {
      lat: Math.min(MDP_BOX.north, Math.max(MDP_BOX.south, lat)),
      lng: Math.min(MDP_BOX.east, Math.max(MDP_BOX.west, lng))
    };
  }
  function hasPos(m) {
    return enTierra(Number(m.lat), Number(m.lng));
  }
  function jitterInland(id, lat, lng) {
    var h = 0;
    var s = String(id || '');
    for (var i = 0; i < s.length; i++) h = (h * 33 + s.charCodeAt(i)) % 97;
    var dlat = ((h % 5) - 2) * 0.00012;
    var dlng = -((h % 4) + 1) * 0.0001;
    return aTierra(lat + dlat, lng + dlng);
  }
  function contieneNombre(texto, nombre) {
    var t = ' ' + String(texto || '').toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9ñ\s]/g, ' ') + ' ';
    var n = String(nombre || '').toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    return t.indexOf(' ' + n + ' ') !== -1;
  }
  function zonaPos(text) {
    var best = null;
    var n = 0;
    ZONAS.forEach(function (z) {
      if (contieneNombre(text, z[0]) && z[0].length >= n) {
        n = z[0].length;
        best = { lat: z[1], lng: z[2] };
      }
    });
    return best;
  }
  function posicionInicial(m) {
    if (hasPos(m)) return jitterInland(m.id, Number(m.lat), Number(m.lng));
    var z = zonaPos((m.direccion || '') + ' ' + (m.ubicacion || ''));
    if (z) return jitterInland(m.id, z.lat, z.lng);
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

    function addOrMove(m, lat, lng) {
      if (!enTierra(lat, lng)) return;
      var pos = jitterInland(m.id, lat, lng);
      if (gMarkers[m.id]) {
        gMarkers[m.id].setPosition(pos);
        bounds.extend(pos);
        if (placed) map.fitBounds(bounds, 56);
        return;
      }
      var marker = new google.maps.Marker({
        map: map,
        position: pos,
        title: m.titulo || ('Ficha ' + m.id)
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
      var p = posicionInicial(m);
      if (p) addOrMove(m, p.lat, p.lng);
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
          setTimeout(next, 20);
          return;
        }
        if (cache[q]) {
          addOrMove(m, cache[q].lat, cache[q].lng);
          setTimeout(next, 40);
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
          if (status === 'OK' && results) {
            for (var r = 0; r < results.length; r++) {
              var g = results[r].geometry && results[r].geometry.location;
              if (!g) continue;
              var lat = g.lat();
              var lng = g.lng();
              var txt = ((results[r].formatted_address || '') + ' ' + JSON.stringify(results[r].address_components || [])).toLowerCase();
              if (enTierra(lat, lng) && txt.indexOf('mar del plata') !== -1) {
                loc = { lat: lat, lng: lng };
                break;
              }
            }
          }
          if (loc) {
            cache[q] = loc;
            addOrMove(m, loc.lat, loc.lng);
          }
          setTimeout(next, 110);
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
