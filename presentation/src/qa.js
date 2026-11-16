/* Visual QA for the dev build: for every slide, finds text outside the safe area (side margins
   100px, top 50px, bottom 40px), text boxes that overlap other text, text clipped by its box and
   anything drawn off the canvas. Run in the browser console: await __qa() */
(function () {
  'use strict';
  function visible(el, slide) {
    for (var e = el; e && e !== slide.parentNode; e = e.parentNode) {
      if (e.nodeType !== 1) continue;
      var cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.05) return false;
    }
    return true;
  }
  function ownText(el) {
    for (var c = el.firstChild; c; c = c.nextSibling) if (c.nodeType === 3 && c.textContent.trim()) return true;
    return false;
  }
  function bleed(el) { return !!el.closest('[data-qa="bleed"]'); }
  function check(i) {
    var slide = Deck.$$('.slide')[i], sr = slide.getBoundingClientRect(), k = sr.width / 1920, issues = [];
    function box(el) { var r = el.getBoundingClientRect(); return { x: (r.left - sr.left) / k, y: (r.top - sr.top) / k, w: r.width / k, h: r.height / k }; }
    function name(el) { var t = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40); return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + ' "' + t + '"'; }
    var texts = [];
    Deck.$$('*', slide).forEach(function (el) {
      if (!visible(el, slide)) return;
      var b = box(el);
      if (b.w === 0 && b.h === 0) return;
      if (!bleed(el) && (b.x < -1 || b.y < -1 || b.x + b.w > 1921 || b.y + b.h > 1081)) issues.push('off canvas: ' + name(el) + ' ' + JSON.stringify(b));
      if (!ownText(el)) return;
      texts.push({ el: el, b: b });
      if (!bleed(el) && (b.x < 100 || b.x + b.w > 1820 || b.y < 50 || b.y + b.h > 1040)) issues.push('outside safe area: ' + name(el) + ' x' + Math.round(b.x) + ' y' + Math.round(b.y) + ' r' + Math.round(b.x + b.w) + ' b' + Math.round(b.y + b.h));
      if (el instanceof HTMLElement && el.scrollWidth > el.clientWidth + 2 && getComputedStyle(el).overflow !== 'visible') issues.push('clipped: ' + name(el));
    });
    for (var a = 0; a < texts.length; a++) for (var c = a + 1; c < texts.length; c++) {
      var A = texts[a], B = texts[c];
      if (A.el.contains(B.el) || B.el.contains(A.el)) continue;
      var ix = Math.min(A.b.x + A.b.w, B.b.x + B.b.w) - Math.max(A.b.x, B.b.x), iy = Math.min(A.b.y + A.b.h, B.b.y + B.b.h) - Math.max(A.b.y, B.b.y);
      if (ix > 3 && iy > 3) issues.push('overlap: ' + name(A.el) + ' × ' + name(B.el) + ' (' + Math.round(ix) + '×' + Math.round(iy) + ')');
    }
    return { slide: i + 1, id: slide.id, issues: issues.slice(0, 14), total: issues.length };
  }
  window.__qa = async function (only) {
    document.body.classList.add('qa'); Deck.instant = true;
    var out = [], n = Deck.count(), start = Deck.cur;
    for (var i = 0; i < n; i++) {
      if (only && only.indexOf(i + 1) < 0) continue;
      Deck.go(i); await new Promise(function (r) { setTimeout(r, 150); });
      out.push(check(i));
    }
    document.body.classList.remove('qa'); Deck.instant = false; Deck.go(start);
    return out.filter(function (x) { return x.total; });
  };
})();
