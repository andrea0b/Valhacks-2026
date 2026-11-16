/* Economics: one night, one average guest, independent cancellations at each hotel's real rate.
   Shows ~ Binomial(N, 1 - cancel rate); net = seated - 2.5 x walked, as a share of a full house. */
(function () {
  var S = Deck.S, $ = Deck.$, $$ = Deck.$$;
  var LF = [0];
  for (var i = 1; i <= 800; i++) LF[i] = LF[i - 1] + Math.log(i);
  function pmf(N, q) { var o = [], lq = Math.log(q), lp = Math.log(1 - q); for (var k = 0; k <= N; k++) o[k] = Math.exp(LF[N] - LF[k] - LF[N - k] + k * lq + (N - k) * lp); return o; }
  function stats(N, q, C) { var p = pmf(N, q), e = 0, w = 0; for (var k = 0; k <= N; k++) { if (k < C) e += p[k] * (C - k); else w += p[k] * (k - C); } return { p: p, empty: e, walk: w, net: (C - e - 2.5 * w) / C }; }

  var H = [], cur = 0, N = 0;
  function setup(D) {
    if (H.length) return;
    [['Downtown', D.hotels.Downtown], ['Seaside', D.hotels.Seaside]].forEach(function (x) {
      var h = { name: x[0], C: x[1].rooms, q: 1 - x[1].cancel };
      h.max = Math.floor(h.C * 1.9); h.classic = Math.round(h.C / h.q); h.curve = [];
      var bn = h.C, bv = -9;
      for (var n = h.C; n <= h.max; n++) { var s = stats(n, h.q, h.C); h.curve.push(s.net); if (s.net > bv) { bv = s.net; bn = n; } }
      h.best = bn; h.bestNet = bv; H.push(h);
    });
    N = H[0].classic;
  }
  function slider() { var h = H[cur], s = $('#nslider'); s.min = h.C; s.max = h.max; s.value = N; }

  function drawDist() {
    var svg = $('#dist'), h = H[cur], C = h.C, s = stats(N, h.q, C);
    svg.innerHTML = '';
    var mean = N * h.q, sd = Math.sqrt(N * h.q * (1 - h.q));
    var lo = Math.floor(Math.min(C - 14, mean - 4 * sd)), hi = Math.ceil(Math.max(C + 14, mean + 4 * sd));
    var ph = 330, bw = 1680 / (hi - lo + 1), mx = Math.max.apply(null, s.p.slice(lo, hi + 1));
    for (var k = lo; k <= hi && k <= N; k++) {
      var hh = s.p[k] / mx * ph * 0.9;
      S('rect', { x: (k - lo) * bw + bw * 0.1, y: ph - hh + 40, width: bw * 0.8, height: hh, rx: 2, fill: k < C ? '#B3C5EE' : k === C ? '#2A5BD7' : '#C23B3B' }, svg);
    }
    var cx = (C - lo) * bw + bw / 2;
    Deck.dash(svg, cx, 12, cx, ph + 40, '#0F1830', 4);
    Deck.T(svg, cx - 18, 34, 'capacity ' + C, { 'text-anchor': 'end', 'font-size': 32, 'font-weight': 700, fill: '#0F1830' });
    Deck.T(svg, cx + 18, 34, 'walked', { 'font-size': 32, 'font-weight': 700, fill: '#C23B3B' });
    Deck.T(svg, 0, 408, 'guests who show up on the night, out of ' + N + ' accepted bookings');
    $('#nlabel').textContent = N + ' bookings accepted per night, ' + (N / C).toFixed(2) + '× capacity';
    $('#kEmpty').textContent = s.empty.toFixed(1);
    $('#kWalk').textContent = s.walk.toFixed(1);
    $('#kNet').textContent = (s.net * 100).toFixed(1) + '%';
  }

  function drawCurve() {
    var svg = $('#curve'), h = H[cur], y0 = 0.5, y1 = 1.0, n = h.curve.length, x0 = 170, x1 = 1540, top = 100, bot = 440;
    svg.innerHTML = '';
    function X(i) { return x0 + i / (n - 1) * (x1 - x0); }
    function Y(v) { v = Math.max(y0, Math.min(y1, v)); return bot - (v - y0) / (y1 - y0) * (bot - top); }
    var bi = h.best - h.C, ci = h.classic - h.C;
    Deck.dash(svg, X(bi), Y(h.bestNet) + 30, X(bi), bot + 20, '#2A5BD7', 3);
    var d = ''; h.curve.forEach(function (v, i) { d += (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); });
    S('path', { d: d, fill: 'none', stroke: '#3E4C73', 'stroke-width': 8, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
    function mark(i, label, val, color, ink, r, above, side) {
      var x = X(i), y = Y(h.curve[i]), a = side ? 'start' : 'middle', lx = side ? x + 26 : x;
      S('circle', { cx: x, cy: y, r: r, fill: color }, svg);
      Deck.T(svg, lx, above ? y - r - 66 : y + r + 58, (val * 100).toFixed(1) + '%', { 'text-anchor': a, 'font-size': 56, 'font-weight': 700, fill: ink });
      Deck.T(svg, lx, above ? y - r - 18 : y + r + 104, label, { 'text-anchor': a, 'font-size': 28, 'font-weight': 600, fill: '#4A5470' });
    }
    mark(0, 'capacity: ' + h.C, h.curve[0], '#98A1B8', '#0F1830', 13, false);
    mark(ci, 'classic rule: ' + h.classic, h.curve[ci], '#98A1B8', '#0F1830', 13, false, true);
    mark(bi, 'best: ' + h.best, h.bestNet, '#2A5BD7', '#1E44A8', 19, true);
    Deck.T(svg, x0 - 110, 548, 'bookings accepted per night, from ' + h.C + ' to ' + h.max + '; expected net revenue as a share of a full house');
  }
  function draw() { drawDist(); drawCurve(); }
  function setHotel(k) {
    cur = +k; N = H[cur].classic;
    $$('#seg3 button, #seg4 button').forEach(function (b) { b.classList.toggle('on', +b.dataset.k === cur); });
    slider(); draw();
  }

  Deck.slide('s-accept', {
    init: function (el, D) {
      setup(D); slider();
      $('#nslider').addEventListener('input', function () { N = +this.value; draw(); });
      $('#seg3').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) setHotel(b.dataset.k); });
      $('#presets').addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b) return;
        var h = H[cur]; N = b.dataset.p === 'cap' ? h.C : b.dataset.p === 'classic' ? h.classic : h.best;
        $('#nslider').value = N; draw();
      });
      draw();
    },
    enter: function () { N = H[cur].classic; slider(); draw(); }
  });
  Deck.slide('s-toomany', {
    init: function (el, D) { setup(D); $('#seg4').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) setHotel(b.dataset.k); }); },
    enter: function () { draw(); }
  });
})();
