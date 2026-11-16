/* Parity test: model.js against the Python model.

   Needs presentation/build/{model,live}.json (export.py) and the Python reference dump written by
   parity.py (<temp>/valhacks-presentation/parity.json).

   node presentation/model/parity.mjs                    full report
   node presentation/model/parity.mjs --n 200            only the first 200 requests (fast)          */
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const HotelModel = createRequire(import.meta.url)('./model.js');
const read = (p) => JSON.parse(readFileSync(p, 'utf8'));
const model = read(join(here, '..', 'build', 'model.json'));
const live = read(join(here, '..', 'build', 'live.json'));
const ref = read(join(tmpdir(), 'valhacks-presentation', 'parity.json'));
const nArg = process.argv.indexOf('--n');
const limit = nArg > 0 ? +process.argv[nArg + 1] : Infinity;

const m = HotelModel.load(model, live);
const reqs = ref.requests.slice(0, limit);
if (live.requests.length !== ref.requests.length) throw new Error('live.json and parity.json come from different replays');

const worst = { features: 0, member: { lr: 0, lgb: 0, cb: 0 }, p: 0, contrib: 0, constant: 0, additivity: 0 };
let top1 = 0, top3 = 0, nDrv = 0, badFeature = 0, t0 = Date.now(), tPredict = 0, tExplain = 0;
reqs.forEach((r, i) => {
  const rec = live.requests[i];
  if (rec.id !== r.id) throw new Error('request order differs at ' + i);
  const b = m.fromRecord(rec), s = m.streamOf(rec);
  let t = performance.now();
  const pr = m.predict(b, s);
  tPredict += performance.now() - t;
  r.features.forEach((v, j) => { const d = Math.abs(pr.A[j] - v); if (d > worst.features) worst.features = d; if (d > 1e-9) badFeature++; });
  for (const k of model.members) worst.member[k] = Math.max(worst.member[k], Math.abs(pr.members[k] - r.members[k]));
  worst.p = Math.max(worst.p, Math.abs(pr.p - r.p));
  t = performance.now();
  const ex = m.explain(pr.A);
  tExplain += performance.now() - t;
  r.contrib.forEach((v, j) => { worst.contrib = Math.max(worst.contrib, Math.abs(ex.perColumn[j] - v)); });
  worst.constant = Math.max(worst.constant, Math.abs(ex.constant - r.constant));
  if (rec.drivers) {                                                       // Python's top-5 drivers, aggregated by label
    nDrv++; if (ex.drivers[0][0] === rec.drivers[0][0]) top1++;
    const a = new Set(ex.drivers.slice(0, 3).map((d) => d[0])); if (rec.drivers.slice(0, 3).every((d) => a.has(d[0]))) top3++;
  }
  let sum = ex.constant; for (const v of ex.perColumn) sum += v;
  worst.additivity = Math.max(worst.additivity, Math.abs(sum - pr.z));
});

// member decompositions (first 400 requests carry them)
const memberWorst = { lr: 0, lgb: 0, cb: 0 };
reqs.slice(0, 400).forEach((r, i) => {
  if (!r.member_contrib) return;
  const rec = live.requests[i], pr = m.predict(m.fromRecord(rec), m.streamOf(rec));
  for (const k of model.members) {
    const c = new Float64Array(pr.A.length), bias = m.mem[k].contrib(pr.A, c);
    r.member_contrib[k].c.forEach((v, j) => { memberWorst[k] = Math.max(memberWorst[k], Math.abs(c[j] - v)); });
    memberWorst[k] = Math.max(memberWorst[k], Math.abs(bias - r.member_contrib[k].bias));
  }
});

// policy: the start-of-day snapshots against the Python quotes (full precision)
let snapWorst = 0, snapN = 0;
ref.days.forEach((d, i) => {
  const sn = live.snapshots[i];
  if (sn.day !== d.day) throw new Error('snapshot day mismatch');
  d.hotels.forEach((h, k) => h.bid.forEach((v, j) => {
    const w = sn.hotels[k].bid[j];
    if (v === null || w === null) { if (v !== w) snapWorst = Infinity; return; }
    snapWorst = Math.max(snapWorst, Math.abs(v - w)); snapN++;
  }));
});

// decision of the FIRST request of every replay day (state = start of day): JS vs Python outcome
const seen = new Set(); let first = 0, agree = 0; const miss = [];
live.requests.forEach((rec, i) => {
  if (i >= reqs.length || seen.has(rec.booked)) return;
  seen.add(rec.booked);
  const o = m.decide(m.fromRecord(rec), { stream: m.streamOf(rec) });
  first++;
  if (o.outcome === rec.outcome) agree++; else miss.push({ id: rec.id, day: rec.booked, js: o.outcome, py: rec.outcome, rate: rec.rate, bidJs: +o.bid.toFixed(1), bidPy: rec.bid });
});

const f = (x) => x.toExponential(2);
console.log(`requests checked      ${reqs.length}   (${(tPredict / reqs.length).toFixed(2)} ms predict, ${(tExplain / reqs.length).toFixed(2)} ms explain per request)`);
console.log(`features              max |diff| ${f(worst.features)}   (inputs differing > 1e-9: ${badFeature})`);
for (const k of model.members) console.log(`member logit ${k.padEnd(4)}     max |diff| ${f(worst.member[k])}   own contributions ${f(memberWorst[k])}${k === 'cb' ? '   (CatBoost: additive, not its own ShapValues)' : ''}`);
console.log(`top driver (by label) same as Python on ${top1} of ${nDrv} requests, top three same set on ${top3}`);
console.log(`P(cancel)             max |diff| ${f(worst.p)}`);
console.log(`contributions (final) max |diff| ${f(worst.contrib)}   constant ${f(worst.constant)}   additivity ${f(worst.additivity)}`);
console.log(`bid snapshots         max |diff| ${snapWorst === Infinity ? 'inf/finite mismatch' : snapWorst.toFixed(3)} over ${snapN} night prices (stored to 0.1)`);
console.log(`first request of each day: outcome agrees on ${agree} of ${first}`);
miss.slice(0, 8).forEach((x) => console.log('  differs', JSON.stringify(x)));
const exact = ['lr', 'lgb'].every((k) => memberWorst[k] < 1e-9);
const ok = worst.features < 1e-9 && worst.p < 1e-9 && exact && worst.additivity < 1e-9 && agree === first;
console.log(ok ? 'PARITY OK' : 'PARITY FAILED');
process.exit(ok ? 0 : 1);
