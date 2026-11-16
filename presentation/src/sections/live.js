/* Live: the exported replay (every decision of the Python policy, 1 Jul - 11 Aug 2016) and the real model
   running in the browser (model.js). Both need model.json and live.json; without them the slides stay empty. */
(function () {
  var S = Deck.S, T = Deck.T, $ = Deck.$;
  var BLUE = '#2A5BD7', SLATE = '#3E4C73', GREY2 = '#C5CBD8', RED = '#C23B3B', INK = '#0F1830';
  var DOT = ['#8FA0D6', '#E8602C'];
  var L = Deck.LIVE, HM = null;
  function lin(d0, d1, r0, r1) { return function (v) { return r0 + (v - d0) / (d1 - d0) * (r1 - r0); }; }
  function dshort(s) { return new Date(s + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }); }
  function drivers(list, dark) {
    var mx = Math.max.apply(null, list.map(function (d) { return Math.abs(d[1]); }).concat([0.5]));
    return list.map(function (d) {
      var left = d[1] < 0, w = Math.abs(d[1]) / mx * 50, col = left ? (dark ? '#6E97F5' : BLUE) : RED;
      return '<div class="d"><span>' + d[0].replace(' (group)', '').replace('identical requests already seen', 'identical requests seen') + '</span><div class="bar"><u></u><i style="background:' + col + ';' + (left ? 'right:50%' : 'left:50%') + ';width:' + w + '%"></i></div></div>';
    }).join('');
  }
  var OUT = { accepted: 'accepted', price: 'too cheap', full: 'night full', capacity: 'over capacity', invalid: 'invalid' };

  /* ---------- replay console ---------- */
  var idx = 0, playing = true, speed = 10, sel = -1, timer = null, counts = { accepted: 0, rejected: 0, price: 0, full: 0, capacity: 0 };
  var ROWS = 6;
  function rowHtml(r, i) {
    var acc = r.accepted;
    return '<div class="r' + (i === sel ? ' sel' : '') + '" data-i="' + i + '"><span class="dot" style="background:' + DOT[r.hotel] + '"></span>' +
      '<span>' + r.nights + ' night' + (r.nights > 1 ? 's' : '') + ' from ' + dshort(r.arrival) + ' · €' + Math.round(r.rate) + ' · ' + r.segment + '</span>' +
      '<span class="p">' + Deck.pct(r.p) + '</span><span class="chip ' + (acc ? 'acc' : 'rej') + '">' + OUT[r.outcome] + '</span></div>';
  }
  function showDetail(i) {
    var r = L.requests[i], d = $('#detail'); if (!r) { d.innerHTML = ''; return; }
    var full = r.bid === null, minFree = r.free ? Math.min.apply(null, r.free) : null, q = 1 - r.p;
    d.innerHTML = '<h3>Why this decision</h3>' +
      '<p class="k"><b>' + L.hotels[r.hotel].replace(' Hotel', '') + '</b> · booked ' + dshort(r.booked) + ' for ' + dshort(r.arrival) + '</p>' +
      '<p class="k"><span>rate</span> €' + Math.round(r.rate) + ' <span>against bid price</span> ' + (r.outcome === 'invalid' ? 'n/a' : full ? '∞ (night full)' : '€' + Math.round(r.bid)) + '</p>' +
      '<p class="k"><span>expected guest</span> ' + q.toFixed(2) + ' <span>against free rooms</span> ' + (minFree === null ? 'n/a' : (minFree < 0 ? '0' : minFree.toFixed(1))) + '</p>' +
      '<div style="height:24px"></div>' +
      (r.drivers ? '<div class="drv">' + drivers(r.drivers.slice(0, 3), true) + '</div>' : '');
  }
  function paint() {
    var feed = $('#feed'), from = Math.max(0, idx - ROWS), html = '';
    for (var i = idx - 1; i >= from; i--) html += rowHtml(L.requests[i], i);
    feed.innerHTML = html;
    var r = L.requests[Math.max(idx - 1, 0)];
    $('#cDay').textContent = idx ? new Date(r.booked + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '1 Jul 2016';
    $('#cCount').textContent = Deck.fmt(idx) + ' requests · ' + Deck.fmt(counts.accepted) + ' accepted · ' + Deck.fmt(idx - counts.accepted) + ' refused';
    $('#cScrub').value = idx;
    showDetail(sel >= 0 ? sel : idx - 1);
  }
  function recount(to) {
    counts = { accepted: 0, rejected: 0, price: 0, full: 0, capacity: 0 };
    for (var i = 0; i < to; i++) { var o = L.requests[i].outcome; if (counts[o] !== undefined) counts[o]++; }
  }
  function tick() {
    var el = $('#s-console');
    if (!el.classList.contains('on')) { stop(); return; }
    if (!playing) return;
    var step = speed === 1 ? 1 : speed === 10 ? 3 : 15;
    for (var k = 0; k < step && idx < L.requests.length; k++) { var o = L.requests[idx].outcome; if (counts[o] !== undefined) counts[o]++; idx++; }
    if (idx >= L.requests.length) { playing = false; $('#cPlay').textContent = 'Replay'; }
    paint();
  }
  function start() { stop(); timer = setInterval(tick, 130); }
  function stop() { if (timer) clearInterval(timer); timer = null; }
  Deck.slide('s-console', {
    init: function (el) {
      if (!L) return;
      $('#cScrub').min = 0; $('#cScrub').max = L.requests.length; $('#cScrub').step = 1;
      $('#cPlay', el).addEventListener('click', function () {
        if (idx >= L.requests.length) { idx = 0; recount(0); sel = -1; playing = true; } else playing = !playing;
        this.textContent = playing ? 'Pause' : 'Play'; paint();
      });
      Deck.seg($('#cSpeed', el), function (k) { speed = +k; });
      $('#cScrub').addEventListener('input', function () { idx = +this.value; recount(idx); sel = -1; paint(); });
      $('#feed').addEventListener('click', function (e) {
        var r = e.target.closest('.r'); if (!r) return; sel = +r.dataset.i; playing = false; $('#cPlay').textContent = 'Play'; paint();
      });
    },
    enter: function () {
      if (!L) return;
      idx = 0; sel = -1; playing = true; recount(0); $('#cPlay').textContent = 'Pause'; paint(); start();
    }
  });

  /* ---------- try a request ---------- */
  var TS = { hotel: 0, day: 12, lead: 60, nights: 3, rate: 140, segment: 'Online TA' }, CH = {}, GT = {};
  function setup() {
    if (HM || !L || !Deck.MODEL || !window.HotelModel) return;
    HM = window.HotelModel.load(Deck.MODEL, L);
    var cnt = {}; L.requests.forEach(function (r) {
      var k = r.segment; cnt[k] = cnt[k] || { ch: {}, gt: {} }; cnt[k].ch[r.channel] = (cnt[k].ch[r.channel] || 0) + 1; cnt[k].gt[r.guest] = (cnt[k].gt[r.guest] || 0) + 1;
    });
    function top(o) { return Object.keys(o).sort(function (a, b) { return o[b] - o[a]; })[0]; }
    Object.keys(cnt).forEach(function (k) { CH[k] = top(cnt[k].ch); GT[k] = top(cnt[k].gt); });
  }
  function wkend(arrMs, n) { var w = 0; for (var i = 0; i < n; i++) { var d = (new Date(arrMs + i * 864e5).getUTCDay() + 6) % 7; if (d >= 5) w++; } return w; }
  function run() {
    if (!HM) return;
    var t = TS.day, bookMs = HM.start + t * 864e5, bookISO = window.HotelModel.iso(bookMs), nDays = L.days.length;
    var maxLead = nDays - 1 - t - TS.nights + 1;
    var lead = Math.min(TS.lead, Math.max(0, maxLead)), arrMs = bookMs + lead * 864e5, def = L.defaults[L.hotels[TS.hotel]];
    var seg = TS.segment, ta = /TA/.test(seg) || seg === 'Groups';
    var b = { hotel: L.hotels[TS.hotel], booking_date: bookISO, arrival_date: window.HotelModel.iso(arrMs), nights: TS.nights, weekend_nights: wkend(arrMs, TS.nights),
      nightly_rate: TS.rate, days_ahead: lead, adults: def.adults, children: 0, babies: 0, sales_segment: seg, sales_channel: CH[seg] || def.sales_channel,
      guest_type: GT[seg] || def.guest_type, meal: def.meal, room_type: def.room_type, agent: ta ? def.agent : null, company: null };
    var o = HM.decide(b);
    function dd(ms) { return new Date(ms).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }); }
    $('#tDayL').textContent = 'Request on ' + dd(bookMs);
    $('#tLeadL').textContent = 'Stay from ' + dd(arrMs);
    $('#tNightsL').textContent = TS.nights + ' night' + (TS.nights > 1 ? 's' : '');
    $('#tRateL').textContent = '€' + TS.rate + ' a night';
    $('#tP').textContent = Deck.pct(o.p);
    var chip = $('#tChip'); chip.className = 'chip ' + (o.accepted ? 'ok' : 'no'); chip.textContent = o.accepted ? 'accept' : 'reject';
    var why;
    if (o.invalid) why = 'out of range';
    else if (!o.okValue) why = o.outcome === 'full' ? 'night full' : '€' + o.rate + ' < bid €' + Math.round(o.bid);
    else if (!o.okRisk) why = 'no room left';
    else why = '€' + o.rate + ' ≥ bid €' + Math.round(o.bid);
    $('#tWhy').textContent = why;
    chart(o, t, lead);
  }
  function chart(o, t, lead) {
    var svg = $('#tChart'); svg.innerHTML = '';
    var h = L.snapshots[t].hotels[TS.hotel], nDays = L.days.length, span = Math.min(150, nDays - t), x0 = 90, x1 = 880, top = 90, bot = 470, ymax = 300;
    var X = lin(0, span - 1, x0, x1), Y = lin(0, ymax, bot, top);
    [0, 100, 200, 300].forEach(function (v) { T(svg, x0 - 16, Y(v) + 9, '€' + v, { 'text-anchor': 'end', 'font-size': 24, fill: '#6B7491' }); });
    S('line', { x1: x0, x2: x1, y1: bot, y2: bot, stroke: GREY2, 'stroke-width': 3 }, svg);
    var start = HM.start + t * 864e5;
    [0, 30, 60, 90, 120].forEach(function (k) { if (k < span) T(svg, X(k), bot + 38, new Date(start + k * 864e5).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }), { 'text-anchor': 'middle', 'font-size': 24, fill: '#6B7491' }); });
    var a = lead, e = Math.min(lead + TS.nights, span - 1);
    S('rect', { x: X(a) - 4, y: top - 20, width: Math.max(8, X(e) - X(a)) + 8, height: bot - top + 20, rx: 6, fill: '#D5DEF7' }, svg);
    for (var k = 0; k < span; k++) {
      var bid = h.bid[k];
      if (bid === null) S('rect', { x: X(k) - 2.5, y: top - 20, width: 5, height: 14, rx: 2, fill: RED, opacity: 0.55 }, svg);
      else S('circle', { cx: X(k), cy: Y(Math.min(bid, ymax)), r: 4.5, fill: SLATE }, svg);
    }
    var ok = o.accepted;
    Deck.dash(svg, x0, Y(TS.rate), x1, Y(TS.rate), ok ? BLUE : RED, 4);
    T(svg, x1, Y(TS.rate) - 14, 'your rate', { 'text-anchor': 'end', 'font-size': 26, 'font-weight': 700, fill: ok ? '#1E44A8' : RED });
    T(svg, x0, 26, 'Bid price of each coming night', { 'font-size': 28, 'font-weight': 600, fill: INK });
    T(svg, x1, 26, 'red tick: full', { 'text-anchor': 'end', 'font-size': 24, fill: RED });
  }
  Deck.slide('s-try', {
    init: function (el) {
      if (!L) return; setup(); if (!HM) return;
      var $d = $('#tDay'), $l = $('#tLead'), $n = $('#tNights'), $r = $('#tRate');
      $d.min = 0; $d.max = L.snapshots.length - 1; $d.value = TS.day;
      $l.min = 0; $l.max = 183; $l.value = TS.lead; $n.value = TS.nights; $r.value = TS.rate;
      $d.addEventListener('input', function () { TS.day = +this.value; run(); });
      $l.addEventListener('input', function () { TS.lead = +this.value; run(); });
      $n.addEventListener('input', function () { TS.nights = +this.value; run(); });
      $r.addEventListener('input', function () { TS.rate = +this.value; run(); });
      Deck.seg($('#tHotel', el), function (k) { TS.hotel = +k; run(); });
      run();
    },
    enter: function () { run(); }
  });
})();
