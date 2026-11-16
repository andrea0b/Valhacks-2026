/* Model: validation, ablations, calibration, stack weights, drivers. Data: presentation/build/data.json (data.py). */
(function () {
  var S = Deck.S, T = Deck.T, $ = Deck.$;
  var BLUE = '#2A5BD7', SLATE = '#3E4C73', GREY = '#98A1B8', GREY2 = '#C5CBD8', RED = '#C23B3B', INK = '#0F1830', INK2 = '#4A5470';
  function lin(d0, d1, r0, r1) { return function (v) { return r0 + (v - d0) / (d1 - d0) * (r1 - r0); }; }
  function mean(a) { return a.reduce(function (s, v) { return s + v; }, 0) / a.length; }
  var NAMES = { lr: 'Logistic regression', lgb: 'LightGBM', cb: 'CatBoost', avg3: 'Average of three', stack3: 'Stack of three' };
  var SHORT = { lr: 'LR', lgb: 'LightGBM', cb: 'CatBoost', avg3: 'Average', stack3: 'Stack' };

  /* ---- shuffled vs temporal ---- */
  var honestKey = 'final features';
  function drawHonest(D) {
    var svg = $('#honest'); svg.innerHTML = '';
    var rows = D.model.random_vs_time.filter(function (r) { return r.features === honestKey; });
    var rand = rows.filter(function (r) { return /random/.test(r.validation); })[0];
    var temp = rows.filter(function (r) { return /temporal/.test(r.validation); });
    var base = 560, top = 80, Y = lin(0.5, 0.92, base, top), bw = 150;
    [0.6, 0.7, 0.8, 0.9].forEach(function (t) { T(svg, 76, Y(t) + 9, t.toFixed(1), { 'text-anchor': 'end', fill: '#6B7491' }); });
    S('line', { x1: 100, x2: 1100, y1: base, y2: base, stroke: GREY2, 'stroke-width': 3 }, svg);
    var xs = [150, 520, 720, 920], bars = [{ x: xs[0], r: rand, c: GREY, ink: INK2, lab: 'shuffled' }];
    temp.forEach(function (r, i) { bars.push({ x: xs[i + 1], r: r, c: BLUE, ink: '#1E44A8', lab: r.validation.replace('temporal cut ', 'cut ').replace('2016-01-01', '1 Jan').replace('2016-04-01', '1 Apr').replace('2016-07-01', '1 Jul') }); });
    Deck.dash(svg, 150 + bw, Y(rand.auc), 1100, Y(rand.auc), INK, 3);
    bars.forEach(function (b) {
      var y = Y(b.r.auc);
      S('rect', { x: b.x, y: y, width: bw, height: base - y, rx: 6, fill: b.c }, svg);
      T(svg, b.x + bw / 2, y - 18, b.r.auc.toFixed(3), { 'text-anchor': 'middle', 'font-size': 40, 'font-weight': 700, fill: b.ink });
      T(svg, b.x + bw / 2, base + 46, b.lab, { 'text-anchor': 'middle', 'font-size': 30, 'font-weight': 600 });
    });
    T(svg, 520, 36, 'next months, unseen', { 'font-size': 30, 'font-weight': 700, fill: '#1E44A8' });
    T(svg, 150, 36, 'random folds', { 'font-size': 30, 'font-weight': 700, fill: INK2 });
    $('#kRand').textContent = rand.auc.toFixed(2);
    $('#kTime').textContent = mean(temp.map(function (r) { return r.auc; })).toFixed(2);
  }
  Deck.slide('s-honest', {
    init: function (el, D) {
      Deck.seg($('#seg-honest', el), function (k) { honestKey = k; drawHonest(D); });
      drawHonest(D);
    },
    enter: function (el, D) { drawHonest(D); }
  });

  /* ---- ablations ---- */
  var triedAlgo = 'lr';
  function drawTried(D) {
    var svg = $('#tried'); svg.innerHTML = '';
    var rows = D.model.ablations.filter(function (a) { return a.algo === triedAlgo; }), by = {};
    rows.forEach(function (a) { (by[a.variant] = by[a.variant] || []).push(a.logloss); });
    var base = mean(by['final features']);
    var order = [
      ['+ country and guest history', 'Add country and guest history', 'bad'],
      ['half-life 3 months', 'Forget faster (half-life 3 months)', 'flat'],
      ['no recency weights', 'No recency weights', 'flat'],
      ['half-life 12 months', 'Forget slower (half-life 12 months)', 'flat'],
      ['+ special requests', 'Add special requests', 'na'],
      ['+ all post-booking columns', 'Add every post-booking column', 'na']];
    var x0 = 700, x1 = 1450, X = lin(-0.06, 0.32, x0, x1), y0 = 100, dy = 90;
    var zero = X(0);
    Deck.dash(svg, zero, 56, zero, 610, INK, 3);
    T(svg, zero, 38, 'final features', { 'text-anchor': 'middle', 'font-size': 26, 'font-weight': 700, fill: INK });
    order.forEach(function (o, i) {
      var d = mean(by[o[0]]) - base, y = y0 + i * dy + 30, col = o[2] === 'bad' ? RED : o[2] === 'na' ? GREY : SLATE;
      T(svg, 660, y + 10, o[1], { 'text-anchor': 'end', 'font-size': 30, 'font-weight': 600, fill: INK });
      S('line', { x1: zero, x2: X(Math.min(d, 0.32)), y1: y, y2: y, stroke: col, 'stroke-width': 8, 'stroke-linecap': 'round' }, svg);
      S('circle', { cx: X(Math.min(d, 0.32)), cy: y, r: 17, fill: o[2] === 'na' ? '#EEF0F4' : col, stroke: col, 'stroke-width': 6 }, svg);
      var lab = (d > 0 ? '+' : '') + d.toFixed(3), right = false;
      T(svg, X(Math.min(d, 0.32)) + (right ? -30 : 38), y + 11, lab, { 'text-anchor': right ? 'end' : 'start', 'font-size': 32, 'font-weight': 700, fill: o[2] === 'bad' ? RED : INK });
      if (o[2] === 'na') T(svg, 1670, y + 9, 'not known at request time', { 'text-anchor': 'end', 'font-size': 24, fill: '#6B7491' });
    });
  }
  Deck.slide('s-tried', {
    init: function (el, D) { Deck.seg($('#seg-tried', el), function (k) { triedAlgo = k; drawTried(D); }); drawTried(D); },
    enter: function (el, D) { drawTried(D); }
  });

  /* ---- calibration ---- */
  var calKey = 'stack3';
  function drawCalib(D) {
    var svg = $('#calib'); svg.innerHTML = '';
    var x0 = 110, x1 = 940, y0 = 40, y1 = 600, X = lin(0, 0.65, x0, x1), Y = lin(0, 0.65, y1, y0);
    [0, 0.2, 0.4, 0.6].forEach(function (t) {
      T(svg, x0 - 22, Y(t) + 9, Deck.pct(t), { 'text-anchor': 'end', fill: '#6B7491' });
      T(svg, X(t), y1 + 44, Deck.pct(t), { 'text-anchor': 'middle', fill: '#6B7491' });
    });
    S('line', { x1: x0, x2: x1, y1: y1, y2: y1, stroke: GREY2, 'stroke-width': 3 }, svg);
    Deck.dash(svg, X(0), Y(0), X(0.65), Y(0.65), INK, 3);
    T(svg, X(0.5) + 16, Y(0.47), 'perfect', { 'font-size': 26, 'font-weight': 600, fill: INK });
    var pts = D.model.calibration[calKey];
    S('path', { d: pts.map(function (p, i) { return (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1); }).join(''), fill: 'none', stroke: BLUE, 'stroke-width': 8, 'stroke-linejoin': 'round' }, svg);
    pts.forEach(function (p) {
      var c = S('circle', { cx: X(p[0]), cy: Y(p[1]), r: 12, fill: BLUE }, svg);
      Deck.hover(c, function () { return 'Predicted <b>' + Deck.pct(p[0], 1) + '</b>, observed <b>' + Deck.pct(p[1], 1) + '</b>'; });
    });
    T(svg, x0, y1 + 92, 'predicted cancellation probability, ten equal-size groups (July cut)', { 'font-size': 26 });
    T(svg, x0 - 100, 18, 'observed', { 'font-size': 26 });
    // log-loss bars
    var s2 = $('#calib-ll'); s2.innerHTML = '';
    var rows = D.model.algorithms.filter(function (a) { return a.cut === '2016-07-01'; });
    var lo = 0.49, hi = 0.525, BX = lin(lo, hi, 240, 640);
    T(s2, 240, 30, 'log-loss, July cut (lower is better)', { 'font-size': 26, 'font-weight': 600 });
    rows.forEach(function (r, i) {
      var y = 70 + i * 82, on = r.recipe === calKey;
      T(s2, 220, y + 36, SHORT[r.recipe], { 'text-anchor': 'end', 'font-size': 28, 'font-weight': on ? 700 : 500, fill: on ? INK : INK2 });
      S('rect', { x: 240, y: y, width: BX(r.logloss) - 240, height: 52, rx: 6, fill: on ? BLUE : GREY2 }, s2);
      T(s2, BX(r.logloss) + 12, y + 37, r.logloss.toFixed(3), { 'font-size': 28, 'font-weight': 700, fill: on ? '#1E44A8' : INK2 });
    });
  }
  Deck.slide('s-calib', {
    init: function (el, D) {
      var host = $('#pills-calib', el);
      ['lr', 'lgb', 'cb', 'avg3', 'stack3'].forEach(function (k) {
        var b = document.createElement('button'); b.type = 'button'; b.className = 'pill' + (k === calKey ? ' on' : ''); b.textContent = NAMES[k]; b.dataset.k = k; host.appendChild(b);
      });
      host.addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b) return; calKey = b.dataset.k;
        Deck.$$('button', host).forEach(function (x) { x.classList.toggle('on', x === b); }); drawCalib(D);
      });
      drawCalib(D);
    }
  });

  /* ---- stack weights ---- */
  Deck.slide('s-stack', {
    init: function (el, D) {
      var svg = $('#stackw'), x0 = 420, x1 = 1560, X = lin(-0.1, 0.8, x0, x1), cuts = D.model.stack_weights, mem = ['lr', 'lgb', 'cb'];
      var cols = ['#C5CBD8', '#98A1B8', BLUE, INK], lab = ['1 Jan', '1 Apr', '1 Jul'];
      [0, 0.2, 0.4, 0.6, 0.8].forEach(function (t) { T(svg, X(t), 520, t.toFixed(1), { 'text-anchor': 'middle', fill: '#6B7491' }); });
      Deck.dash(svg, X(0), 50, X(0), 490, INK, 3);
      T(svg, X(0), 34, 'no weight', { 'text-anchor': 'middle', 'font-size': 24, 'font-weight': 600, fill: INK });
      mem.forEach(function (m, i) {
        var y = 110 + i * 100, v = cuts.map(function (c) { return c[m]; }), lo = Math.min.apply(null, v), hi = Math.max.apply(null, v);
        T(svg, 380, y + 10, NAMES[m], { 'text-anchor': 'end', 'font-size': 32, 'font-weight': 600, fill: INK });
        S('line', { x1: X(lo), x2: X(hi), y1: y, y2: y, stroke: m === 'cb' ? BLUE : GREY2, 'stroke-width': 14, 'stroke-linecap': 'round', opacity: 0.6 }, svg);
        v.forEach(function (w, j) {
          var c = S('circle', { cx: X(w), cy: y, r: 17, fill: m === 'cb' ? BLUE : SLATE, stroke: '#EEF0F4', 'stroke-width': 4 }, svg);
          Deck.hover(c, function () { return '<b>' + NAMES[m] + '</b>, cut ' + lab[j] + ': weight ' + w.toFixed(2); });
        });
        if (m === 'cb' || m === 'lgb') T(svg, X(hi) + 36, y + 11, lo.toFixed(2) + ' to ' + hi.toFixed(2), { 'font-size': 30, 'font-weight': 700, fill: m === 'cb' ? '#1E44A8' : INK2 });
      });
      T(svg, x0, 556, 'weight in the meta-model, one dot per temporal cut (1 Jan, 1 Apr, 1 Jul 2016)', { 'font-size': 26 });
    }
  });

  /* ---- drivers ---- */
  var openTheme = null;
  function drawThemes(D) {
    var host = $('#themePills');
    if (!host.children.length) {
      ['All'].concat(Object.keys(D.model.themes)).forEach(function (t) {
        var b = document.createElement('button'); b.type = 'button'; b.className = 'pill'; b.dataset.k = t === 'All' ? '' : t;
        b.textContent = t === 'All' ? 'All inputs' : t; b.style.cssText = 'font-size:22px;padding:10px 16px;white-space:nowrap;flex:none'; host.appendChild(b);
      });
      host.addEventListener('click', function (e) { var b = e.target.closest('button'); if (!b) return; openTheme = b.dataset.k || null; drawThemes(D); });
    }
    Deck.$$('button', host).forEach(function (b) { b.classList.toggle('on', (b.dataset.k || null) === openTheme); });
    var svg = $('#themes'); svg.innerHTML = '';
    var cols = D.model.columns.filter(function (c) { return !openTheme || c.theme === openTheme; }).slice(0, 20), mx = D.model.columns[0].share;
    var colW = 820, lab = 420, bw = 270, row = 66;
    function short(l) { return l.replace('identical requests already seen (group)', 'identical requests seen').replace("agent's historical cancel rate", 'agent cancel history').replace('similar requests the same day', 'similar requests that day').replace('requests already seen for the week', 'requests seen for the week').replace('requests already seen for the night', 'requests seen for the night').replace('requests from the same agent that day', 'same-agent requests that day'); }
    cols.forEach(function (c, i) {
      var col = i < 10 ? 0 : 1, r = i % 10, x = col * (colW + 40), y = 10 + r * row, w = Math.max(4, c.share / mx * bw);
      T(svg, x, y + 36, String(i + 1), { 'font-size': 24, fill: '#6B7491' });
      T(svg, x + 44, y + 36, short(c.label), { 'font-size': 28, fill: INK });
      S('rect', { x: x + 44 + lab, y: y + 8, width: w, height: 38, rx: 6, fill: BLUE }, svg);
      T(svg, x + 44 + lab + w + 12, y + 37, Deck.pct(c.share, 1), { 'font-size': 26, 'font-weight': 700, fill: '#1E44A8' });
      var hit = S('rect', { x: x, y: y, width: colW - 20, height: row - 6, fill: 'transparent' }, svg);
      Deck.hover(hit, '<b>' + c.label + '</b><br>' + c.theme + ': ' + Deck.pct(c.share, 1) + ' of the forecast');
    });
  }
  Deck.slide('s-drivers', {
    init: function (el, D) { drawThemes(D); },
    enter: function (el, D) { openTheme = null; drawThemes(D); }
  });
})();
