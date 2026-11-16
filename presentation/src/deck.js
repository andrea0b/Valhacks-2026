/* Deck: slide controller plus the small drawing helpers every section shares.
   A section registers its slides with Deck.slide(id, {init, enter}); init runs once at load,
   enter every time the slide is shown. Timers started with Deck.after are cleared on leave. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  function json(id) { var el = document.getElementById(id); try { return el ? JSON.parse(el.textContent) : null; } catch (e) { return null; } }
  var Deck = { D: json('deck-data'), MODEL: json('model-data'), LIVE: json('live-data'), instant: false, defs: {}, cur: -1 };
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var timers = [];

  Deck.slide = function (id, def) { Deck.defs[id] = def; };
  Deck.$ = function (s, r) { return (r || document).querySelector(s); };
  Deck.$$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  Deck.S = function (tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) if (attrs[k] !== undefined && attrs[k] !== null) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };
  Deck.T = function (svg, x, y, txt, attrs) {
    var a = { x: x, y: y, 'font-size': 26, fill: '#4A5470' };
    for (var k in attrs || {}) a[k] = attrs[k];
    var t = Deck.S('text', a, svg); t.textContent = txt; return t;
  };
  /* reference and threshold lines are always dashed */
  Deck.dash = function (svg, x1, y1, x2, y2, color, w) {
    return Deck.S('line', { x1: x1, y1: y1, x2: x2, y2: y2, stroke: color || '#0F1830', 'stroke-width': w || 3, 'stroke-dasharray': '12 9', 'stroke-linecap': 'round' }, svg);
  };
  Deck.mix = function (a, b, t) {
    function rgb(c) { return [1, 3, 5].map(function (i) { return parseInt(c.slice(i, i + 2), 16); }); }
    var x = rgb(a), y = rgb(b);
    return '#' + x.map(function (v, i) { return Math.round(v + (y[i] - v) * t).toString(16).padStart(2, '0'); }).join('');
  };
  Deck.pct = function (v, d) { return (v * 100).toFixed(d || 0) + '%'; };
  Deck.fmt = function (v, d) { return v.toLocaleString('en-GB', { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }); };
  Deck.countUp = function (el, to, dec, dur, pre, suf) {
    pre = pre || ''; suf = suf || '';
    if (reduce || Deck.instant) { el.textContent = pre + Deck.fmt(to, dec) + suf; return; }
    var t0 = null;
    function f(t) { if (t0 === null) t0 = t; var p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3); el.textContent = pre + Deck.fmt(to * e, dec) + suf; if (p < 1) requestAnimationFrame(f); }
    requestAnimationFrame(f);
  };
  Deck.after = function (ms, fn) { var id = setTimeout(fn, Deck.instant ? 0 : ms); timers.push(id); return id; };

  var tip = Deck.$('#tip');
  Deck.tip = function (html, e) {
    tip.innerHTML = html; tip.style.opacity = 1;
    var x = e.clientX + 16, y = e.clientY + 16;
    if (x + 330 > innerWidth) x = e.clientX - 336;
    if (y + 140 > innerHeight) y = e.clientY - 140;
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  };
  Deck.untip = function () { tip.style.opacity = 0; };
  Deck.hover = function (el, html) {
    el.addEventListener('mousemove', function (e) { Deck.tip(typeof html === 'function' ? html() : html, e); });
    el.addEventListener('mouseleave', Deck.untip);
  };
  /* segmented control: buttons with data-k, calls fn(key) */
  Deck.seg = function (seg, fn) {
    seg.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      Deck.$$('button', seg).forEach(function (x) { x.classList.toggle('on', x === b); });
      fn(b.dataset.k);
    });
  };

  var stage, slides;
  function fit() {
    var w = innerWidth, h = innerHeight, k = Math.min(w / 1920, h / 1080);
    stage.style.transform = 'scale(' + k + ')';
    stage.style.left = ((w - 1920 * k) / 2) + 'px';
    stage.style.top = ((h - 1080 * k) / 2) + 'px';
  }
  function go(i) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    if (i === Deck.cur) return;
    timers.forEach(clearTimeout); timers = [];
    slides.forEach(function (s, k) { s.classList.toggle('on', k === i); });
    Deck.cur = i;
    document.body.style.backgroundColor = getComputedStyle(slides[i]).backgroundColor;
    Deck.$('#count').textContent = (i + 1) + ' / ' + slides.length;
    try { history.replaceState(null, '', '#slide-' + (i + 1)); } catch (e) { /* sandboxed */ }
    Deck.untip();
    var def = Deck.defs[slides[i].id];
    if (def && def.enter) def.enter(slides[i], Deck.D);
  }
  Deck.go = go;
  Deck.count = function () { return slides.length; };

  var fsTried = false;
  function fullscreen(force) {
    var d = document, el = d.documentElement;
    try {
      if (d.fullscreenElement) { if (force) d.exitFullscreen(); return; }
      if (el.requestFullscreen) el.requestFullscreen().catch(function () {});
    } catch (e) { /* not allowed here */ }
  }
  function firstGesture() { if (!fsTried) { fsTried = true; fullscreen(false); } }

  Deck.boot = function () {
    stage = Deck.$('#stage');
    slides = Deck.$$('.slide');
    slides.forEach(function (s) { var def = Deck.defs[s.id]; if (def && def.init) def.init(s, Deck.D); });
    fit();
    window.addEventListener('resize', fit);
    document.addEventListener('keydown', function (e) {
      var t = e.target && e.target.tagName;
      if (t === 'INPUT' || t === 'SELECT' || t === 'TEXTAREA') return;
      firstGesture();
      var k = e.key;
      if (k === 'ArrowRight' || k === 'PageDown' || k === ' ') { go(Deck.cur + 1); e.preventDefault(); }
      else if (k === 'ArrowLeft' || k === 'PageUp') { go(Deck.cur - 1); e.preventDefault(); }
      else if (k === 'Home') go(0); else if (k === 'End') go(slides.length - 1);
      else if (k === 'f' || k === 'F') fullscreen(true);
    });
    document.addEventListener('pointerdown', firstGesture, { passive: true });
    var tx = null;
    document.addEventListener('touchstart', function (e) { tx = e.touches[0].clientX; }, { passive: true });
    document.addEventListener('touchend', function (e) {
      if (tx === null) return; var dx = e.changedTouches[0].clientX - tx;
      if (Math.abs(dx) > 70) go(Deck.cur + (dx < 0 ? 1 : -1)); tx = null;
    }, { passive: true });
    var nav = Deck.$('#nav'), hideT = null;
    document.addEventListener('mousemove', function (e) {
      if (e.clientY < innerHeight - 140) { if (!nav.matches(':hover')) nav.classList.remove('show'); return; }
      nav.classList.add('show'); clearTimeout(hideT);
      hideT = setTimeout(function () { if (!nav.matches(':hover')) nav.classList.remove('show'); }, 1800);
    });
    Deck.$('#prev').onclick = function () { go(Deck.cur - 1); };
    Deck.$('#next').onclick = function () { go(Deck.cur + 1); };
    Deck.$('#fs').onclick = function () { fullscreen(true); };
    var h = parseInt((location.hash || '').replace('#slide-', ''), 10);
    go(isNaN(h) ? 0 : h - 1);
  };
  window.Deck = Deck;
})();
