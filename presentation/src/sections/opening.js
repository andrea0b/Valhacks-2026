/* Opening: cover with a live booking ticket, the task as a journey, what a good decision is worth. */
(function () {
  var S = Deck.S, $ = Deck.$, $$ = Deck.$$;

  /* ---- cover: hotel facade; windows light up when a request is accepted ---- */
  Deck.slide('s-cover', {
    init: function (el) {
      var svg = $('#facade', el);
      S('rect', { x: 10, y: 60, width: 700, height: 580, rx: 10, fill: '#1B2748' }, svg);
      S('rect', { x: 250, y: 8, width: 220, height: 52, rx: 8, fill: '#2A5BD7' }, svg);
      S('rect', { x: 310, y: 556, width: 100, height: 84, rx: 6, fill: '#0F1830' }, svg);
      var seed = 7; function rnd() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }
      var claim = { '1,4': '0', '3,1': '1' };
      for (var r = 0; r < 5; r++) for (var c = 0; c < 6; c++) {
        S('rect', { x: 48 + 110 * c, y: 90 + 92 * r, width: 82, height: 68, rx: 6, 'class': 'w', 'data-lit': rnd() < 0.6 ? '1' : '0', 'data-claim': claim[r + ',' + c] || '' }, svg);
      }
    },
    enter: function (el) {
      var reqs = [
        { a: 'Downtown · online agency', b: '3 nights at €156', c: 'rate €156 against a bid price of €144', ok: 1, w: '0' },
        { a: 'Downtown · online agency', b: '3 nights at €151', c: 'rate €151 against a bid price of €175', ok: 0 },
        { a: 'Downtown · direct', b: '1 night at €96', c: 'a quiet night: bid price €0', ok: 1, w: '1' }];
      var tk = $('#tk', el), ws = $$('#facade .w', el);
      tk.classList.remove('show');
      ws.forEach(function (w) { w.classList.remove('lit', 'claim'); w.style.transitionDelay = '0ms'; });
      void el.offsetWidth;
      ws.forEach(function (w, i) { if (w.dataset.claim) return; w.style.transitionDelay = (i * 45) + 'ms'; if (w.dataset.lit === '1') w.classList.add('lit'); });
      function show(i) {
        var q = reqs[i];
        tk.classList.remove('show'); void tk.offsetWidth;
        $('#tk1', el).textContent = q.a; $('#tk2', el).textContent = q.b; $('#tk3', el).textContent = q.c;
        var s = $('#tkS', el); s.textContent = q.ok ? 'Accepted' : 'Rejected'; s.className = 'stamp ' + (q.ok ? 'ok' : 'no');
        tk.classList.add('show');
        if (q.ok) Deck.after(700, function () {
          var w = ws.filter(function (x) { return x.dataset.claim === q.w; })[0];
          w.style.transitionDelay = '0ms'; w.classList.add('claim');
          Deck.after(1000, function () { w.classList.remove('claim'); w.classList.add('lit'); });
        });
      }
      if (Deck.instant) { show(2); return; }
      [1300, 3900, 6500].forEach(function (t, i) { Deck.after(t, function () { show(i); }); });
    }
  });

  /* ---- the task as a journey ---- */
  var ICON = {
    mail: 'M7 13h34v24H7z M7 14l17 13 17-13',
    fork: 'M24 42V26 M24 26L11 13 M24 26l13-13 M11 13h9 M11 13v9 M37 13h-9 M37 13v9',
    cal: 'M8 12h32v28H8z M8 20h32 M16 7v9 M32 7v9',
    door: 'M13 41V7h22v34 M7 41h34 M29 24v1'
  };
  function icon(d) { return '<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' + d + '"/></svg>'; }
  Deck.slide('s-task', {
    init: function (el, D) {
      var j = $('#journey', el), H = D.hotels;
      var st = [
        { x: 200, t: 'Request arrives', s: 'Rate, nights, party, channel and how far ahead', i: 'mail', c: '#0F1830', d: 150 },
        { x: 627, t: 'Accept or reject', s: 'Immediately, without seeing the future', i: 'fork', c: '#2A5BD7', d: 190 },
        { x: 1053, t: 'Cancel or show up', s: Deck.pct(H.Downtown.cancel, 1) + ' cancel at Downtown, ' + Deck.pct(H.Seaside.cancel, 1) + ' at Seaside', i: 'cal', c: '#3E4C73', d: 150 },
        { x: 1480, t: 'Check-in', s: 'No room left: the guest is walked and costs 2.5× the stay', i: 'door', c: '#C23B3B', d: 150 }];
      var html = '<div class="track" style="left:200px;width:1280px;top:195px"></div>';
      [['seconds', 413], ['weeks or months', 840], ['arrival day', 1266]].forEach(function (w) { html += '<p class="when" style="left:' + w[1] + 'px;top:142px">' + w[0] + '</p>'; });
      st.forEach(function (s, k) {
        html += '<div class="st rise" style="--i:' + (k + 1) + ';left:' + s.x + 'px;top:105px"><div class="rw">' +
          '<div class="ring" style="width:' + s.d + 'px;height:' + s.d + 'px;background:' + s.c + '">' + icon(ICON[s.i]) + '</div></div>' +
          '<h3>' + s.t + '</h3><p>' + s.s + '</p></div>';
      });
      html += '<div class="token"></div>';
      j.innerHTML = html;
    }
  });

  /* ---- what a good decision is worth ---- */
  Deck.slide('s-stakes', {
    init: function (el) {
      var svg = $('#ladder', el), base = 600, u = 62, W = 300, vals = [];
      var bars = [
        { x: 110, v: 3.79, c: '#C5CBD8', l: 'No overbooking', d: 'Accept only up to capacity' },
        { x: 530, v: 5.26, c: '#98A1B8', l: 'Classic overbooking', d: 'One cancellation rate per hotel' },
        { x: 1370, v: 7.76, c: '#DDE1EA', l: 'Perfect foresight', d: 'Knows who will show up. Not achievable.', dash: 1 }];
      bars.forEach(function (b) {
        var g = S('g', {}, svg);
        var r = S('rect', { x: b.x, y: base - b.v * u, width: W, height: b.v * u, rx: 14, fill: b.c, 'class': 'bar' }, g);
        if (b.dash) { r.setAttribute('stroke', '#98A1B8'); r.setAttribute('stroke-width', 3); r.setAttribute('stroke-dasharray', '12 9'); }
        vals.push({ el: Deck.T(g, b.x + W / 2, base - b.v * u - 22, '0.00', { 'text-anchor': 'middle', 'font-size': 58, 'font-weight': 700, fill: '#0F1830' }), v: b.v });
        Deck.T(g, b.x + W / 2, base + 54, b.l, { 'text-anchor': 'middle', 'font-size': 32, 'font-weight': 600, fill: '#0F1830' });
        Deck.hover(g, '<b>' + b.l + '</b><br>' + b.d + '<br>' + b.v.toFixed(2) + ' M€ net on the 2016 replay');
      });
      function pill(x, y, w, txt, cls, fill, ink) {
        var g = S('g', { 'class': cls }, svg);
        S('rect', { x: x - w / 2, y: y - 30, width: w, height: 60, rx: 30, fill: fill }, g);
        Deck.T(g, x, y + 11, txt, { 'text-anchor': 'middle', 'font-size': 32, 'font-weight': 700, fill: ink });
      }
      pill(470, 322, 110, '+39%', 'fade', '#DDE1EA', '#0F1830');
      S('rect', { x: 950, y: base - 7.76 * u, width: W, height: 2.5 * u, rx: 14, fill: 'none', stroke: '#2A5BD7', 'stroke-width': 3, 'stroke-dasharray': '12 9', 'class': 'fade zt' }, svg);
      Deck.T(svg, 950 + W / 2, base - 7.76 * u + 66, '2.5 M€', { 'text-anchor': 'middle', 'font-size': 44, 'font-weight': 700, fill: '#1E44A8', 'class': 'fade zt' });
      Deck.T(svg, 950 + W / 2, base - 7.76 * u + 106, 'left on the table', { 'text-anchor': 'middle', 'font-size': 28, fill: '#4A5470', 'class': 'fade zt' });
      var ours = S('rect', { x: 950, y: base - 6.33 * u, width: W, height: 6.33 * u, rx: 14, fill: '#2A5BD7', 'class': 'bar ours' }, svg);
      Deck.T(svg, 950 + W / 2, base - 6.33 * u - 22, '6.33', { 'text-anchor': 'middle', 'font-size': 58, 'font-weight': 700, fill: '#1E44A8', 'class': 'oursl' });
      Deck.T(svg, 950 + W / 2, base + 54, 'This system', { 'text-anchor': 'middle', 'font-size': 32, 'font-weight': 700, fill: '#1E44A8', 'class': 'oursl' });
      pill(890, 240, 110, '+20%', 'oursl', '#2A5BD7', '#F8F9FC');
      Deck.hover(ours, '<b>This system</b><br>Calibrated cancellation model and a bid price for every night<br>6.33 M€ net on the 2016 replay');
      var btn = $('#reveal', el);
      btn.onclick = function () { svg.classList.add('rev'); btn.style.visibility = 'hidden'; };
      el._vals = vals;
    },
    enter: function (el) {
      var svg = $('#ladder', el), btn = $('#reveal', el);
      svg.classList.remove('go', 'rev'); btn.style.visibility = '';
      void svg.offsetWidth;
      Deck.after(60, function () { svg.classList.add('go'); });
      el._vals.forEach(function (o, i) { Deck.after(200 + i * 250, function () { Deck.countUp(o.el, o.v, 2, 900); }); });
    }
  });
})();
