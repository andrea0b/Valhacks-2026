/* Results: 2016 replay (scoreboard, year, decision flow, robustness) and the 2017 evaluation. */
(function () {
  var S = Deck.S, T = Deck.T, $ = Deck.$;
  var BLUE = '#2A5BD7', BLT = '#6E97F5', SLATE = '#3E4C73', GREY = '#98A1B8', GREY2 = '#C5CBD8', RED = '#C23B3B', INK = '#0F1830', INK2 = '#4A5470';
  var HOTEL = { Downtown: '#3E4C73', Seaside: '#E8602C' };
  function lin(d0, d1, r0, r1) { return function (v) { return r0 + (v - d0) / (d1 - d0) * (r1 - r0); }; }

  /* ---- scoreboard ---- */
  var win = 2;
  function drawBoard(D) {
    var svg = $('#board'); svg.innerHTML = '';
    var rows = D.replay.table.rows, vals = rows.map(function (r) { return r[1][win]; });
    var max = Math.ceil(Math.max.apply(null, vals) * 1.08), base = 520, Y = lin(0, max, base, 70), bw = 250, gap = 160, x0 = 40;
    var cols = [GREY2, GREY, BLUE, 'none'];
    rows.forEach(function (r, i) {
      var v = r[1][win], x = x0 + i * (bw + gap), y = Y(v), ours = i === 2, oracle = i === 3;
      S('rect', { x: x, y: y, width: bw, height: base - y, rx: 8, fill: oracle ? 'none' : cols[i], stroke: oracle ? INK : 'none', 'stroke-width': 4, 'stroke-dasharray': oracle ? '14 10' : null }, svg);
      T(svg, x + bw / 2, y - 20, v.toFixed(2), { 'text-anchor': 'middle', 'font-size': ours ? 64 : 50, 'font-weight': 700, fill: ours ? '#1E44A8' : INK });
      T(svg, x + bw / 2, base + 50, r[0], { 'text-anchor': 'middle', 'font-size': 30, 'font-weight': ours ? 700 : 600, fill: INK });
    });
    S('line', { x1: 0, x2: 1640, y1: base, y2: base, stroke: GREY2, 'stroke-width': 3 }, svg);
    T(svg, 0, 28, 'net revenue, million euros', { 'font-size': 26 });
    var none = vals[0], classic = vals[1], ours = vals[2], oracle = vals[3];
    $('#boardNote').innerHTML = '<span class="hl">+' + Math.round((ours / classic - 1) * 100) + '%</span> over classic overbooking, closing <span class="hl">' + Math.round((ours - classic) / (oracle - classic) * 100) + '%</span> of the gap to perfect foresight';
  }
  Deck.slide('s-board', {
    init: function (el, D) { Deck.seg($('#seg-board', el), function (k) { win = +k; drawBoard(D); }); drawBoard(D); },
    enter: function (el, D) { drawBoard(D); }
  });

  /* ---- the year ---- */
  var yh = 'Downtown';
  function drawYear(D) {
    var svg = $('#year'); svg.innerHTML = '';
    var Y0 = D.replay.year[yh], n = Y0.occ.length, x0 = 90, x1 = 1660, top = 40, bot = 430;
    var X = lin(0, n - 1, x0, x1), Y = lin(0, 1.1, bot, top), col = HOTEL[yh];
    [0, 0.5, 1].forEach(function (t) { T(svg, x0 - 20, Y(t) + 9, Deck.pct(t), { 'text-anchor': 'end', fill: '#6B7491' }); });
    var start = new Date(Y0.start + 'T00:00:00'), M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    for (var m = 0; m < 12; m++) { var i = Math.round((new Date(start.getFullYear(), m, 1) - start) / 864e5); if (i >= 0) T(svg, X(i), bot + 36, M[m], { 'font-size': 24 }); }
    var area = 'M' + X(0) + ' ' + bot; Y0.occ.forEach(function (v, i) { area += 'L' + X(i).toFixed(1) + ' ' + Y(Math.min(v, 1.1)).toFixed(1); }); area += 'L' + X(n - 1) + ' ' + bot + 'Z';
    S('path', { d: area, fill: col, opacity: 0.22 }, svg);
    var line = ''; Y0.occ.forEach(function (v, i) { line += (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(Math.min(v, 1.1)).toFixed(1); });
    S('path', { d: line, fill: 'none', stroke: col, 'stroke-width': 3, 'stroke-linejoin': 'round' }, svg);
    Deck.dash(svg, x0, Y(1), x1, Y(1), INK, 3);
    T(svg, x1, Y(1) - 14, 'every room seated', { 'text-anchor': 'end', 'font-size': 26, 'font-weight': 600, fill: INK });
    Y0.walk.forEach(function (w, i) { if (w > 0) S('rect', { x: X(i) - 3, y: bot + 58, width: 6, height: Math.min(w, 20) * 2.4, rx: 2, fill: RED }, svg); });
    T(svg, x0, bot + 140, 'guests walked on the night', { 'font-size': 24, fill: RED });
    var cw = (x1 - x0) / n;
    Y0.occ.forEach(function (v, i) {
      var r = S('rect', { x: X(i) - cw / 2, y: top, width: cw, height: bot - top + 80, fill: 'transparent' }, svg);
      Deck.hover(r, function () { var d = new Date(start.getTime() + i * 864e5); return '<b>' + d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }) + '</b><br>' + Deck.pct(v) + ' of the rooms seated' + (Y0.walk[i] ? '<br><b style="color:#F3DCDC">' + Y0.walk[i] + ' walked</b>' : ''); });
    });
    $('#yOcc').textContent = Deck.pct(Y0.occ.reduce(function (s, v) { return s + Math.min(v, 1); }, 0) / n);
    $('#yWalk').textContent = Deck.fmt(Y0.walk.reduce(function (s, v) { return s + v; }, 0));
    $('#yPen').textContent = Deck.pct(D.replay.fy.penalty / D.replay.fy.revenue, 1);
  }
  Deck.slide('s-year', {
    init: function (el, D) { Deck.seg($('#seg-year', el), function (k) { yh = k; drawYear(D); }); drawYear(D); }
  });

  /* ---- decision flow ---- */
  Deck.slide('s-flow', {
    init: function (el, D) {
      var svg = $('#flow'), f = D.replay.flow;
      var order = [['accepted', 'Accepted', BLUE], ['price', 'Rate below the bid price', GREY], ['full', 'Night already full', GREY], ['capacity', 'Would exceed capacity', GREY], ['invalid', 'Zero rate or outside the year', GREY2]];
      var total = 0; order.forEach(function (o) { total += f[o[0]].n; });
      var X = lin(0, f.accepted.n, 0, 560);
      order.forEach(function (o, i) {
        var d = f[o[0]], y = 30 + i * 112, w = X(d.n), cw = X(d.cancelled);
        T(svg, 640, y + 56, o[1], { 'text-anchor': 'end', 'font-size': 32, 'font-weight': o[0] === 'accepted' ? 700 : 600, fill: INK });
        var g = S('g', { transform: 'translate(700 0)' }, svg);
        S('rect', { x: 0, y: y, width: w, height: 72, rx: 8, fill: o[2] }, g);
        S('rect', { x: w - cw, y: y, width: cw, height: 72, rx: 8, fill: RED }, g);
        S('rect', { x: w - cw - 8, y: y, width: 16, height: 72, fill: o[2] }, g); S('rect', { x: w - cw, y: y, width: 8, height: 72, fill: RED }, g);
        var lab = T(svg, 700 + w + 20, y + 50, Deck.fmt(d.n), { 'font-size': 40, 'font-weight': 700, fill: INK });
        var tsp = S('tspan', { dx: 22, 'font-size': 26, 'font-weight': 400, fill: RED }, lab); tsp.textContent = Deck.pct(d.cancelled / d.n) + ' cancelled';
        var hit = S('rect', { x: 700, y: y, width: 960, height: 72, fill: 'transparent' }, svg);
        Deck.hover(hit, '<b>' + o[1] + '</b><br>' + Deck.fmt(d.n) + ' requests, ' + Deck.fmt(d.cancelled) + ' of them would have cancelled');
      });
      var rej = total - f.accepted.n;
      $('#flowNote').innerHTML = Deck.fmt(total) + ' requests in the second half of 2016; ' + Deck.fmt(rej) + ' (' + Deck.pct(rej / total) + ') were refused. Red: guests who cancelled anyway, known only afterwards.';
    }
  });

  /* ---- robustness ---- */
  var rw = 'FY';
  var CFG = [['lr', 'Logistic regression', GREY], ['lgb', 'LightGBM', SLATE], ['stack_lr_lgb_cb', 'Stack of three (shipped)', BLUE]];
  function drawRobust(D) {
    var svg = $('#robust'); svg.innerHTML = '';
    var rows = D.policy.finalists.filter(function (r) { return r.window === rw; });
    var lo = Math.min.apply(null, rows.map(function (r) { return r.min; })), hi = Math.max.apply(null, rows.map(function (r) { return r.max; }));
    var pad = (hi - lo) * 0.15; lo -= pad; hi += pad;
    var x0 = 130, x1 = 1600, top = 120, bot = 550, X = lin(-0.2, 0.2, x0, x1), Y = lin(lo, hi, bot, top);
    var tk = 5, step = (hi - lo) / tk;
    for (var i = 0; i <= tk; i++) { var v = lo + i * step; T(svg, x0 - 20, Y(v) + 9, v.toFixed(2), { 'text-anchor': 'end', fill: '#6B7491' }); }
    [-0.2, -0.1, 0, 0.1, 0.2].forEach(function (s) { T(svg, X(s), bot + 44, (s > 0 ? '+' : '') + s.toFixed(1), { 'text-anchor': 'middle', fill: '#6B7491' }); });
    T(svg, x0, bot + 92, 'logit shift added to every probability', { 'font-size': 26 });
    Deck.dash(svg, X(0), top - 20, X(0), bot, INK, 3);
    T(svg, X(0), top - 30, 'shipped: no shift', { 'text-anchor': 'middle', 'font-size': 26, 'font-weight': 700, fill: INK });
    CFG.slice().sort(function (a, b) { return (a[0] === 'stack_lr_lgb_cb') - (b[0] === 'stack_lr_lgb_cb'); }).forEach(function (c) {
      var pts = rows.filter(function (r) { return r.config === c[0]; }).sort(function (a, b) { return a.shift - b.shift; });
      if (!pts.length) return;
      var ours = c[0] === 'stack_lr_lgb_cb';
      if (ours) { var band = pts.map(function (p, i) { return (i ? 'L' : 'M') + X(p.shift).toFixed(1) + ' ' + Y(p.max).toFixed(1); }).join('') + pts.slice().reverse().map(function (p) { return 'L' + X(p.shift).toFixed(1) + ' ' + Y(p.min).toFixed(1); }).join('') + 'Z'; S('path', { d: band, fill: BLUE, opacity: 0.18 }, svg); }
      var d = pts.map(function (p, i) { return (i ? 'L' : 'M') + X(p.shift).toFixed(1) + ' ' + Y(p.mean).toFixed(1); }).join('');
      S('path', { d: d, fill: 'none', stroke: c[2], 'stroke-width': ours ? 9 : 5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
      pts.forEach(function (p) { var dot = S('circle', { cx: X(p.shift), cy: Y(p.mean), r: ours ? 11 : 7, fill: c[2] }, svg); Deck.hover(dot, '<b>' + c[1] + '</b>, shift ' + p.shift + '<br>' + p.mean.toFixed(3) + ' M€ (' + p.min.toFixed(3) + ' to ' + p.max.toFixed(3) + ')'); });
    });
    CFG.forEach(function (c, i) {
      var x = 10 + i * 275;
      S('circle', { cx: x, cy: 22, r: 9, fill: c[2] }, svg);
      T(svg, x + 18, 31, c[1].replace(' (shipped)', ''), { 'font-size': 22, 'font-weight': c[0] === 'stack_lr_lgb_cb' ? 700 : 500, fill: INK });
    });
  }
  Deck.slide('s-robust', {
    init: function (el, D) { Deck.seg($('#seg-robust', el), function (k) { rw = k; drawRobust(D); }); drawRobust(D); }
  });

  /* ---- 2017 evaluation ---- */
  Deck.slide('s-evaluator', {
    init: function (el, D) {
      var svg = $('#evaluator'), O = D.evaluator, by = {}; O.rows.forEach(function (r) { by[r.key] = r; });
      var base = 560, Y = lin(0, 6000000, base, 60), bw = 280, gap = 120, x0 = 40;
      var bars = [['no_overbooking', 'No overbooking', '#4A5470'], ['average_rate', 'Classic overbooking', '#A3ADCB'], ['model', 'This system', BLT]];
      bars.forEach(function (b, i) {
        var v = by[b[0]].net, x = x0 + i * (bw + gap), y = Y(v), ours = i === 2;
        S('rect', { x: x, y: y, width: bw, height: base - y, rx: 8, fill: b[2] }, svg);
        T(svg, x + bw / 2, y - 20, '€' + (v / 1e6).toFixed(2) + 'M', { 'text-anchor': 'middle', 'font-size': ours ? 56 : 44, 'font-weight': 700, fill: '#EEF0F4' });
        T(svg, x + bw / 2, base + 50, b[1], { 'text-anchor': 'middle', 'font-size': 28, 'font-weight': ours ? 700 : 500, fill: '#EEF0F4' });
      });
      S('line', { x1: 0, x2: 1640, y1: base, y2: base, stroke: '#4A5470', 'stroke-width': 3 }, svg);
      var cx = x0 + 2 * (bw + gap);
      var c1 = S('g', {}, svg); S('rect', { x: cx + bw + 30, y: Y(by.model.net) + 30, width: 250, height: 60, rx: 30, fill: BLT }, c1);
      T(c1, cx + bw + 155, Y(by.model.net) + 71, '+' + (O.vs_classic * 100).toFixed(1) + '% vs classic', { 'text-anchor': 'middle', 'font-size': 26, 'font-weight': 700, fill: INK });
      var c2 = S('g', {}, svg); S('rect', { x: cx + bw + 30, y: Y(by.model.net) + 104, width: 250, height: 60, rx: 30, fill: 'none', stroke: BLT, 'stroke-width': 3 }, c2);
      T(c2, cx + bw + 155, Y(by.model.net) + 145, '+' + (O.vs_none * 100).toFixed(1) + '% vs none', { 'text-anchor': 'middle', 'font-size': 26, 'font-weight': 700, fill: '#EEF0F4' });
      $('#offNote').textContent = 'The organisers’ evaluator on the 2017 test year, run on the submitted solution. The recipe was chosen on the 2016 replay; 2017 was not used to choose or tune it.';
    }
  });
})();
