# Methodology and decisions

How the system was built, in order, with the evidence behind each choice. Every number is net
revenue in M€ on the **local replay of 2016** (`src/simulator.py`) or a metric on the **temporal
walk-forward cuts**, both built from `train.csv` only. The notebooks and the scripts in
`experiments/` reproduce every figure quoted here.

## 1 · The problem and the ground rules

Requests arrive one at a time in booking order; each must be accepted or rejected immediately. A
guest who shows up earns `nightly_rate × nights`; when a hotel (Downtown 124 rooms, Seaside 103) is
full at check-in, the cheapest arriving guests are walked, earning nothing and costing 2.5 × their
stay value. The model is trained once and stays frozen for a full year.

| Rule | Why |
|---|---|
| `deposit` is never used | organisers' instruction |
| `booking_id` and the order of requests within a day are never used | the source file is sorted by outcome in long runs; within a day the first tenth of ids cancels 82% of the time at Downtown, the last tenth 13% (notebook 01) |
| Only information available when the request arrives | `amendments`, `waitlist_days`, `special_requests` accumulate after the booking |
| `country`, `past_stays`, `past_cancellations`, `returning_guest` are left out | their meaning drifts over time and they destroy calibration (§4) |
| Validation is temporal only | the model is frozen for a year; random CV is misleading (§3) |

## 2 · What the data says

* **Capacity binds.** Guests who showed up exceed capacity on 73% (Downtown) and 79% (Seaside) of
  nights, 1.3–1.8× from March to November. The question is mostly *whom* to accept (notebook 02).
* **Value per room-night swings with the season**, about 4× at Seaside. Requests must be compared
  with the price level of their own night.
* **Late bookers matter.** ~40% of the guests who show up booked in the last month and cancel
  12–23%; bookings made 90+ days ahead cancel 38–54%. The commitments inherited at the start of the
  year cancel far more than in-year bookings.
* **Cancellations come in blocks.** 38% of rows are identical group bookings; 96% of groups end
  unanimously (notebook 03).
* **Signals drift.** In 2015, 93–94% of cancellations are recorded as Portugal, about half by late
  2016 (country is likely confirmed at check-in). `past_cancellations` loses almost all its ranking
  power from 2015 to 2016.
* **Customers.** 7 personas at Downtown, 8 clusters (7 personas) at Seaside, stable and
  explainable; families and direct guests are worth the most per room, agency blocks the least
  (notebooks 04–05).

## 3 · How models and policies are evaluated

* **Temporal walk-forward.** Cuts on 1 January, 1 April and 1 July 2016, fixed in advance. At each
  cut: train on arrivals before the cut, test on every request booked from the cut to the end of
  2016. The same LightGBM gets AUC 0.874 under random 5-fold CV and 0.729–0.734 under the cuts.
* **Local replay** (`src/simulator.py`, notebook 06). Same rules as the official evaluator on three
  windows: H1 (Jan–Jun 2016), H2 (Jul–Dec 2016), FY (2016). Each window rebuilds the commitments
  (bookings made before the window for arrivals inside it) and the capacity (rooms minus guests
  still in house). The model of a window only sees arrivals before it. Three random within-day
  orders per configuration; their spread is ≤ 0.01 M€.
* **Revenue is the objective.** Classification metrics guide the model work, but recipes are chosen
  on replayed revenue, which is not monotone in log-loss (notebook 07).

## 4 · Features

The final set (`MODEL_CFG`, 36 columns) contains lead time (raw, log, band), stay and calendar
(nights, weekend share, arrival weekday, season, cyclic month), party and product, sales segment,
channel, guest type, company flag, the hotel, the agent id and its smoothed out-of-fold historical
cancel rate, and **live stream features** computed from the requests already seen, in random
within-day order: identical and similar requests (groups), requests from the same agent that day,
requests already seen for the night and week.

Ablations at the three cuts (`experiments/01_walk_forward_metrics.py`):

| Variant | LR log-loss (Jan / Apr / Jul) | LightGBM log-loss | Note |
|---|---|---|---|
| final features | 0.531 / 0.535 / 0.519 | 0.545 / 0.538 / 0.516 | |
| + country and guest history | 0.934 / 0.567 / 0.521 | 1.044 / 0.766 / 0.647 | January predictions average 11% for a true 31% |
| + special requests | 0.508 / 0.500 / 0.507 | 0.522 / 0.497 / 0.491 | not known at request time |
| + all post-booking columns | 0.499 / 0.490 / 0.496 | 0.509 / 0.489 / 0.487 | +0.03–0.05 AUC, invalid |
| no recency weights | 0.531 / 0.535 / 0.518 | 0.552 / 0.540 / 0.517 | half-life 6 months kept |

On revenue the post-booking columns do not even help logistic regression (H1+H2 4.32 with all
three, 4.41 with special requests, 4.40 without).

## 5 · Cancellation models

Three model families with different inductive biases: logistic regression (explicit one-hot and
standardisation, scored in microseconds), LightGBM and CatBoost. An earlier screening of seven
algorithms (these three, an EBM, random forest, extra trees and histogram gradient boosting) gave
log-losses between 0.52 and 0.55; the three retained are strong and different from each other. An EBM
(a glass-box additive model) was also compared and kept out of the final model: adding it to the
average or to the stack changes log-loss and AUC by at most 0.002 at every cut. Combinations of the
three: the plain average of logits (`avg3`) and a **temporal stack** (`stack3`, the shipped recipe):
members trained on arrivals up to four months before the cut predict the last four months; a
logistic meta-model learns the weights; the members are then refitted on everything.

| Recipe | Log-loss Jan / Apr / Jul | AUC Jul | ECE Jul |
|---|---|---|---|
| Logistic regression | 0.531 / 0.535 / 0.519 | 0.728 | 0.030 |
| LightGBM | 0.545 / 0.538 / 0.516 | 0.729 | 0.030 |
| CatBoost | 0.571 / 0.542 / 0.510 | 0.740 | 0.038 |
| EBM (compared, not in the final model) | 0.563 / 0.555 / 0.518 | 0.734 | 0.031 |
| Average of the three | 0.532 / 0.527 / **0.506** | **0.742** | **0.026** |
| **Stack of the three (shipped)** | 0.534 / 0.540 / 0.512 | 0.741 | 0.047 |

The average of the three beats the stack on log-loss and calibration at every cut; the stack ranks
as well (AUC within 0.001) but at the July cut predicts 22% cancellations for an observed 27%.

Tried and rejected: one model per hotel (LR 3.96 vs 4.40 on H1+H2; LightGBM 3.31 vs 4.09: less
data per model), a per-hotel intercept re-calibrated on the last three months (LR 4.39, LightGBM
3.73: chases noise).

## 6 · The acceptance policy

### 6.1 The decision, step by step (`BidPricePolicy.decide`)

1. `p_cancel` from the model; `q = 1 − p_cancel` is the expected share of a room the booking uses.
2. Free rooms per night = capacity − expected shows already accepted (commitments included).
3. Bid price per night (§6.2), averaged over the nights of the stay.
4. **Value check:** nightly rate ≥ average bid price.
5. **Capacity check:** expected shows + `q` ≤ capacity on every night (no safety margin).
6. Both pass: accept and add `q` to those nights.

`q × rate ≥ q × bid` reduces to `rate ≥ bid`: the probability decides how much capacity a booking
uses, the bid price decides who gets it. Overbooking is a consequence of counting expected shows.

### 6.2 Demand forecast and bid price (`DemandForecast`)

For night `d` decided `L` days before it, built from the training history and updated with every
request seen (accepted or not):

1. **Booking curve** `F(L)`: share of a night's demand booked at least `L` days ahead (per hotel,
   recency-weighted).
2. **Total demand** `T = g × μ(d)`: `μ(d)` = expected shows of the same weekday a year earlier
   (mean of nights −371, −364, −357 days; hotel average if not covered). `g` = growth factor: over
   the next 90 nights that are at least 30% booked, `(seen + 500) / (expected by now + 500)`,
   clipped to [0.6, 1.8].
3. **Demand still to come** `N = T × (1 − F(L))`.
4. **Bid price.** `free ≤ 0` → ∞ (reject); `N ≤ free` → 0 (the night will not fill); otherwise
   `P(d) × Q(1 − free / N)`, where `P(d)` is the price level of the night (requests seen for nearby
   nights corrected for their lead-time mix, blended with last year's level) and `Q` the weighted
   quantile function of the relative rates (rate / price level of nights ±3) of bookings made less
   than `L` days ahead.

### 6.3 Worked example (notebook 08)

Downtown, night of 15 September 2016, decided on 20 July with the policy live since 1 July:
57.6 expected guests already accepted, so 66.4 rooms free. Last year's same weekday: 183 expected
guests; growth 1.74 → `T` ≈ 318. At 57 days out 45% is usually booked → `N` ≈ 175 still to come.
66 of 175 can be seated (the top 38%), so the marginal guest is at the 62nd percentile of late
bookers' relative rates, 1.11 × the price level (€130): **bid price ≈ €145**. A €160 request passes,
a €120 one does not. With 5 free rooms the bid price would be above €250.

### 6.4 Where the gain comes from (H1+H2, LR model)

| Step | Net |
|---|---|
| Classic overbooking (one cancellation rate per hotel) | 3.67 |
| + per-booking probability, first come first served | 3.85 (+0.19) |
| + bid price | 4.41 (+0.55) |

### 6.5 Policy variants rejected (`experiments/04_policy_ablation.py`, LR, shift 0)

| Variant | Δ H1+H2 |
|---|---|
| bid price × 1.1 | +0.022 (inside the noise, not adopted) |
| safety margin z = 0.5 | −0.008 |
| price the walk on full nights (k = 3.5) | −0.065 (k = 2.5: −0.231) |
| bid price × 0.9 | −0.103 |

A **logit shift** on the probabilities was also gridded (`02`, `03`): an earlier, simpler model
needed +0.6; with the final feature set the best shifts are within ±0.2 and 0 is used.

## 7 · Results (2016 replay, M€)

| Strategy | H1 | H2 | FY |
|---|---|---|---|
| No overbooking | 1.638 | 1.101 | 3.790 |
| Classic overbooking (average rate per hotel) | 2.246 | 1.420 | 5.257 |
| Bid price + logistic regression | 2.693 | 1.711 | 6.492 |
| Bid price + LightGBM | 2.364 | 1.730 | 5.926 |
| **Bid price + stack of three (shipped)** | 2.683 | 1.694 | **6.328** |
| Oracle (knows who shows up) | 3.068 | 1.933 | 7.761 |

The shipped system is +20% over classic overbooking on the year and closes 43% of the gap to the
oracle. In H2 the commitments inherited on 1 July already exceed capacity on many summer nights,
which costs every policy, the oracle included.

## 8 · The shipped model, in hindsight

The delivered model is the stack of the three (`stack3`) at shift 0, retrained on all of July 2015 –
December 2016 (`python -m src.build_final`), meta-model: `logit = 0.168 + 0.292·LR − 0.002·LightGBM +
0.695·CatBoost`. Offline, the recipes tried are within a few percent of each other (H1+H2, shift 0:
stack of three 4.377 M€, logistic regression 4.404, stack of LR and LightGBM 4.406) and the stack
weights are not stable across cuts (LR 0.36–0.47, LightGBM 0.07–0.33, CatBoost 0.26–0.71). The plain
average of the same three is better than the stack on log-loss and calibration at every cut and has
no meta-model to fit: it is the recipe to try first next time (its revenue was not replayed).

## 9 · Interpretability

* **Exact decomposition.** Final logit = intercept + Σ members' weighted contributions, each member
  additive (LR coefficients, TreeSHAP for LightGBM and CatBoost). Verified to
  5·10⁻¹⁵ (`experiments/06_feature_importance.py`).
* **Per decision** (`Solution.explain()`): show-up probability, expected value, bid price, the
  check that decided, and the three inputs that moved the forecast most.
* **Global** (1,500 requests of 2016): guest profile 33%, group of identical requests 21%, agent
  15%, lead time 14%, calendar 8%, hotel 5%, rate and stay 3%, demand already seen 1%.
* **Limits.** SHAP attributions are not causal; correlated inputs can carry offsetting
  contributions; CatBoost carries most of the stack weight and is not readable on its own.

## 10 · Delivery

`solution.py` + `src/` + `models/final.joblib` + `requirements.txt`. Initialisation takes about
7 s (the demand forecast is built from the history stored in the model bundle), each `decide()`
about 2 ms. A single request is scored without pandas (`FeatureBuilder.transform_record`, the
explicit LR design, the LightGBM booster), and the online stream state is a handful of dict
counters.

The organisers' evaluator was run on this solution for reporting only (`evaluation/`): 5,425,157 € net
on the 2017 requests, +29.4% over classic overbooking and +72.3% over no overbooking. Nothing was chosen
or tuned on those requests.

## 11 · Limits

1. One out-of-sample year (2016) for every choice.
2. The demand forecast assumes last year's shape plus a bounded growth factor.
3. The model is frozen for a year and under-predicted cancellations by ~4 points at the July cut.
4. Only accepted bookings are observed (selection bias).
5. The capacity check uses expected shows, not the variance that groups add.

## 12 · Decision log

| # | Decision | Evidence |
|---|---|---|
| D1 | Temporal walk-forward, three fixed cuts | random CV overstates AUC by 0.14 |
| D2 | Choose the recipe on the past, then retrain on everything | more history, recent months weigh more |
| D3 | No `deposit`, `booking_id`, within-day order | rules; label leak |
| D4 | No `country` and guest history | drift; calibration collapses |
| D5 | No post-booking columns | not known at request time |
| D6 | Per-night bid price as the decision rule | largest single lever (+0.55 M€ H1+H2) |
| D7 | No safety margin, no walk pricing, bid scale 1 | worse or within noise |
| D8 | One model for both hotels, no recent recalibration | less data / chases noise |
| D9 | Ship `stack3` at shift 0 | top recipes within a few percent; average of the three preferred in hindsight |
