/* Decision: fraction of a room, the bid price, the two checks, where the gain comes from. */
(function () {
  var S = Deck.S, T = Deck.T, $ = Deck.$;
  var BLUE = '#2A5BD7', SLATE = '#3E4C73', GREY = '#98A1B8', GREY2 = '#C5CBD8', RED = '#C23B3B', INK = '#0F1830', INK2 = '#4A5470';
  function lin(d0, d1, r0, r1) { return function (v) { return r0 + (v - d0) / (d1 - d0) * (r1 - r0); }; }

  /* ---- fraction of a room ---- */
  var rolled = null;
  function drawFrac(D) {
    var svg = $('#frac'); svg.innerHTML = '';
    var q = D.replay.night.q, cols = 19, tw = 80, th = 112, gx = 8.5, gy = 18;
    q.forEach(function (v, i) {
      var c = i % cols, r = Math.floor(i / cols), x = c * (tw + gx), y = r * (th + gy) + 20;
      var show = rolled ? rolled[i] : null;
      S('rect', { x: x, y: y, width: tw, height: th, rx: 8, fill: '#E6E9F0' }, svg);
      if (!rolled) S('rect', { x: x, y: y + th * (1 - v), width: tw, height: th * v, rx: 8, fill: BLUE }, svg);
      else if (show) S('rect', { x: x, y: y, width: tw, height: th, rx: 8, fill: BLUE }, svg);
      else S('rect', { x: x + 3, y: y + 3, width: tw - 6, height: th - 6, rx: 6, fill: 'none', stroke: RED, 'stroke-width': 4, 'stroke-dasharray': '10 8' }, svg);
      var hit = S('rect', { x: x, y: y, width: tw, height: th, fill: 'transparent' }, svg);
      Deck.hover(hit, 'Shows up with probability <b>' + Deck.pct(v) + '</b>');
    });
    var sum = q.reduce(function (s, v) { return s + v; }, 0);
    $('#fBook').textContent = q.length;
    if (rolled) {
      var n = rolled.filter(Boolean).length;
      $('#fExp').textContent = n; $('#fExpL').textContent = 'guests showed up this time (expected ' + sum.toFixed(1) + ')';
    } else { $('#fExp').textContent = sum.toFixed(1); $('#fExpL').textContent = 'guests expected'; }
  }
  Deck.slide('s-fraction', {
    init: function (el, D) {
      $('#fRoll', el).addEventListener('click', function () {
        rolled = D.replay.night.q.map(function (v) { return Math.random() < v; }); this.textContent = 'Roll again'; drawFrac(D);
      });
      drawFrac(D);
    },
    enter: function (el, D) { rolled = null; $('#fRoll', el).textContent = 'Who shows up?'; drawFrac(D); }
  });

  /* ---- bid price ---- */
  var BX = null;
  function drawBid() {
    var L = Deck.LIVE; if (!L) return;
    var b = L.bid_example, svg = $('#bid'), free = +$('#bidFree').value, rate = +$('#bidRate').value;
    svg.innerHTML = '';
    var xs = b.bid_by_free.free, ys = b.bid_by_free.bid, n = xs.length - 1, x0 = 130, x1 = 1600, top = 40, bot = 500;
    var ymax = 320, X = lin(0, n, x0, x1), Y = lin(0, ymax, bot, top);
    [0, 100, 200, 300].forEach(function (t) { T(svg, x0 - 24, Y(t) + 9, '€' + t, { 'text-anchor': 'end', fill: '#6B7491' }); });
    [0, 50, 100, 150].forEach(function (t) { T(svg, X(t), bot + 44, t, { 'text-anchor': 'middle', fill: '#6B7491' }); });
    S('line', { x1: x0, x2: x1, y1: bot, y2: bot, stroke: GREY2, 'stroke-width': 3 }, svg);
    var d = ''; for (var i = 1; i <= n; i++) if (ys[i] !== null) d += (d ? 'L' : 'M') + X(xs[i]).toFixed(1) + ' ' + Y(Math.min(ys[i], ymax)).toFixed(1);
    S('path', { d: d, fill: 'none', stroke: SLATE, 'stroke-width': 8, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
    var bid = ys[free];
    // region where the rate beats the curve
    var ok = rate >= bid;
    Deck.dash(svg, x0, Y(rate), x1, Y(rate), ok ? BLUE : RED, 4);
    T(svg, x1, Y(rate) - 16, 'request: €' + rate, { 'text-anchor': 'end', 'font-size': 30, 'font-weight': 700, fill: ok ? '#1E44A8' : RED });
    Deck.dash(svg, X(free), Y(bid), X(free), bot, INK, 3);
    S('circle', { cx: X(free), cy: Y(bid), r: 18, fill: INK }, svg);
    T(svg, X(free) + 30, Y(bid) - 22, 'bid price €' + Math.round(bid), { 'font-size': 40, 'font-weight': 700, fill: INK });
    T(svg, x0, bot + 96, 'rooms still free on the night', { 'font-size': 26 });
    var chip = S('g', {}, svg);
    S('rect', { x: x1 - 250, y: 60, width: 250, height: 64, rx: 32, fill: ok ? BLUE : INK }, chip);
    T(chip, x1 - 125, 104, ok ? 'accept' : 'reject', { 'text-anchor': 'middle', 'font-size': 34, 'font-weight': 700, fill: ok ? '#F8F9FC' : '#EEF0F4' });
    $('#bidFreeL').textContent = free + ' rooms free of ' + Math.round(b.capacity) + (free === Math.round(b.free) ? ' (the real state on 20 July)' : '');
    $('#bidRateL').textContent = 'Request pays €' + rate + ' per night';
  }
  Deck.slide('s-bid', {
    init: function (el) {
      var L = Deck.LIVE; if (!L) return;
      var b = L.bid_example, n = b.bid_by_free.free.length - 1;
      var f = $('#bidFree'), r = $('#bidRate');
      f.min = 1; f.max = n; f.value = Math.round(b.free); r.min = 50; r.max = 300; r.value = 160;
      f.addEventListener('input', drawBid); r.addEventListener('input', drawBid);
      $('#bidNote').textContent = 'Downtown, night of 15 September 2016, decided on 20 July: about ' + Math.round(b.N) + ' room-nights of demand still to come, price level €' + Math.round(b.P) + '. The bid price is the rate of the marginal guest we would still seat.';
      drawBid();
    },
    enter: function () { drawBid(); }
  });

  /* ---- two checks ---- */
  var PICKS = [['accepted', 'Accepted'], ['price', 'Too cheap'], ['full', 'Night full'], ['capacity', 'Over capacity']], cur = 'accepted', picked = {};
  function pick() {
    var L = Deck.LIVE; if (!L || picked.accepted) return;
    PICKS.forEach(function (p) {
      var c = L.requests.filter(function (r) { return r.outcome === p[0] && r.nights >= 2 && r.bids; });
      if (p[0] === 'accepted') c = c.filter(function (r) { return r.bid > 0; });
      if (p[0] === 'full') c = c.filter(function (r) { return r.rate > 120; });
      picked[p[0]] = c[Math.floor(c.length * (p[0] === 'accepted' ? 0.35 : 0.2))] || c[0];
    });
  }
  function drawChecks() {
    var L = Deck.LIVE; if (!L) return;
    var r = picked[cur]; if (!r) return;
    var full = r.bid === null, minFree = Math.min.apply(null, r.free), q = 1 - r.p;
    var okV = full ? false : r.rate >= r.bid, okF = minFree >= q - 1e-9;
    var sh = L.hotels[r.hotel].replace(' Hotel', ''), dot = r.hotel ? '#E8602C' : '#3E4C73';
    function arrive(s) { return new Date(s + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }); }
    var free = Math.max(minFree, 0), rate = Math.round(r.rate);
    function sv(inner) { return '<svg viewBox="0 0 800 130" width="800" height="130" role="img" aria-label="Comparison drawn on a scale">' + inner + '</svg>'; }
    function tx(x, y, t, a, sz, wt, fill) { return '<text x="' + x + '" y="' + y + '" text-anchor="' + a + '" font-size="' + sz + '" font-weight="' + wt + '" fill="' + fill + '" style="font-family:var(--font)">' + t + '</text>'; }
    // check 1: rate against bid price on one scale
    var top1 = Math.max(rate, full ? 0 : r.bid) * 1.25, X1 = function (v) { return 30 + v / top1 * 740; }, bx = full ? 770 : X1(r.bid);
    var v1 = '<rect x="30" y="62" width="' + Math.max(0, bx - 30) + '" height="26" rx="6" fill="#F3DCDC"/><rect x="' + bx + '" y="62" width="' + Math.max(0, 770 - bx) + '" height="26" rx="6" fill="#D5DEF7"/>' +
      '<line x1="' + bx + '" y1="30" x2="' + bx + '" y2="104" stroke="#0F1830" stroke-width="4" stroke-dasharray="12 9" stroke-linecap="round"/>' +
      tx(bx, 22, full ? 'night full: bid price ∞' : 'bid price €' + Math.round(r.bid), full ? 'end' : 'middle', 26, 700, '#0F1830') +
      '<circle cx="' + X1(rate) + '" cy="75" r="17" fill="' + (okV ? '#2A5BD7' : '#C23B3B') + '"/>' + tx(X1(rate), 122, 'request €' + rate, X1(rate) > 600 ? 'end' : 'middle', 26, 700, okV ? '#1E44A8' : '#C23B3B');
    // check 2: expected guest against free rooms on the tightest night
    var top2 = Math.max(free, q) * 1.25 || 1, X2 = function (v) { return 30 + v / top2 * 740; };
    var fx = free < 1 ? 36 : X2(free), qx = X2(q), qRight = qx > 400;
    var v2 = '<rect x="30" y="62" width="' + Math.max(0, X2(free) - 30) + '" height="26" rx="6" fill="#D5DEF7"/>' +
      tx(fx, 36, free.toFixed(1) + ' rooms free', free < 1 ? 'start' : 'end', 26, 700, '#0F1830') +
      '<circle cx="' + qx + '" cy="75" r="17" fill="' + (okF ? '#2A5BD7' : '#C23B3B') + '"/>' +
      tx(qRight ? qx + 20 : Math.max(qx - 10, 30), 122, 'expected guest ' + q.toFixed(2), qRight ? 'end' : 'start', 26, 700, okF ? '#1E44A8' : '#C23B3B');
    function card(n, title, sub, vis, ok, eq) {
      return '<div class="card"><div class="q"><span class="n">' + n + '</span><div><b>' + title + '</b><span>' + sub + '</span></div></div><div class="v">' + vis + '</div><div class="res"><span class="chip ' + (ok ? 'ok' : 'no') + '">' + (ok ? 'pass' : 'fail') + '</span><span class="eq">' + eq + '</span></div></div>';
    }
    $('#chkReq').innerHTML = '<b style="color:' + dot + '">●</b> <b>' + sh + '</b> · ' + r.nights + ' nights from ' + arrive(r.arrival) + ' · €' + rate + ' per night · booked ' + r.lead + ' days ahead <span style="margin-left:auto"><b class="c-blue">' + Deck.pct(q) + '</b> chance the guest shows up</span>';
    $('#chkBody').innerHTML =
      card(1, 'Is the rate worth the room?', 'the request must pay at least the bid price', sv(v1), okV, full ? '€' + rate + ' &lt; ∞' : '€' + rate + (okV ? ' ≥ ' : ' &lt; ') + '€' + Math.round(r.bid)) +
      card(2, 'Does it fit?', 'the expected guest must fit the free rooms', sv(v2), okF, q.toFixed(2) + (okF ? ' ≤ ' : ' &gt; ') + free.toFixed(1));
    var acc = okV && okF;
    $('#chkWhy').innerHTML = '<span class="chip ' + (acc ? 'ok' : 'no') + '" style="margin-right:24px">' + (acc ? 'Accepted' : 'Rejected') + '</span>' + r.reason.replace(/^(accepted|rejected): /, '').replace(/; main factors:.*$/, '.');
  }
  Deck.slide('s-checks', {
    init: function (el) {
      var L = Deck.LIVE; if (!L) return;
      pick();
      var host = $('#chkTabs', el);
      PICKS.forEach(function (p) {
        var b = document.createElement('button'); b.type = 'button'; b.className = 'pill' + (p[0] === cur ? ' on' : ''); b.textContent = p[1]; b.dataset.k = p[0]; host.appendChild(b);
      });
      host.addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b) return; cur = b.dataset.k;
        Deck.$$('button', host).forEach(function (x) { x.classList.toggle('on', x === b); }); drawChecks();
      });
      drawChecks();
    }
  });

  /* ---- where the gain comes from ---- */
  Deck.slide('s-lever', {
    init: function (el, D) {
      var svg = $('#lever'), base = 560, Y = lin(3.0, 4.6, base, 70), bw = 190;
      var steps = [['Classic overbooking', 0, 3.67, GREY, '3.67'], ['Each booking’s own probability', 3.67, 3.855, SLATE, '+0.19'], ['Bid price per night', 3.855, 4.41, BLUE, '+0.55']];
      steps.forEach(function (s, i) {
        var x = 20 + i * 250, lo = s[1] || 3.0, yTop = Y(s[2]), yLo = Y(lo);
        S('rect', { x: x, y: yTop, width: bw, height: yLo - yTop, rx: 6, fill: s[3] }, svg);
        T(svg, x + bw / 2, yTop - 18, s[4], { 'text-anchor': 'middle', 'font-size': 44, 'font-weight': 700, fill: i === 2 ? '#1E44A8' : INK });
        var w = s[0].split(' ');
        T(svg, x + bw / 2, base + 44, w.slice(0, 2).join(' '), { 'text-anchor': 'middle', 'font-size': 26, 'font-weight': 600 });
        T(svg, x + bw / 2, base + 76, w.slice(2).join(' '), { 'text-anchor': 'middle', 'font-size': 26, 'font-weight': 600 });
      });
      // total
      var xT = 20 + 3 * 250; S('rect', { x: xT, y: Y(4.41), width: bw, height: base - Y(4.41), rx: 6, fill: INK }, svg);
      T(svg, xT + bw / 2, Y(4.41) - 18, '4.41', { 'text-anchor': 'middle', 'font-size': 44, 'font-weight': 700, fill: INK });
      T(svg, xT + bw / 2, base + 44, 'Bid price', { 'text-anchor': 'middle', 'font-size': 26, 'font-weight': 600 });
      T(svg, xT + bw / 2, base + 76, 'policy', { 'text-anchor': 'middle', 'font-size': 26, 'font-weight': 600 });
            T(svg, 0, 690, 'net revenue in M€, 1st + 2nd half of 2016, logistic regression; axis starts at 3.0', { 'font-size': 24 });
      // rejected variants
      var ab = D.policy.ablation, items = [['bid price × 1.1', ab['bid1.1']], ['safety margin 0.5σ', ab.z0501 !== undefined ? ab.z0501 : ab['z0.5']], ['price the walk, k = 3.5', ab['displace3.5']], ['bid price × 0.9', ab['bid0.9']], ['price the walk, k = 2.5', ab['displace2.5']]];
      var x0 = 1560, zero = 1310, X = lin(-0.25, 0.05, 1130, x0 - 0);
      T(svg, 1130, 30, 'Variants we rejected, change in net (M€)', { 'font-size': 28, 'font-weight': 700, fill: INK });
      zero = X(0); Deck.dash(svg, zero, 70, zero, 640, INK, 3);
      items.forEach(function (it, i) {
        var y = 130 + i * 112, v = it[1], x = X(v);
        T(svg, 1120, y - 22, it[0], { 'font-size': 26, 'font-weight': 600, fill: INK });
        S('line', { x1: zero, x2: x, y1: y + 14, y2: y + 14, stroke: v < -0.02 ? RED : GREY, 'stroke-width': 8, 'stroke-linecap': 'round' }, svg);
        S('circle', { cx: x, cy: y + 14, r: 14, fill: v < -0.02 ? RED : GREY }, svg);
        T(svg, v < 0 ? x - 26 : x + 26, y + 24, (v > 0 ? '+' : '') + v.toFixed(3), { 'text-anchor': v < 0 ? 'end' : 'start', 'font-size': 28, 'font-weight': 700, fill: v < -0.02 ? RED : INK2 });
      });
    }
  });
})();
