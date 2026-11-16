/* The real cancellation model and the nightly bid price in plain JavaScript.

   Reads the two files written by presentation/model/export.py:
     model.json  stack of logistic regression, LightGBM and CatBoost, trained on arrivals before 1 July 2016
     live.json   the replay of 1 July - 11 August 2016 (every request with the numbers behind its decision,
                 and a start-of-day snapshot of every night's bid price and free rooms)

   HotelModel.load(model, live) -> m
     m.features(b, s)      one request + its stream features -> the 36 model inputs (same order as Python)
     m.predict(b, s)       -> { p, z, members: {lr, lgb, cb}, A }       (p = P(cancel))
     m.explain(A)          -> { constant, perColumn, drivers, themes }       (exact additive split of the logit)
     m.context(h, arrival, booked, extra)   stream features of a new request at the start of a replay day
     m.decide(b, opts)     -> everything behind an accept / reject (p, bid, free rooms, which check decided)

   parity.py / parity.mjs compare every number with the Python model. */
(function (root) {
  'use strict';

  /* ---------- typed arrays: "~f64:<base64>" ---------- */
  var KINDS = { f64: Float64Array, f32: Float32Array, i32: Int32Array, u32: Uint32Array, i16: Int16Array, u16: Uint16Array, u8: Uint8Array };
  function bytes(b64) {
    if (typeof atob === 'function') { var s = atob(b64), n = s.length, u = new Uint8Array(n); for (var i = 0; i < n; i++) u[i] = s.charCodeAt(i); return u; }
    var buf = Buffer.from(b64, 'base64'); return new Uint8Array(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.length));
  }
  function decode(o) {
    if (typeof o === 'string') {
      var m = /^~(f64|f32|i32|u32|i16|u16|u8):/.exec(o);
      return m ? new KINDS[m[1]](bytes(o.slice(m[0].length)).buffer) : o;
    }
    if (Array.isArray(o)) { for (var i = 0; i < o.length; i++) o[i] = decode(o[i]); return o; }
    if (o && typeof o === 'object') { for (var k in o) o[k] = decode(o[k]); }
    return o;
  }

  /* ---------- dates (UTC, ISO strings) ---------- */
  var DAY = 86400000;
  function utc(s) { var p = String(s).slice(0, 10).split('-'); return Date.UTC(+p[0], +p[1] - 1, +p[2]); }
  function iso(ms) { return new Date(ms).toISOString().slice(0, 10); }
  function dow(ms) { return (new Date(ms).getUTCDay() + 6) % 7; }          // Monday = 0, as pandas
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  function weekNumber(ms) {                                                  // the dataset's Sunday-start week number
    var d = new Date(ms), y = d.getUTCFullYear(), jan1 = Date.UTC(y, 0, 1);
    var doy = Math.round((ms - jan1) / DAY) + 1, off = (dow(jan1) + 1) % 7;
    return Math.floor((doy - 1 + off) / 7) + 1;
  }

  function num(v, d) { if (d === undefined) d = 0; if (v === null || v === undefined || v === '') return d; var f = +v; return f !== f ? d : f; }
  function sigmoid(z) { return 1 / (1 + Math.exp(-z)); }
  function logitClip(p) { p = Math.min(Math.max(p, 1e-6), 1 - 1e-6); return Math.log(p / (1 - p)); }

  /* ---------- features (FeatureBuilder.transform_record) ---------- */
  function Features(F) {
    this.F = F; this.cols = F.columns; this.code = {};
    for (var c in F.vocab) { var m = {}; F.vocab[c].forEach(function (v, i) { m[v] = i; }); this.code[c] = m; }
  }
  Features.prototype.row = function (b, s) {
    var F = this.F, r = {}, agent = b.agent === null || b.agent === undefined || (typeof b.agent === 'number' && b.agent !== b.agent) ? 'none' : String(Math.trunc(+b.agent));
    var comp = b.company === null || b.company === undefined || b.company === '' || (typeof b.company === 'number' && b.company !== b.company) ? 'none' : String(Math.trunc(+b.company));
    var arr = utc(b.arrival_date), mo = new Date(arr).getUTCMonth() + 1, nights = num(b.nights), lead = num(b.days_ahead);
    F.raw_num.forEach(function (c) { r[c] = num(b[c]); });
    if (b.arrival_week === undefined) r.arrival_week = weekNumber(arr);   // derived inputs a form does not give
    if (b.arrival_day === undefined) r.arrival_day = new Date(arr).getUTCDate();
    if (b.weekday_nights === undefined) r.weekday_nights = nights - num(b.weekend_nights);
    F.raw_cat.forEach(function (c) { r[c] = b[c] === null || b[c] === undefined ? 'NA' : String(b[c]); });
    r.arrival_month = MONTHS[mo - 1];
    r.agent = agent; r.agent_none = agent === 'none' ? 1 : 0;
    r.company_flag = comp !== 'none' ? 1 : 0;
    r.log_lead = Math.log1p(lead);
    r.lead_bin = F.lead_bins.filter(function (x) { return lead <= x[0]; })[0][1];
    r.arrival_dow = String(dow(arr));
    r.booking_dow = dow(utc(b.booking_date));
    r.weekend_share = num(b.weekend_nights) / Math.max(nights, 1);
    r.season = mo >= 6 && mo <= 8 ? 'summer' : (mo === 12 || mo <= 2) ? 'winter' : mo <= 5 ? 'spring' : 'autumn';
    r.month_sin = F.month_sin[mo - 1]; r.month_cos = F.month_cos[mo - 1];
    r.block_rank = s.block_rank; r.log_block_rank = Math.log(s.block_rank); r.in_block = s.block_rank > 1 ? 1 : 0;
    r.log_loose_rank = Math.log(s.loose_rank); r.log_day_agent = Math.log(s.day_agent_count);
    r.log_demand_date = Math.log1p(s.demand_date); r.log_demand_week = Math.log1p(s.demand_week);
    r.agent_te = Object.prototype.hasOwnProperty.call(F.agent_te, agent) ? F.agent_te[agent] : F.prior;
    var A = new Float64Array(this.cols.length);
    for (var j = 0; j < this.cols.length; j++) {
      var c = this.cols[j], v = r[c], code = this.code[c];
      A[j] = code ? (Object.prototype.hasOwnProperty.call(code, v) ? code[v] : code.other) : v;
    }
    return A;
  };

  /* ---------- the three members ---------- */
  function LR(M) { this.m = M.lr; }
  LR.prototype.raw = function (A) {
    var m = this.m, z = m.intercept, k = m.num_idx.length, i, j;
    for (i = 0; i < k; i++) z += m.coef[i] * (A[m.num_idx[i]] - m.mu[i]) / m.sd[i];
    for (i = 0; i < m.cat_idx.length; i++) { var c = Math.min(Math.max(Math.trunc(A[m.cat_idx[i]]), 0), m.sizes[i] - 1); z += m.coef[k + c]; k += m.sizes[i]; }
    return z;
  };
  LR.prototype.contrib = function (A, out) {
    var m = this.m, k = m.num_idx.length, i;
    for (i = 0; i < k; i++) out[m.num_idx[i]] += m.coef[i] * (A[m.num_idx[i]] - m.mu[i]) / m.sd[i];
    for (i = 0; i < m.cat_idx.length; i++) { var c = Math.min(Math.max(Math.trunc(A[m.cat_idx[i]]), 0), m.sizes[i] - 1); out[m.cat_idx[i]] += m.coef[k + c]; k += m.sizes[i]; }
    return m.intercept;
  };

  function LGB(M) {
    var m = this.m = M.lgb; this.sets = m.cat_sets.map(function (a) { var s = {}; a.forEach(function (v) { s[v] = 1; }); return s; });
  }
  LGB.prototype.go = function (i, x) {                                       // true = left child
    var m = this.m, k = m.kind[i];
    if (k & 1) { if (x !== x || x < 0) return false; return this.sets[m.thr[i]][Math.trunc(x)] === 1; }
    var mt = k >> 2, dl = (k >> 1) & 1;
    if (mt === 2 && x !== x) return !!dl;
    if (mt === 1 && Math.abs(x) <= 1e-35) return !!dl;
    return x <= m.thr[i];
  };
  LGB.prototype.raw = function (A) {
    var m = this.m, raw = 0;
    for (var t = 0; t < m.n_trees; t++) {
      var io = m.int_off[t], node = 0;
      while (node >= 0) { var i = io + node; node = this.go(i, A[m.feat[i]]) ? m.left[i] : m.right[i]; }
      raw += m.leaf_value[m.leaf_off[t] + ~node];
    }
    return raw;
  };
  /* TreeSHAP of one tree (path-dependent, covers = LightGBM's counts), as LightGBM's pred_contrib */
  LGB.prototype.contrib = function (A, out) {
    var m = this.m, self = this, bias = 0;
    for (var t = 0; t < m.n_trees; t++) {
      var io = m.int_off[t], lo = m.leaf_off[t];
      var tree = {
        isLeaf: function (n) { return n < 0; },
        feat: function (n) { return m.feat[io + n]; },
        hot: function (n) { return self.go(io + n, A[m.feat[io + n]]) ? m.left[io + n] : m.right[io + n]; },
        left: function (n) { return m.left[io + n]; }, right: function (n) { return m.right[io + n]; },
        cover: function (n) { return n < 0 ? m.leaf_count[lo + ~n] : m.count[io + n]; },
        value: function (n) { return m.leaf_value[lo + ~n]; }
      };
      bias += treeShap(tree, 0, out, function (f) { return [f]; });
    }
    return bias;
  };

  function CB(M) { this.m = M.cb; this.M = M; }
  CB.prototype.buckets = function (A) {
    var m = this.m, X32 = new Float32Array(A.length), codes = [], i, p, j;
    for (i = 0; i < A.length; i++) X32[i] = A[i];
    for (i = 0; i < m.cat_flat.length; i++) codes.push(Math.trunc(A[m.cat_flat[i]]));
    var cb = new Int32Array(m.ctr_proj.length);
    for (p = 0; p < m.projections.length; p++) {
      var pr = m.projections[p], key = 0, digs = [];
      for (j = 0; j < pr.cats.length; j++) digs.push(codes[pr.cats[j]]);
      for (j = 0; j < pr.bins.length; j++) {
        var bn = pr.bins[j];
        digs.push(bn.float !== undefined ? (X32[m.float_flat[bn.float]] > Math.fround(bn.border) ? 1 : 0) : (codes[bn.onehot] === bn.code ? 1 : 0));
      }
      for (j = 0; j < digs.length; j++) key = key * pr.radix[j] + digs[j];
      var lo = 0, hi = pr.keys.length - 1, at = -1;
      while (lo <= hi) { var mid = (lo + hi) >> 1; if (pr.keys[mid] === key) { at = mid; break; } if (pr.keys[mid] < key) lo = mid + 1; else hi = mid - 1; }
      for (j = 0; j < pr.ctrs.length; j++) cb[pr.ctrs[j]] = at >= 0 ? pr.buckets[j][at] : pr.default[j];
    }
    return { X32: X32, codes: codes, cb: cb };
  };
  CB.prototype.bits = function (st, t, pos) {                                // split outcomes of tree t
    var m = this.m, d = m.depth[t], out = new Array(d);
    for (var k = 0; k < d; k++) {
      var kind = m.split_kind[pos + k], a = m.split_a[pos + k], b = m.split_b[pos + k];
      out[k] = kind === 0 ? (st.X32[m.float_flat[a]] > Math.fround(b) ? 1 : 0) : kind === 1 ? (st.codes[a] === Math.trunc(b) ? 1 : 0) : (st.cb[a] > Math.trunc(b) ? 1 : 0);
    }
    return out;
  };
  CB.prototype.raw = function (A) {
    var m = this.m, st = this.buckets(A), raw = 0, pos = 0, leaf = 0;
    for (var t = 0; t < m.n_trees; t++) {
      var d = m.depth[t], bits = this.bits(st, t, pos), li = 0;
      for (var k = 0; k < d; k++) li |= bits[k] << k;
      raw += m.leaf_value[leaf + li];
      pos += d; leaf += 1 << d;
    }
    return raw * m.scale + m.bias;
  };
  /* Attribution over the "feature classes" CatBoost trees use (a split on a combination of inputs is one
     player; its share is split equally between the inputs). Players are few (at most the tree depth), so the
     Shapley values are summed exactly over all subsets; the value of a subset is the cover-weighted mean leaf
     among the leaves that agree with the request on the known splits. The result is additive (it sums to the
     tree's output) but it is not CatBoost's own ShapValues: see NOTES.md. */
  var FACT = [1, 1, 2, 6, 24, 120, 720, 5040];
  CB.prototype.contrib = function (A, out) {
    var m = this.m, st = this.buckets(A), pos = 0, leaf = 0, bias = 0;
    for (var t = 0; t < m.n_trees; t++) {
      var d = m.depth[t], nl = 1 << d, bits = this.bits(st, t, pos), cls = [], ci = new Array(d), k, i, mask;
      for (k = 0; k < d; k++) { var c = m.split_class[pos + k], at = cls.indexOf(c); if (at < 0) { at = cls.length; cls.push(c); } ci[k] = at; }
      var n = cls.length, miss = new Int32Array(nl);
      for (i = 0; i < nl; i++) { var mm = 0; for (k = 0; k < d; k++) if (((i >> k) & 1) !== bits[k]) mm |= 1 << ci[k]; miss[i] = mm; }
      var val = new Float64Array(1 << n);
      for (mask = 0; mask < (1 << n); mask++) {
        var num = 0, den = 0;
        for (i = 0; i < nl; i++) if ((miss[i] & mask) === 0) { var w = m.leaf_weight[leaf + i]; num += m.leaf_value[leaf + i] * w; den += w; }
        val[mask] = den > 0 ? num / den : 0;
      }
      bias += val[0];
      for (i = 0; i < n; i++) {
        var phi = 0;
        for (mask = 0; mask < (1 << n); mask++) {
          if ((mask >> i) & 1) continue;
          var sz = 0; for (var j = 0; j < n; j++) sz += (mask >> j) & 1;
          phi += FACT[sz] * FACT[n - sz - 1] / FACT[n] * (val[mask | (1 << i)] - val[mask]);
        }
        var cols = m.classes[cls[i]];
        for (j = 0; j < cols.length; j++) out[cols[j]] += phi / cols.length;
      }
      pos += d; leaf += nl;
    }
    return bias * m.scale + m.bias;
  };

  /* ---------- TreeSHAP (Lundberg et al.), path-dependent ---------- */
  function treeShap(tree, root, phi, cols) {
    var bias = 0;
    (function ev(n, w) { if (tree.isLeaf(n)) { bias += w * tree.value(n); return; } var c = tree.cover(n), l = tree.left(n), r = tree.right(n); if (c > 0) { ev(l, w * tree.cover(l) / c); ev(r, w * tree.cover(r) / c); } })(root, 1);
    function extend(p, ud, zf, of, fi) {
      p[ud] = { fi: fi, zf: zf, of: of, pw: ud === 0 ? 1 : 0 };
      for (var i = ud - 1; i >= 0; i--) { p[i + 1].pw += of * p[i].pw * (i + 1) / (ud + 1); p[i].pw = zf * p[i].pw * (ud - i) / (ud + 1); }
    }
    function unwind(p, ud, pi) {
      var of = p[pi].of, zf = p[pi].zf, next = p[ud].pw, i;
      for (i = ud - 1; i >= 0; i--) {
        if (of !== 0) { var tmp = p[i].pw; p[i].pw = next * (ud + 1) / ((i + 1) * of); next = tmp - p[i].pw * zf * (ud - i) / (ud + 1); }
        else p[i].pw = p[i].pw * (ud + 1) / (zf * (ud - i));
      }
      for (i = pi; i < ud; i++) { p[i].fi = p[i + 1].fi; p[i].zf = p[i + 1].zf; p[i].of = p[i + 1].of; }
    }
    function unwoundSum(p, ud, pi) {
      var of = p[pi].of, zf = p[pi].zf, next = p[ud].pw, total = 0;
      for (var i = ud - 1; i >= 0; i--) {
        if (of !== 0) { var tmp = next * (ud + 1) / ((i + 1) * of); total += tmp; next = p[i].pw - tmp * zf * ((ud - i) / (ud + 1)); }
        else total += p[i].pw / zf / ((ud - i) / (ud + 1));
      }
      return total;
    }
    function rec(n, ud, parent, pzf, pof, pfi) {
      var p = new Array(ud + 1), i;
      for (i = 0; i < ud; i++) p[i] = { fi: parent[i].fi, zf: parent[i].zf, of: parent[i].of, pw: parent[i].pw };
      extend(p, ud, pzf, pof, pfi);
      if (tree.isLeaf(n)) {
        var v = tree.value(n);
        for (i = 1; i <= ud; i++) {
          var w = unwoundSum(p, ud, i) * (p[i].of - p[i].zf) * v, cs = cols(p[i].fi);
          for (var c = 0; c < cs.length; c++) phi[cs[c]] += w / cs.length;
        }
        return;
      }
      var hot = tree.hot(n), l = tree.left(n), r = tree.right(n), cold = hot === l ? r : l, f = tree.feat(n);
      var iz = 1, io = 1, k;
      for (k = 1; k <= ud; k++) if (p[k].fi === f) break;
      if (k <= ud) { iz = p[k].zf; io = p[k].of; unwind(p, ud, k); ud -= 1; }
      var cn = tree.cover(n), fh = cn > 0 ? tree.cover(hot) / cn : 0, fc = cn > 0 ? tree.cover(cold) / cn : 0;
      rec(hot, ud + 1, p, iz * fh, io, f);
      if (iz * fc !== 0) rec(cold, ud + 1, p, iz * fc, 0, f);                // zero-weight cold branch adds nothing
    }
    rec(root, 0, [], 1, 1, -1);
    return bias;
  }

  /* ---------- the model object ---------- */
  function Model(M, L) {
    this.M = M; this.L = L; this.feat = new Features(M.features);
    this.mem = { lr: new LR(M), lgb: new LGB(M), cb: new CB(M) };
    this.order = M.members;
    if (L) { this.hotels = L.hotels; this.start = utc(L.meta.start); this.nDays = L.days.length; this.snap = {}; L.snapshots.forEach(function (s) { this.snap[s.t] = s; }, this); }
  }
  Model.prototype.features = function (b, s) { return this.feat.row(b, s); };
  Model.prototype.predict = function (b, s) {
    var A = this.feat.row(b, s), members = {}, z = this.M.stack.intercept, self = this;
    this.order.forEach(function (n) { var raw = self.mem[n].raw(A); members[n] = raw; z += self.M.stack.coef[n] * logitClip(sigmoid(raw)); });
    return { p: sigmoid(z), z: z, members: members, A: A };
  };
  Model.prototype.explain = function (A, topK) {
    var M = this.M, n = A.length, total = new Float64Array(n), constant = M.stack.intercept, self = this;
    this.order.forEach(function (name) {
      var c = new Float64Array(n), bias = self.mem[name].contrib(A, c), w = M.stack.coef[name];
      for (var j = 0; j < n; j++) total[j] += w * c[j];
      constant += w * bias;
    });
    var F = M.features, byLabel = {}, byTheme = {};
    for (var j = 0; j < n; j++) {
      var c = F.columns[j], lab = F.labels[c], th = F.themes[c] || 'other';
      byLabel[lab] = (byLabel[lab] || 0) + total[j]; byTheme[th] = (byTheme[th] || 0) + total[j];
    }
    function sorted(o) { return Object.keys(o).map(function (k) { return [k, o[k]]; }).sort(function (a, b) { return Math.abs(b[1]) - Math.abs(a[1]); }); }
    return { constant: constant, perColumn: total, drivers: sorted(byLabel).slice(0, topK || 5), allDrivers: sorted(byLabel), themes: sorted(byTheme) };
  };

  /* ---------- policy at the start of a replay day (snapshots exported from the Python policy) ---------- */
  Model.prototype.dayIndex = function (isoDate) { return Math.round((utc(isoDate) - this.start) / DAY); };
  /* stream features of a NEW request: nothing identical seen yet, demand counters from the snapshot */
  Model.prototype.context = function (hotel, arrival, booked, extra) {
    var t = this.dayIndex(booked), d = this.dayIndex(arrival), sn = this.snap[t], s = { block_rank: 1, loose_rank: 1, day_agent_count: 1, demand_date: 0, demand_week: 0 };
    if (sn) {
      var h = sn.hotels[hotel], k = d - t, w = Math.floor((d + this.L.dow0) / 7) - h.w0;
      if (k >= 0 && k < h.dd.length) s.demand_date = h.dd[k];
      if (w >= 0 && w < h.dw.length) s.demand_week = h.dw[w];
    }
    for (var key in extra || {}) s[key] = extra[key];
    return s;
  };
  Model.prototype.decide = function (b, opts) {
    opts = opts || {};
    var hotel = typeof b.hotel === 'number' ? b.hotel : this.L.hotels.indexOf(b.hotel);
    var nights = Math.max(1, Math.trunc(num(b.nights)));
    var s = opts.stream || this.context(hotel, b.arrival_date, b.booking_date);
    var bb = {}; for (var k in b) bb[k] = b[k];
    bb.hotel = this.M.features.vocab.hotel[hotel] || this.L.hotels[hotel];
    var pr = this.predict(bb, s), q = 1 - pr.p;
    var t = this.dayIndex(b.booking_date), d0 = this.dayIndex(b.arrival_date), sn = this.snap[t];
    var out = { p: pr.p, q: q, z: pr.z, members: pr.members, A: pr.A, stream: s, rate: num(b.nightly_rate), nights: nights, hotel: hotel, day: t };
    var h = sn ? sn.hotels[hotel] : null, rows = [], sum = 0, full = false, fits = true, i;
    if (!h || d0 < t || d0 + nights > this.nDays + 0 && d0 >= this.nDays || out.rate <= 0) { out.invalid = true; out.outcome = 'invalid'; out.accepted = false; out.nightsInfo = []; return out; }
    for (i = 0; i < nights; i++) {
      var d = d0 + i; if (d >= this.nDays) break;
      var bid = h.bid[d - t], free = h.free[d - t], inf = bid === null;
      rows.push({ night: iso(this.start + d * DAY), bid: inf ? Infinity : bid, free: free });
      if (inf) full = true; sum += inf ? Infinity : bid;
      if (free < q - 1e-9) fits = false;
    }
    out.nightsInfo = rows; out.bid = rows.length ? sum / rows.length : 0;
    out.okValue = out.rate >= out.bid; out.okRisk = out.okValue && fits;
    out.accepted = out.okRisk;
    out.outcome = out.accepted ? 'accepted' : !out.okValue ? (full ? 'full' : 'price') : 'capacity';
    return out;
  };
  /* a request of live.json -> the raw booking dict the model expects, and its stream features */
  Model.prototype.fromRecord = function (r) {
    return { hotel: this.L.hotels[r.hotel], booking_date: r.booked, arrival_date: r.arrival, nights: r.nights, weekend_nights: r.wkend,
      nightly_rate: r.rate, days_ahead: r.lead, adults: r.adults, children: r.children, babies: r.babies, sales_segment: r.segment,
      sales_channel: r.channel, guest_type: r.guest, meal: r.meal, room_type: r.room, agent: r.agent, company: r.company };
  };
  Model.prototype.streamOf = function (r) { return { block_rank: r.ctx[0], loose_rank: r.ctx[1], day_agent_count: r.ctx[2], demand_date: r.ctx[3], demand_week: r.ctx[4] }; };
  Model.prototype.example = function () { return this.L && this.L.bid_example; };

  var HotelModel = { load: function (M, L) { return new Model(decode(M), L ? decode(L) : null); }, decode: decode, utc: utc, iso: iso, weekNumber: weekNumber, MONTHS: MONTHS, treeShap: treeShap };
  if (typeof module !== 'undefined' && module.exports) module.exports = HotelModel;
  root.HotelModel = HotelModel;
})(typeof window !== 'undefined' ? window : globalThis);
