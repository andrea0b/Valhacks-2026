/* Data: what the bookings say. Every number comes from presentation/build/data.json (presentation/data.py). */
(function () {
  var S = Deck.S, T = Deck.T, $ = Deck.$, $$ = Deck.$$;
  var HOTEL = { Downtown: '#3E4C73', Seaside: '#E8602C' };
  function lin(d0, d1, r0, r1) { return function (v) { return r0 + (v - d0) / (d1 - d0) * (r1 - r0); }; }
  function path(pts) { return pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(''); }
  function yAxis(svg, ticks, Y, x, fmt) { ticks.forEach(function (t) { T(svg, x, Y(t) + 9, fmt(t), { 'text-anchor': 'end' }); }); }

  /* ---- anatomy ---- */
  Deck.slide('s-anatomy', {
    init: function (el, D) { $('#an-n', el).textContent = Deck.fmt(D.hotels.Downtown.bookings + D.hotels.Seaside.bookings); }
  });

  /* ---- demand calendar ---- */
  Deck.slide('s-demand', {
    init: function (el, D) {
      var start = new Date(D.nightly.start + 'T00:00:00'), wd0 = (start.getDay() + 6) % 7, C = 15, P = 18, cells = {};
      var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      function color(r) { return r < 0.5 ? '#DDE3F3' : r < 0.75 ? '#C5D3F1' : r < 1 ? '#9DB5EB' : r < 1.25 ? '#F0B8B8' : r < 1.5 ? '#E27F7F' : r < 1.75 ? '#D05555' : '#A82A2A'; }
      ['Downtown', 'Seaside'].forEach(function (h, idx) {
        var host = $(idx ? '#heatSS' : '#heatDT', el), arr = D.nightly.ratio[h], rooms = D.hotels[h].rooms;
        host.innerHTML = '<div style="display:flex;gap:44px;align-items:flex-start;width:1680px"><div style="width:290px"><p style="font-size:34px;font-weight:700"><span style="display:inline-block;width:20px;height:20px;border-radius:50%;margin-right:12px;background:' + HOTEL[h] + '"></span>' + h + '</p><p class="pct" style="margin-top:6px;font-size:112px;font-weight:700;line-height:1;letter-spacing:-.045em;color:' + HOTEL[h] + '"></p><p class="cap" style="margin-top:4px">of the nights</p></div><svg width="1386" height="' + (idx ? 140 : 160) + '" role="img" aria-label="Calendar of guests who showed up divided by rooms, ' + h + '"></svg></div>';
        var svg = $('svg', host), oy = idx ? 6 : 30;
        if (!idx) for (var m = 0; m < 18; m++) {
          var d0 = new Date(2015, 6 + m, 1), off = Math.round((d0 - start) / 864e5) + wd0;
          if (off >= 0) T(svg, Math.floor(off / 7) * P, 18, months[(6 + m) % 12], { 'font-size': 24 });
        }
        cells[h] = arr.map(function (r, i) {
          var o = i + wd0, rect = S('rect', { x: Math.floor(o / 7) * P, y: oy + (o % 7) * P, width: C, height: C, rx: 3, fill: color(r) }, svg);
          Deck.hover(rect, function () { var d = new Date(start.getTime() + i * 864e5); return '<b>' + d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) + '</b><br>' + Math.round(r * rooms) + ' guests showed up for ' + rooms + ' rooms (' + r.toFixed(2) + '×)'; });
          return rect;
        });
      });
      var thr = $('#thr', el);
      el._upd = function () {
        var t = +thr.value; $('#thrv', el).textContent = t.toFixed(2) + '× the rooms';
        ['Downtown', 'Seaside'].forEach(function (h, idx) {
          var hit = 0; D.nightly.ratio[h].forEach(function (r, i) { var on = r >= t; if (on) hit++; cells[h][i].setAttribute('fill', on ? color(r) : '#E6E9F0'); });
          $('.pct', $(idx ? '#heatSS' : '#heatDT', el)).textContent = Math.round(hit / D.nightly.ratio[h].length * 100) + '%';
        });
      };
      thr.addEventListener('input', el._upd); el._upd();
    },
    enter: function (el) { $('#thr', el).value = 1; el._upd(); }
  });

  /* ---- price by season ---- */
  Deck.slide('s-season', {
    init: function (el, D) {
      var svg = $('#season', el), x0 = 130, x1 = 1500, top = 40, bot = 560, M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      var ymax = 0; ['Downtown', 'Seaside'].forEach(function (h) { ymax = Math.max(ymax, Math.max.apply(null, D.seasons[h].q75)); });
      ymax = Math.ceil(ymax / 50) * 50;
      var X = function (i) { return x0 + i * (x1 - x0) / 11; }, Y = lin(0, ymax, bot, top);
      var ticks = []; for (var t = 0; t <= ymax; t += 50) ticks.push(t);
      yAxis(svg, ticks, Y, x0 - 34, function (v) { return '€' + v; });
      M.forEach(function (m, i) { T(svg, X(i), bot + 48, m, { 'text-anchor': 'middle' }); });
      S('line', { x1: x0 - 10, x2: x1 + 10, y1: bot, y2: bot, stroke: '#C5CBD8', 'stroke-width': 3 }, svg);
      ['Downtown', 'Seaside'].forEach(function (h) {
        var s = D.seasons[h], c = HOTEL[h];
        var up = s.q75.map(function (v, i) { return [X(i), Y(v)]; }), dn = s.q25.map(function (v, i) { return [X(i), Y(v)]; }).reverse();
        S('path', { d: path(up.concat(dn)) + 'Z', fill: c, opacity: 0.14 }, svg);
        S('path', { d: path(s.median.map(function (v, i) { return [X(i), Y(v)]; })), fill: 'none', stroke: c, 'stroke-width': 7, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
        s.median.forEach(function (v, i) { S('circle', { cx: X(i), cy: Y(v), r: 7, fill: c }, svg); });
        T(svg, x1 + 24, Y(s.median[11]) + 9, h, { 'font-size': 30, 'font-weight': 700, fill: c });
      });
      var sm = D.seasons.Seaside.median, lo = Math.min.apply(null, sm), hi = Math.max.apply(null, sm), ilo = sm.indexOf(lo), ihi = sm.indexOf(hi);
      Deck.dash(svg, x0 + 430, Y(hi), X(ihi) - 18, Y(hi), '#E8602C', 3);
      T(svg, x0 + 30, Y(hi) + 20, (hi / lo).toFixed(1) + '×', { 'font-size': 64, 'font-weight': 700, fill: '#C2461B' });
      T(svg, x0 + 30, Y(hi) + 64, 'Seaside: €' + Math.round(lo) + ' a night in ' + M[ilo] + ', €' + Math.round(hi) + ' in ' + M[ihi], { 'font-size': 28, fill: '#4A5470' });
      M.forEach(function (m, i) {
        var r = S('rect', { x: X(i) - 55, y: top, width: 110, height: bot - top, fill: 'transparent' }, svg);
        Deck.hover(r, '<b>' + m + ' 2016</b><br>Downtown median €' + Math.round(D.seasons.Downtown.median[i]) + ' (half between €' + Math.round(D.seasons.Downtown.q25[i]) + ' and €' + Math.round(D.seasons.Downtown.q75[i]) + ')<br>Seaside median €' + Math.round(D.seasons.Seaside.median[i]) + ' (€' + Math.round(D.seasons.Seaside.q25[i]) + '–' + Math.round(D.seasons.Seaside.q75[i]) + ')');
      });
      T(svg, x0 - 100, 662, 'Nightly rate by month of arrival, 2016: line = median, band = middle half of the bookings. A rate is high or low only against its own night.', { 'font-size': 26 });
    }
  });

  /* ---- lead time bubbles ---- */
  Deck.slide('s-lead', {
    init: function (el, D) {
      var order = ['181+', '91-180', '31-90', '8-30', '0-7'], lab = { '181+': '181+ days', '91-180': '91–180', '31-90': '31–90', '8-30': '8–30', '0-7': '0–7 days' };
      var svg = $('#bubbles', el), cx0 = 180, gap = 330, cy = 250, circ = {}, txt = {}, key = 'all';
      function colr(c) { var t = Math.max(0, Math.min(1, (c - 0.08) / 0.54)); return t < 0.5 ? Deck.mix('#2A5BD7', '#9AA3C0', t / 0.5) : Deck.mix('#9AA3C0', '#C23B3B', (t - 0.5) / 0.5); }
      function rad(s) { return 135 * Math.sqrt(s / 0.3); }
      order.forEach(function (b, i) {
        var x = cx0 + gap * i;
        circ[b] = S('circle', { cx: x, cy: cy, r: 10, fill: '#98A1B8', style: 'transition:r .8s cubic-bezier(.2,.7,.2,1),fill .8s' }, svg);
        txt[b] = T(svg, x, cy + 20, '', { 'text-anchor': 'middle', 'font-size': 60, 'font-weight': 700, fill: '#fff', style: 'pointer-events:none' });
        T(svg, x, cy + 196, lab[b], { 'text-anchor': 'middle', 'font-size': 32, 'font-weight': 600, fill: '#0F1830' });
        Deck.hover(circ[b], function () { var d = D.lead[key][b]; return '<b>' + lab[b] + ' before arrival</b><br>' + Deck.fmt(d.n) + ' bookings<br>cancel rate ' + Deck.pct(d.cancel) + '<br>' + Deck.pct(d.share) + ' of the guests who show up<br>median rate €' + Math.round(d.rate); });
      });
      var bx1 = cx0 + gap * 3 - 140, bx2 = cx0 + gap * 4 + 140;
      S('path', { d: 'M' + bx1 + ' 84 V62 H' + bx2 + ' V84', fill: 'none', stroke: '#2A5BD7', 'stroke-width': 6, 'stroke-linejoin': 'round' }, svg);
      var bt = T(svg, bx2, 36, '', { 'text-anchor': 'end', 'font-size': 34, 'font-weight': 700, fill: '#1E44A8' });
      S('path', { d: 'M20 500 H1640', stroke: '#C5CBD8', 'stroke-width': 8, 'stroke-linecap': 'round' }, svg);
      S('path', { d: 'M1620 480 L1650 500 L1620 520', fill: 'none', stroke: '#C5CBD8', 'stroke-width': 8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, svg);
      T(svg, 20, 548, 'days between the request and the arrival');
      el._draw = function () {
        var B = D.lead[key];
        order.forEach(function (b) { var d = B[b]; circ[b].setAttribute('r', rad(d.share)); circ[b].setAttribute('fill', colr(d.cancel)); txt[b].textContent = Deck.pct(d.cancel); });
        bt.textContent = Deck.pct(B['0-7'].share + B['8-30'].share) + ' of the guests who show up booked in the last month';
        $('#callA', el).textContent = Deck.pct(B['0-7'].cancel) + ' vs ' + Deck.pct(B['181+'].cancel);
        var rs = order.map(function (b) { return B[b].rate; });
        $('#callB', el).textContent = '€' + Math.round(Math.min.apply(null, rs)) + '–' + Math.round(Math.max.apply(null, rs));
      };
      Deck.seg($('#leadseg', el), function (k) { key = k; el._draw(); });
      el._circ = circ; el._draw();
    },
    enter: function (el) { Object.keys(el._circ).forEach(function (b) { el._circ[b].setAttribute('r', 10); }); Deck.after(120, el._draw); }
  });

  /* ---- booking ID leak ---- */
  Deck.slide('s-leak', {
    init: function (el, D) {
      var svg = $('#leak', el), x0 = 110, x1 = 1080, top = 30, bot = 540, Y = lin(0, 0.9, bot, top), bw = (x1 - x0) / 10;
      yAxis(svg, [0, 0.3, 0.6, 0.9], Y, x0 - 22, function (v) { return Math.round(v * 100) + '%'; });
      var bars = [], vals = [];
      for (var i = 0; i < 10; i++) {
        bars.push(S('rect', { x: x0 + i * bw + 10, y: bot, width: bw - 20, height: 0, rx: 8, style: 'transition:y .6s,height .6s,fill .4s' }, svg));
        vals.push(T(svg, x0 + i * bw + bw / 2, bot - 14, '', { 'text-anchor': 'middle', 'font-size': 26, 'font-weight': 700, fill: '#0F1830' }));
        T(svg, x0 + i * bw + bw / 2, bot + 40, String(i + 1), { 'text-anchor': 'middle' });
      }
      T(svg, x0, bot + 92, 'position of the booking ID among the requests of its booking day, in tenths', {});
      var h = 'Downtown';
      el._draw = function () {
        var v = D.id_leak[h];
        v.forEach(function (r, i) { bars[i].setAttribute('y', Y(r)); bars[i].setAttribute('height', bot - Y(r)); bars[i].setAttribute('fill', HOTEL[h]); vals[i].setAttribute('y', Y(r) - 14); vals[i].textContent = Math.round(r * 100) + '%'; });
        $('#lk-a', el).textContent = Deck.pct(v[0]); $('#lk-b', el).textContent = Deck.pct(v[9]);
      };
      Deck.seg($('#leakseg', el), function (k) { h = k; el._draw(); });
      el._draw();
    }
  });

  /* ---- drift ---- */
  Deck.slide('s-drift', {
    init: function (el, D) {
      var svg = $('#prt', el), x0 = 90, x1 = 700, top = 90, bot = 470, Y = lin(0, 1, bot, top), q = D.drift.quarters, v = D.drift.prt_share;
      var X = function (i) { return x0 + i * (x1 - x0) / (q.length - 1); };
      T(svg, 0, 34, 'Cancellations recorded as Portugal', { 'font-size': 30, 'font-weight': 700, fill: '#0F1830' });
      yAxis(svg, [0, 0.5, 1], Y, x0 - 22, function (t) { return Math.round(t * 100) + '%'; });
      S('path', { d: path(v.map(function (y, i) { return [X(i), Y(y)]; })) + 'L' + X(q.length - 1) + ' ' + bot + 'L' + x0 + ' ' + bot + 'Z', fill: '#3E4C73', opacity: 0.1 }, svg);
      S('path', { d: path(v.map(function (y, i) { return [X(i), Y(y)]; })), fill: 'none', stroke: '#3E4C73', 'stroke-width': 7, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
      v.forEach(function (y, i) {
        S('circle', { cx: X(i), cy: Y(y), r: 8, fill: '#3E4C73' }, svg);
        T(svg, X(i), bot + 44, q[i].slice(4) + " '" + q[i].slice(2, 4), { 'text-anchor': 'middle', 'font-size': 24 });
      });
      T(svg, X(0) + 18, Y(v[0]) - 22, Deck.pct(v[0]), { 'font-size': 40, 'font-weight': 700, fill: '#0F1830' });
      T(svg, X(q.length - 1), Y(v[q.length - 1]) - 24, Deck.pct(v[q.length - 1]), { 'text-anchor': 'middle', 'font-size': 40, 'font-weight': 700, fill: '#0F1830' });
      T(svg, 0, 560, 'Country is partly filled in at check-in, so its meaning moves.', {});

      var c = $('#calib0', el), cut = '2016-01-01';
      el._draw = function () {
        c.innerHTML = '';
        var rows = D.drift.calib.filter(function (r) { return r.cut === cut && r.algo === 'lr'; });
        var fin = rows.filter(function (r) { return r.variant === 'final features'; })[0], ctry = rows.filter(function (r) { return r.variant !== 'final features'; })[0];
        var yb = lin(0, 0.4, 470, 110);
        T(c, 0, 34, 'Average predicted cancellation rate', { 'font-size': 30, 'font-weight': 700, fill: '#0F1830' });
        [[fin.pred, 'Model used', '#2A5BD7', 120], [ctry.pred, '+ country and guest history', '#C23B3B', 420]].forEach(function (b) {
          S('rect', { x: b[3], y: yb(b[0]), width: 220, height: 470 - yb(b[0]), rx: 12, fill: b[2] }, c);
          T(c, b[3] + 110, yb(b[0]) - 18, Deck.pct(b[0]), { 'text-anchor': 'middle', 'font-size': 44, 'font-weight': 700, fill: '#0F1830' });
          T(c, b[3] + 110, 514, b[1], { 'text-anchor': 'middle', 'font-size': 26 });
        });
        Deck.dash(c, 80, yb(fin.true), 740, yb(fin.true), '#0F1830', 4);
        T(c, 740, yb(fin.true) - 14, 'true rate ' + Deck.pct(fin.true), { 'text-anchor': 'end', 'font-size': 28, 'font-weight': 700, fill: '#0F1830' });
        T(c, 0, 560, 'Logistic regression, tested on every request after the cut.', {});
      };
      Deck.seg($('#driftseg', el), function (k) { cut = k; el._draw(); });
      el._draw();
    }
  });

  /* ---- groups ---- */
  function binom(n, p) { var o = [1]; for (var i = 0; i < n; i++) { var nx = new Array(o.length + 1).fill(0); for (var k = 0; k < o.length; k++) { nx[k] += o[k] * (1 - p); nx[k + 1] += o[k] * p; } o = nx; } return o; }
  function stretch(d, f) { var o = new Array((d.length - 1) * f + 1).fill(0); d.forEach(function (v, k) { o[k * f] = v; }); return o; }
  function conv(a, b) { var o = new Array(a.length + b.length - 1).fill(0); a.forEach(function (x, i) { b.forEach(function (y, j) { o[i + j] += x * y; }); }); return o; }
  function tail(d, f) { var s = 0; for (var k = f + 1; k < d.length; k++) s += d[k]; return s; }
  Deck.slide('s-groups', {
    init: function (el, D) {
      var g = D.groups;
      $('#grpbar', el).innerHTML = '<div style="width:' + (g.all_show * 100) + '%;background:#2A5BD7">' + Deck.pct(g.all_show) + ' all showed up</div><div style="width:' + (g.all_cancel * 100) + '%;background:#C23B3B">' + Deck.pct(g.all_cancel) + ' all cancelled</div><div style="width:' + (g.mixed * 100) + '%;background:#98A1B8"></div>';
      $('#grpcap', el).textContent = Deck.fmt(g.n_groups) + ' groups of identical bookings (' + Deck.pct(g.rows_in_groups) + ' of all rows). Only ' + Deck.pct(g.mixed, 1) + ' had mixed outcomes.';
      var sc = [
        { l: '60 independent bookings', c: '#2A5BD7', d: binom(60, 0.7) },
        { l: '30 singles + 3 groups of 10', c: '#8FA0CC', d: conv(binom(30, 0.7), stretch(binom(3, 0.7), 10)) },
        { l: '3 groups of 20', c: '#C23B3B', d: stretch(binom(3, 0.7), 20), smooth: true }];
      var svg = $('#risk', el), x0 = 100, x1 = 960, top = 20, bot = 400, F0 = 34, F1 = 56, X = lin(F0, F1, x0, x1), Y = lin(0, 1, bot, top);
      yAxis(svg, [0, 0.25, 0.5, 0.75, 1], Y, x0 - 20, function (t) { return Math.round(t * 100) + '%'; });
      for (var f = F0; f <= F1; f += 4) T(svg, X(f), bot + 42, String(f), { 'text-anchor': 'middle' });
      T(svg, x0, bot + 78, 'free rooms that night', {});
      sc.forEach(function (s) {
        var pts = [];
        if (s.smooth) {                                  // the exact curve is a staircase: draw it through a Gaussian window of 1.5 rooms (the readouts stay exact)
          var G = [], gs = 0; for (var j = -5; j <= 5; j++) { var gv = Math.exp(-j * j / (2 * 1.5 * 1.5)); G.push(gv); gs += gv; }
          var sm = function (f) { var a = 0; G.forEach(function (gv, i) { a += gv * tail(s.d, Math.min(Math.max(f + i - 5, 0), s.d.length - 1)); }); return a / gs; };
          for (var u = F0; u <= F1; u += 0.25) { var f0 = Math.floor(u), fr = u - f0, y0 = sm(f0), y1 = sm(f0 + 1); pts.push([X(u), Y(y0 + (y1 - y0) * fr)]); }
        } else for (var f = F0; f <= F1; f++) pts.push([X(f), Y(tail(s.d, f))]);
        S('path', { d: path(pts), fill: 'none', stroke: s.c, 'stroke-width': 6, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
      });
      var vline = Deck.dash(svg, 0, top, 0, bot, '#0F1830', 3);
      var host = $('#riskk', el);
      host.innerHTML = sc.map(function (s, i) { return '<div style="display:flex;align-items:baseline;gap:18px"><b id="rk' + i + '" style="font-size:64px;letter-spacing:-.03em;width:180px;color:' + s.c + '"></b><span style="font-size:28px;color:var(--ink2);white-space:nowrap">' + s.l + '</span></div>'; }).join('');
      var slider = $('#freer', el);
      el._upd = function () {
        var f = +slider.value; $('#freev', el).textContent = f;
        vline.setAttribute('x1', X(f)); vline.setAttribute('x2', X(f));
        sc.forEach(function (s, i) { var p = tail(s.d, f); $('#rk' + i, el).textContent = p < 0.001 ? '<0.1%' : Deck.pct(p, p < 0.1 ? 1 : 0); });
      };
      slider.addEventListener('input', el._upd); el._upd();
    },
    enter: function (el) { $('#freer', el).value = 50; el._upd(); }
  });

  /* ---- personas ---- */
  var PCOL = { 'Online leisure couples': '#3E4C73', 'Families': '#E8602C', 'Tour-operator holidays': '#8FA0CC', 'Contracts / allotments': '#B9C1D3', 'Last-minute direct guests': '#2A5BD7', 'Business / corporate': '#0F1830', 'Groups and agency blocks': '#C23B3B' };
  function labelPlacer() {
    var boxes = [];
    function hit(b) { return boxes.some(function (o) { return b.x < o.x + o.w && b.x + b.w > o.x && b.y < o.y + o.h && b.y + b.h > o.y; }); }
    return {
      block: function (b) { boxes.push(b); },
      place: function (cx, cy, r, w, h, xmin, xmax) {
        var d = r * 0.72;
        var c = [[cx + r + 14, cy - h / 2], [cx - r - 14 - w, cy - h / 2], [cx - w / 2, cy - r - 10 - h], [cx - w / 2, cy + r + 10],
                 [cx + d + 8, cy - d - h - 4], [cx + d + 8, cy + d + 4], [cx - d - 8 - w, cy - d - h - 4], [cx - d - 8 - w, cy + d + 4]];
        for (var i = 0; i < c.length; i++) { var b = { x: c[i][0], y: c[i][1], w: w, h: h }; if (b.x >= xmin && b.x + b.w <= xmax && !hit(b)) { boxes.push(b); return b; } }
        var d = { x: Math.min(c[0][0], xmax - w), y: c[0][1], w: w, h: h }; boxes.push(d); return d;
      }
    };
  }
  Deck.slide('s-personas', {
    init: function (el, D) {
      var svg = $('#pers', el), x0 = 120, x1 = 1640, top = 20, bot = 600, X = lin(0, 0.8, x0, x1), Y = lin(0, 180, bot, top), h = 'Downtown';
      el._draw = function () {
        svg.innerHTML = '';
        yAxis(svg, [0, 60, 120, 180], Y, x0 - 22, function (t) { return '€' + t; });
        [0, 0.2, 0.4, 0.6, 0.8].forEach(function (t) { T(svg, X(t), bot + 42, Math.round(t * 100) + '%', { 'text-anchor': 'middle' }); });
        T(svg, x0, bot + 84, 'cancellation rate  ·  average nightly rate if the guest shows up  ·  dashed curves: equal expected value per night', {});
        [40, 60, 80, 100].forEach(function (ev) {
          var pts = []; for (var x = 0; x <= 0.8; x += 0.01) { var y = ev / (1 - x); if (y > 180) break; pts.push([X(x), Y(y)]); }
          S('path', { d: path(pts), fill: 'none', stroke: '#B9C1D3', 'stroke-width': 3, 'stroke-dasharray': '10 8' }, svg);
          T(svg, pts[pts.length - 1][0] + 8, pts[pts.length - 1][1] + 26, 'EV €' + ev, { 'font-size': 24, fill: '#6B7491' });
        });
        var rows = D.personas[h].slice().sort(function (a, b) { return b.share - a.share; }), pl = labelPlacer();
        rows.forEach(function (p) { var r = 110 * Math.sqrt(p.share / 0.41); pl.block({ x: X(p.cancel) - r, y: Y(p.rate) - r, w: 2 * r, h: 2 * r }); });
        rows.forEach(function (p) {
          var r = 110 * Math.sqrt(p.share / 0.41), cx = X(p.cancel), cy = Y(p.rate);
          var c = S('circle', { cx: cx, cy: cy, r: r, fill: PCOL[p.persona], opacity: 0.92, stroke: '#EEF0F4', 'stroke-width': 3 }, svg);
          Deck.hover(c, '<b>' + p.persona + '</b><br>' + Deck.pct(p.share) + ' of the room-nights requested<br>cancel rate ' + Deck.pct(p.cancel) + '<br>average rate €' + Math.round(p.rate) + '<br>€' + Math.round(p.yield) + ' earned per requested room-night<br>' + Deck.pct(p.late) + ' booked within 30 days');
        });
        rows.forEach(function (p) {
          var r = 110 * Math.sqrt(p.share / 0.41), cx = X(p.cancel), cy = Y(p.rate), words = p.persona.split(' ');
          if (r >= 90) {   /* big bubbles carry their name inside, on two lines */
            var cut = Math.ceil(words.length / 2);
            T(svg, cx, cy - 6, words.slice(0, cut).join(' '), { 'text-anchor': 'middle', 'font-size': 28, 'font-weight': 700, fill: '#F8F9FC' });
            T(svg, cx, cy + 28, words.slice(cut).join(' '), { 'text-anchor': 'middle', 'font-size': 28, 'font-weight': 700, fill: '#F8F9FC' });
            return;
          }
          var b = pl.place(cx, cy, r, p.persona.length * 15.5, 34, x0, x1);
          T(svg, b.x, b.y + 27, p.persona, { 'font-size': 28, 'font-weight': 600, fill: '#0F1830' });
        });
      };
      Deck.seg($('#perseg', el), function (k) { h = k; el._draw(); });
      el._draw();
    }
  });

  /* ---- partner types ---- */
  var TCOL = { 'High-volume online partners': '#2A5BD7', 'Reliable niche agencies': '#6E97F5', 'Mixed tour operators': '#98A1B8', 'Block wholesalers': '#C23B3B' };
  Deck.slide('s-partners', {
    init: function (el, D) {
      var svg = $('#agencies', el), x0 = 110, x1 = 1060, top = 20, bot = 600, X = lin(0, 0.9, x0, x1), Y = lin(0, 2, bot, top), sel = null, dots = [];
      yAxis(svg, [0, 0.5, 1, 1.5, 2], Y, x0 - 22, function (t) { return t.toFixed(1) + '×'; });
      [0, 0.3, 0.6, 0.9].forEach(function (t) { T(svg, X(t), bot + 42, Math.round(t * 100) + '%', { 'text-anchor': 'middle' }); });
      T(svg, x0, bot + 84, 'cancellation rate  ·  revenue per requested room-night against the hotel average', {});
      Deck.dash(svg, x0, Y(1), x1, Y(1), '#4A5470', 3);
      T(svg, x1, Y(1) - 14, 'hotel average', { 'text-anchor': 'end', 'font-size': 26, fill: '#4A5470' });
      D.agencies.slice().sort(function (a, b) { return b.bookings - a.bookings; }).forEach(function (a) {
        var c = S('circle', { cx: X(Math.min(a.cancel, 0.9)), cy: Y(Math.min(a.yield, 2)), r: 6 + 46 * Math.sqrt(a.bookings / 18626), fill: TCOL[a.type], opacity: 0.85, stroke: '#EEF0F4', 'stroke-width': 2, style: 'transition:opacity .3s' }, svg);
        c._t = a.type; dots.push(c);
        Deck.hover(c, '<b>Agency ' + a.agent + ' · ' + a.hotel + '</b><br>' + a.type + '<br>' + Deck.fmt(a.bookings) + ' bookings, cancel rate ' + Deck.pct(a.cancel) + '<br>value index ' + a.yield.toFixed(2) + '×');
      });
      var types = Object.keys(D.partner_types).sort(function (a, b) { return D.partner_types[b].share - D.partner_types[a].share; });
      var host = $('#ptypes', el);
      host.innerHTML = types.map(function (t) {
        var p = D.partner_types[t];
        return '<button type="button" data-t="' + t + '" style="all:unset;cursor:pointer;display:flex;flex-direction:column;gap:6px;transition:opacity .3s"><span style="font-size:30px;font-weight:700"><i style="display:inline-block;width:20px;height:20px;border-radius:50%;margin-right:12px;background:' + TCOL[t] + '"></i>' + t + '</span><span style="font-size:26px;color:var(--ink2);padding-left:32px">' + Deck.pct(p.share) + ' of revenue · cancels ' + Deck.pct(p.cancel) + '</span></button>';
      }).join('');
      host.addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b) return;
        sel = sel === b.dataset.t ? null : b.dataset.t;
        dots.forEach(function (d) { d.style.opacity = !sel || d._t === sel ? 0.85 : 0.12; });
        $$('button', host).forEach(function (x) { x.style.opacity = !sel || x.dataset.t === sel ? 1 : 0.4; });
      });
    }
  });
})();
