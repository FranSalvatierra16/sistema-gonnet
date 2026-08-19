(function () {
  var MDP = { lat: -38.0055, lng: -57.5426 };
  var ZONAS = [
    ['punta mogotes', -38.0865, -57.5468],
    ['playa grande', -38.0168, -57.5332],
    ['playa chica', -38.0128, -57.5324],
    ['stella maris', -38.0189, -57.5315],
    ['la perla', -37.9992, -57.5418],
    ['los troncos', -38.0104, -57.5488],
    ['güemes', -38.0084, -57.5364],
    ['guemes', -38.0084, -57.5364],
    ['plaza mitre', -38.0024, -57.5466],
    ['constitucion', -38.0210, -57.5485],
    ['constitución', -38.0210, -57.5485],
    ['independencia', -38.0048, -57.5440],
    ['san martin', -38.0028, -57.5455],
    ['san martín', -38.0028, -57.5455],
    ['pueyrredon', -38.0005, -57.5530],
    ['pueyrredón', -38.0005, -57.5530],
    ['gascón', -38.0122, -57.5348],
    ['gascon', -38.0122, -57.5348],
    ['santa fe', -38.0065, -57.5460],
    ['parque luro', -38.0300, -57.5650],
    ['las américas', -37.9800, -57.5450],
    ['las americas', -37.9800, -57.5450],
    ['san carlos', -38.0400, -57.5550],
    ['chauspe', -38.0250, -57.5500],
    ['alem', -37.9918, -57.5482],
    ['luro', -38.0032, -57.5485],
    ['moreno', -38.0056, -57.5472],
    ['colón', -38.0015, -57.5448],
    ['colon', -38.0015, -57.5448],
    ['centro', -37.9978, -57.5498]
  ];

  function markersFromCards() {
    return Array.prototype.map.call(document.querySelectorAll('.card[data-ficha]'), function (card) {
      return {
        id: card.getAttribute('data-ficha'),
        titulo: card.getAttribute('data-titulo') || '',
        ubicacion: card.getAttribute('data-ubicacion') || '',
        direccion: card.getAttribute('data-direccion') || '',
        query: [card.getAttribute('data-direccion'), card.getAttribute('data-ubicacion'), 'Mar del Plata, Buenos Aires, Argentina'].filter(Boolean).join(', '),
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
  function hasPos(m) {
    var lat = Number(m.lat);
    var lng = Number(m.lng);
    return Number.isFinite(lat) && Number.isFinite(lng) && lat !== 0 && lng !== 0;
  }
  function jitter(id, lat, lng, step) {
    step = step || 0.0012;
    var h = 0;
    var s = String(id || '');
    for (var i = 0; i < s.length; i++) h = (h * 33 + s.charCodeAt(i)) % 97;
    return {
      lat: lat + ((h % 9) - 4) * step,
      lng: lng + ((Math.floor(h / 9) % 9) - 4) * step
    };
  }
  function zonaPos(text) {
    var t = String(text || '').toLowerCase();
    var best = null;
    var n = 0;
    ZONAS.forEach(function (z) {
      if (t.indexOf(z[0]) !== -1 && z[0].length >= n) {
        n = z[0].length;
        best = { lat: z[1], lng: z[2] };
      }
    });
    return best;
  }
  function posicionInicial(m) {
    if (hasPos(m)) return jitter(m.id, Number(m.lat), Number(m.lng), 0.00018);
    var z = zonaPos((m.direccion || '') + ' ' + (m.ubicacion || '') + ' ' + (m.query || ''));
    if (z) return jitter(m.id, z.lat, z.lng, 0.0014);
    return jitter(m.id, MDP.lat, MDP.lng, 0.006);
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
      fullscreenControl: true
    });
    var bounds = new google.maps.LatLngBounds();
    var info = new google.maps.InfoWindow();
    var placed = 0;
    var hint = document.querySelector('#portal-map-panel .map-count');
    var gMarkers = {};

    function addOrMove(m, lat, lng) {
      var pos = { lat: Number(lat), lng: Number(lng) };
      if (gMarkers[m.id]) {
        gMarkers[m.id].setPosition(pos);
        bounds.extend(pos);
        map.fitBounds(bounds, 48);
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
      map.fitBounds(bounds, 48);
    }

    markers.forEach(function (m) {
      var p = posicionInicial(m);
      addOrMove(m, p.lat, p.lng);
    });

    if (google.maps.Geocoder) {
      var geocoder = new google.maps.Geocoder();
      var cache = {};
      var i = 0;
      function next() {
        if (i >= markers.length) return;
        var m = markers[i];
        i += 1;
        if (hasPos(m) || !m.query) {
          setTimeout(next, 20);
          return;
        }
        if (cache[m.query]) {
          addOrMove(m, cache[m.query].lat, cache[m.query].lng);
          setTimeout(next, 40);
          return;
        }
        geocoder.geocode({ address: m.query }, function (results, status) {
          if (status === 'OVER_QUERY_LIMIT') {
            i -= 1;
            setTimeout(next, 600);
            return;
          }
          if (status === 'OK' && results[0] && results[0].geometry) {
            var loc = results[0].geometry.location;
            var refined = jitter(m.id, loc.lat(), loc.lng(), 0.00018);
            cache[m.query] = refined;
            addOrMove(m, refined.lat, refined.lng);
          }
          setTimeout(next, 90);
        });
      }
      next();
    }

    var zona = document.getElementById('portal-zona');
    if (zona && google.maps.places) {
      var ac = new google.maps.places.Autocomplete(zona, {
        fields: ['geometry'],
        componentRestrictions: { country: 'ar' }
      });
      ac.addListener('place_changed', function () {
        var place = ac.getPlace();
        if (!place || !place.geometry || !place.geometry.location) return;
        map.panTo(place.geometry.location);
        map.setZoom(15);
      });
    } else if (zona) {
      zona.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Enter') return;
        ev.preventDefault();
        var q = (zona.value || '').trim();
        if (!q) return;
        var geocoderZ = new google.maps.Geocoder();
        geocoderZ.geocode({ address: q + ', Mar del Plata, Argentina' }, function (results, status) {
          if (status === 'OK' && results[0]) {
            map.panTo(results[0].geometry.location);
            map.setZoom(15);
          }
        });
      });
    }
  };

  if (window.google && google.maps) window.initPortalMap();
})();
