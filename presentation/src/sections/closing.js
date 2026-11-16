/* Closing: the pipeline, how it is used, the answer. Numbers come from data.json and live.json so the text never drifts from the results. */
(function () {
  var S = Deck.S, T = Deck.T, $ = Deck.$;
  var BLUE = '#2A5BD7', INK = '#0F1830', GREY2 = '#C5CBD8';

  var cur = 0;
  function stages(D) {
    var L = Deck.LIVE, bid = L && L.bid_example ? '€' + Math.round(L.bid_example.bid) : '€156';
    var n = Deck.MODEL ? Deck.MODEL.features.columns.length : 36;
    var auc = D.model.random_vs_time.filter(function (r) { return /2016-07-01/.test(r.validation) && r.features === 'final features'; })[0];
    return [
      { name: 'Request', big: String(n), h: 'inputs, known on arrival', p: 'Hotel, stay, rate, agent, lead time, and live counters of identical requests seen. No booking ID, no column that appears after the booking.' },
      { name: 'Cancellation model', big: auc ? auc.auc.toFixed(2) : '0.73', h: 'AUC on months it has not seen', p: 'Logistic regression, LightGBM and CatBoost, stacked into one calibrated probability of cancelling.' },
      { name: 'Expected shows', big: 'q = 1 − p', h: 'a booking is a fraction of a room', p: 'Counting expected guests instead of bookings is what makes overbooking safe: 76 bookings can mean 58.6 guests.' },
      { name: 'Bid price', big: bid, h: 'the rate of the marginal guest', p: 'For every night: the rate of the last guest we still expect to seat if we keep the room (Downtown, 15 September, decided on 20 July).' },
      { name: 'Decision', big: D.evaluator.ms_per_decision + ' ms', h: 'accept or reject, with a reason', p: 'Accept when the rate beats the bid price and the expected guests fit the free rooms. One sentence says which check decided.' }];
  }
  function draw(D) {
    var svg = $('#pipe'), st = stages(D), w = 288, gap = 60;
    svg.innerHTML = '';
    st.forEach(function (s, i) {
      var x = i * (w + gap), on = i === cur, g = S('g', { style: 'cursor:pointer' }, svg);
      S('rect', { x: x, y: 40, width: w, height: 170, rx: 28, fill: on ? BLUE : '#F8F9FC' }, g);
      T(g, x + 36, 100, String(i + 1), { 'font-size': 30, 'font-weight': 700, fill: on ? '#DCE5FB' : '#6B7491' });
      var words = s.name.split(' ');
      T(g, x + 36, (words.length > 1 ? 144 : 170), words.length > 1 ? words[0] : s.name, { 'font-size': 40, 'font-weight': 700, fill: on ? '#F8F9FC' : INK });
      if (words.length > 1) T(g, x + 36, 196, words.slice(1).join(' '), { 'font-size': 40, 'font-weight': 700, fill: on ? '#F8F9FC' : INK });
      if (i < st.length - 1) { S('path', { d: 'M' + (x + w + 10) + ' 125 H' + (x + w + gap - 12) + ' M' + (x + w + gap - 28) + ' 111 L' + (x + w + gap - 12) + ' 125 L' + (x + w + gap - 28) + ' 139', fill: 'none', stroke: GREY2, 'stroke-width': 5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, svg); }
      g.addEventListener('click', function () { cur = i; draw(D); });
    });
    var s = st[cur];
    $('#pipeD').innerHTML = '<div class="big">' + s.big + '</div><div><h3>' + s.h + '</h3><p>' + s.p + '</p></div>';
  }
  Deck.slide('s-pipeline', {
    init: function (el, D) { draw(D); },
    enter: function (el, D) { cur = 0; draw(D); }
  });

  Deck.slide('s-deploy', {
    init: function (el, D) {
      $('#depMs', el).textContent = D.evaluator.ms_per_decision + ' ms';
      $('#depN', el).textContent = Deck.fmt(D.evaluator.decide_calls);
      var L = Deck.LIVE, r = L && L.requests.filter(function (x) { return x.accepted && x.nights >= 3 && x.reason; })[1];
      var q = $('#depQ', el);
      if (r) q.innerHTML = '<b>What the manager reads:</b> ' + r.reason.replace(/; main factors:.*$/, '.');
      else q.style.display = 'none';
    }
  });

  Deck.slide('s-end', {
    init: function (el, D) {
      var m = D.evaluator.rows.filter(function (r) { return r.key === 'model'; })[0];
      $('#endNet', el).textContent = '€' + (m.net / 1e6).toFixed(2) + 'M';
      $('#endVs', el).textContent = '+' + Math.round(D.evaluator.vs_classic * 100) + '%';
    }
  });
})();
