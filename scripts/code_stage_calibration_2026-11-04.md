# Calibration after the gate - report (2026-11-04)

Stage rules kept: test database only (production not touched); deleted nothing; Gemini flash-lite on the shared counter (about 150 attempts in this stage against the cap of 250: re-ask experiment 23, loads of the five weak REITs 107 - MAC 22, PK 18, DHC 23, BDN 22, HPP 22 - and a few at the start of the stage); golden not changed;
no key printed, no `.env` sourced; the `security` branch not touched. **No rulebook file was edited. No parameter is on. Every measurement below was made with the parameter switched on by an environment variable for the length of the run only, writing nothing to the database.**

Measurement tools (all in `scripts/`): `cal_measure.py` (scores every company from the stored facts and answers, nothing written; run with `VC_CAL_<NAME>=1`), `cal_compare.py` (two runs side by side), `cal_reit_341.py`, `cal_reit_ai.py`,
`cal_weak_reit.py`, `cal_price_scale.py`, `cal_reask_ai.py`, `cal_verify_quotes.py`. Raw outputs: `scripts/state/cal_*.txt|json`.
Population of the measurement: 115 companies of the test database that had a score (the five weak REITs were loaded afterwards and are measured separately). **Caveat:** 44 companies have AI items still `ai_pending` (answers not yet approved); `ai_pending` is ignored by the score and by the coverage (M-rules), so
their scores are on the other items.

Parameters added in this stage (`config/calibration.yaml`, read by `src/scoring/calibration.py`; all **false**): `growth_window_10y`, `reg_basis_from_text`, `life_dominant_na` (and `life_dominant_share`, 0.5, reserved: the definition used today is the line of business, see 2).
Code changes that are not parameters: (a) `drop_facts` - a figure held back by a control is also removed from the stored facts (rule M10, see 3); (b) the work-queue repository reads the queue page by page (see "A bug found on the way" at the end);
(c) `assess.ask(..., extra_note="")` - an optional note for experiments, empty by default, so the production prompt is unchanged. Tests: 1000 pass.

---

## 1. REIT calibration (profile INCOME_REAL_ESTATE, 24 companies in the measurement)

### 1(a) Buffett 3.4.1 (incremental return on capital) per REIT - `scripts/state/cal_reit_341.txt`
Of 24 REITs: **8 are scored, 16 are missing.** The 16 missing (AMT, AVB, BXP, DLR, EPR, EQIX, EXR, HST, KIM, MAA, OHI, SLG, VICI, WY, EQR, SPG) have no disclosed stabilized acquisition/development yield, and the NOI_PROXY cannot be computed
(needs NOI at t and t-4 and enough growth capital; EQR: disposals are 17.2% of the real estate, above the 10% limit; SPG: net growth capital is negative). **The zeros are not an anchors problem for most REITs - for most there is no number at all.**
Of the 8 scored: FRT, O, PLD (direct yield, basis "direct") score 1.63 / 1.48 / 0.28 of 4. Five are 0.00: PSA (spread -6.3pp) and SUI (spread -10.1pp) are zero because of the data, not the anchors (the spread is below -2pp); ARE, REXR, VTR (spreads -0.4 / -0.9 / -1.8pp, NOI_PROXY basis) are zero because of the anchors / cost of equity.
Sensitivity (average points of 4 over the 8 scored): today (9% cost of equity, anchors 0..4pp) **0.68**; cost of equity 8% 1.06; 10% 0.42; zero anchor moved to -2pp: 8% 2.31, **9% 1.98**, 10% 1.53 (positive scores for 6 of 8 instead of 3 at 9%); also moving 4 points to +4pp: 9% 1.35.
**Result: no change made. Recommendation: do not touch the anchors.** Moving the zero to -2pp would add about 1.3 points (of 4, i.e. under 1% of a quality score) to three REITs; the real gap is that 16 of 24 REITs have no figure. The weak REITs confirm it: 4 of the 5 are missing here too (see 1(d)) - the item does not discriminate.

### 1(b) `growth_window_10y` (default off) - `scripts/state/cal_growth10_compare.txt`
Definition: growth items (Buffett 3.3.3 revenue, 3.8.2, 3.8.3 EPS / FCF / owner earnings / book value in all profiles) use up to 10 years where they exist (at least 5): CAGR from the average of the first 3 years to the average of the last 3, instead of the 5-year smoothed growth of R14.
Measurement on all 115 companies (Buffett; **Graham is unchanged for all: 0 companies, no item**; coverage unchanged for all):

| Profile | n | mean before | mean after | moved more than 2 points | up / down |
|---|---|---|---|---|---|
| BANK | 22 | 75.8 | 77.1 | 10 | 9 / 1 |
| INCOME_REAL_ESTATE | 24 | 76.3 | 75.7 | 11 | 4 / 7 |
| INSURANCE | 23 | 77.3 | 78.4 | 8 | 7 / 1 |
| STANDARD | 29 | 71.2 | 73.5 | 13 | 12 / 1 |
| TECH_ASSET_LIGHT | 17 | 87.2 | 87.7 | 2 | 2 / 0 |

44 of 115 companies move by more than 2 points. Items changed: 3.3.3 (48 companies), 3.8.2 (71), 3.8.3 (62).
**The REIT-vs-others gap does not narrow - it widens:** others minus REITs, mean 0.5 -> 2.6 points (median 2.7 -> 2.4). REITs fall (7 of 11 movers go down), the others rise. (In Graham the REITs are already 7.9 points *above* the others, unchanged.)
Where the 10 years are missing: the stored series have 10 fiscal years (FY2016-FY2025) for most companies. Fewer for revenue: AMT 9, MAA 9, VICI 8 (a missing first-year figure or a later listing); fewer for EPS: KIM 5, SPG 5, O 8, VICI 8 (EPS tag gaps - the minimum of 5 years still applies);
CLX, DOW, UBER 9; ERIE and HSY have no EPS series. Banks have no revenue series (other series are used).
**Result: the parameter is built and measured; it does not do what it was meant to for the REITs.**

### 1(c) AI answers of the REITs against the other profiles (3.1.1-3.1.5, 3.2.4, 3.2.5, 3.7.5, 3.8.6; maximum 17) - `scripts/state/cal_reit_ai.txt`
Companies with all nine items answered, and how many have 17 of 17: **REIT 13 of 16 (81%)**; INSURANCE 7 of 13 (54%); TECH 8 of 12 (67%); STANDARD 8 of 18 (44%); BANK 4 of 12 (33%). Per item the REITs and the others are the same in 3.1.x (2.00 each); the REITs are a little higher in 3.2.4 (1.87 vs 1.77), 3.2.5 (1.00 vs 0.92), 3.7.5 (2.00 vs 1.96), 3.8.6 (1.87 vs 1.82).
So the effect is real but concentrated: 13 REITs reach the maximum. Of the 24 REITs, 8 are still `ai_pending`.
Sample of three REITs with 17/17 (AVB, DLR, SLG; reasoning and quotes read, `B3.2-Q4`, `B3.2-Q5`, `B3.7-Q5`, `B3.8-Q6`):
- **B3.2-Q4 / Q5 (stable competitive position, moat):** the answer is 2 by *size* ("one of the largest developers", "largest global provider", "Manhattan's largest owner of office real estate"). The skill note asks to judge the durability of the location/asset and not to treat a rising market as stability; **none of the three reasonings shows durability evidence** (occupancy or same-property NOI through the cycle, rent spreads, lease terms). SLG - a Manhattan office owner - gets 2 and 2 on the quote "largest owner of office real estate", which is a size claim.
- **B3.7-Q5 (transparent, no heavy use of "adjusted" metrics):** all three quote the boilerplate "disclosure controls and procedures were effective". That sentence is in every 10-K and says nothing about transparency; the scale's level 1 names "heavy use of adjusted metrics", which describes FFO/AFFO reporting of nearly every REIT, and the answer is never 1.
- **B3.8-Q6 (sustainable growth):** AVB gets 2 while its listed drivers include acquisitions and development; the scale gives 1 for growth that partly depends on acquisitions. The REIT note (organic - same-property NOI, rents - against acquisition-led) is not applied in the reasoning.
- Weak REITs get the same: MAC 2/2 and DHC 2/2 in 3.2.4 and 3.8.6 (dividend cut from $3.00 to $0.68 for MAC, from $1.56 to $0.04 for DHC).
**Judgement: the AI answers do not separate a durable location advantage from a rising market; they reward size.** Proposed rewording (the skill version is not changed; for the owner's decision):
  1. B3.2-Q4/Q5, REIT note: "Level 2 needs at least one durability fact from the report for the last 5 years (occupancy, same-property NOI growth, rent spread, lease term) - being the largest does not by itself give 2. If the report gives no such fact: 1."
  2. B3.7-Q5, REIT note: "The sentence that disclosure controls are effective is not evidence. Check how FFO/AFFO/'adjusted' measures are presented against GAAP: heavy reliance = 1."
  3. B3.8-Q6, REIT note: "Growth whose stated drivers include acquisitions or development financed by new equity or debt is level 1 unless the report shows same-property growth."
  The effect should be measured before adoption with a small re-ask (about 20 calls), as in item 6 - not done here (cap and scope).

### 1(d) Reference set of five NEW weak REITs - `scripts/state/cal_weak_reit.txt`
Chosen with external evidence (dividends and EPS from the stored XBRL facts; all five have 10 years of 10-K under the same CIK; five property types) and checked by `acceptance_preflight` (MPW is not on the SEC list and was rejected):

| REIT | Type | Evidence (stored facts) |
|---|---|---|
| MAC | retail (malls) | dividend per share 3.00 (2019) -> 1.55 -> 0.60 (2021) -> 0.68; EPS negative in 2020, 2022-2025 |
| BDN | office | dividend 0.76 (2022) -> 0.68 -> 0.60 -> 0.53; EPS 1.77 (2020) -> -1.03 (2025) |
| PK | hotels | dividend 1.90 (2019) -> 0.45 -> 0.00 (2021); EPS -6.11 (2020), -1.43 (2025) |
| DHC | healthcare | dividend 1.56 (2018) -> 0.84 -> 0.18 -> 0.04; EPS negative in 6 of 7 years |
| HPP | office | dividend 7.00 (2022) -> 2.63 -> 0.70 -> 0.00 (2025); EPS -2.73, -9.54, -18.05, -12.81 |

All five were loaded with `load` (the data) and the AI queue (extraction, assessment, background): about 290 fact rows each, 10 fiscal years. Quality scores (Buffett): **BDN 48.9, DHC 56.3, PK 46.0, MAC 78.0 (coverage 71%), HPP no score (coverage 56%, below the 60% of M5).** Strong REITs in the measurement: mean 76.3, median 77.2 (24 REITs).
Per item (mean points of the strong REITs against the five weak; only items where the weak REITs are at least 0.5 point lower): 3.3.1 5.92 -> 2.80 (-3.1); 3.3.2 3.25 -> 1.80 (-1.5); 3.3.4 1.78 -> 0.40 (-1.4); 3.3.3 2.63 -> 1.47 (-1.2); 3.8.1 2.54 -> 1.40 (-1.1); 3.8.2 1.43 -> 0.81 (-0.6); 3.5.1 4.67 -> 1.70 (-3.0, n=3); 3.5.2 5.25 -> 3.94 (-1.3);
3.6.1 / 3.6.2 3.4 -> 0 (n=2-3); 3.4.2 5.45 -> 0 (n=1). **The method discriminates through the growth (3.3, 3.8.1-3.8.3), leverage (3.6) and cost-of-capital items (3.5); it does not discriminate through 3.4.1 (4 of 5 missing), the other 3.4 items, 3.7.x, and all AI items (3.1.x, 3.2.4, 3.7.5: the weak REITs get the same points as the strong; 3.2.5, 3.8.6 only slightly less).**
Two cases are not caught: **MAC scores 78 (above the strong mean)** because 3.4.2, 3.5.1 and 3.6.x are missing (coverage 71%) and the growth items it fails are few; **HPP gets no score only because of coverage.** A score of 78 at 71% coverage for a REIT that cut its dividend by 77% is a gap of the method (RP1a only removes the buy price below 80%).
Gap per criterion (strong minus weak, points): growth 3.3 about -1.1 to -3.1; leverage 3.6 about -3.4; float/cost-of-capital 3.5 about -1.3 to -3.0; AI items about 0.

### 1(e) Recommendation (REIT)
| Item | Adopt? | Why / numbers |
|---|---|---|
| (a) 3.4.1 anchors / cost of equity | **No** | The problem is data (16 of 24 missing), not the anchors. Moving the zero to -2pp = +1.3 of 4 points for 3 REITs. |
| (b) `growth_window_10y` for the REIT gap | **No** | The gap widens (0.5 -> 2.6); 44 companies move by more than 2 points; 7 of 11 moving REITs fall. If the owner wants 10-year growth in general, it is a separate decision for all profiles (mean +1.2 for the non-REIT profiles). |
| (c) AI rewording B3.2-Q4/Q5, B3.7-Q5, B3.8-Q6 (REIT notes) | **Yes, after a small re-ask test** | 81% of the REITs have 17/17 against 33-67% elsewhere; weak REITs get the same AI points as strong ones; three samples show size and boilerplate as the evidence. |
| (d) the weak set | **Keep as a standing reference set** | It shows the method separates 3 of 4 scored weak REITs by 20-30 points (BDN, DHC, PK) and fails for MAC (78) and for HPP (no score). Proposal: a rule that a REIT with coverage under 80% and a dividend cut is flagged for review (owner decision). |

---

## 2. Life insurers

**`life_dominant_na` (default off).** Measurable definition (the one built): the insurer's line of business is *life* (SIC 6311; `LINE_OF_BUSINESS` of the golden set, set by `auto_config` for others) - a premium-share test ("long-duration life and health premiums above 50% of the premiums", parameter `life_dominant_share` 0.5)
needs an extracted premium split that does not exist in the data today, so it is reserved and not built. With the parameter on, Buffett 3.5 #1, #2, #4 that are *missing* become *not applicable* (the loss ratio and the combined ratio are not reported by a life insurer).
Measurement on the 23 insurers (`scripts/state/cal_life.json`): **only LNC changes**: 3.5.1, 3.5.2, 3.5.4 missing -> not applicable; Buffett quality **51.2 -> 52.6**, coverage **75% -> 90%** (it crosses the 80% line of RP1a: the buy price is no longer removed for coverage; at quality under 55 it stays "not suitable").
**UNM does not change**: its 3.5 items are already scored (6.0 / 3.0 / 4.0 / 0.0); its missing item is 3.6.1 (see below). MET, PRU, AFL (life) do not change either: they have a figure for every 3.5 item. **All P&C insurers (CB, TRV, PGR, ALL, WRB, CINF), reinsurance (RNR) and the composites (AIG, HIG) are unchanged** - 0 companies, 0 items. AIG (composite, 3.5.1/2/4 missing, score 28.4) is not touched because it is not life by the definition.
(KNSL Graham 3.1.2 differs in the sixth decimal between the runs - a price refresh between the runs, not related to the parameter.)

**`reg_basis_from_text` (default off).** The regulatory capital ratio extracted by the AI carries its basis in words, not in the tag of the hand-made table. With the parameter on, the words give the basis (Company Action Level, Authorized Control Level, SCR, solvency margin).
Measurement on the 23 insurers (`scripts/state/cal_reg.json`): **only UNM changes**: Buffett 3.6.1 missing -> scored 4.0 (full); Buffett quality **79.6 -> 81.3**, coverage **90% -> 100%**; Graham 3.2.1 missing -> scored 10.0 but the Graham quality score stays 88.89 (coverage 82% unchanged; the reason - the normalisation of that criterion - was not investigated further). No other company changes.
**Text search without a model, LNC and UNM:** UNM states the figure in words: "the RBC ratio for our traditional U.S. insurance subsidiaries ... calculated on a weighted average basis using the NAIC Company Action Level formula, was approximately 44x%" (the parameter reads this). **LNC discloses no RBC ratio figure at all** (the 10-K defines the RBC ratio, the "company action level", and quotes an effect of "about 10 percentage points" on an estimated ratio, but no number with a percent sign near RBC or action level): synonyms cannot fill it.
Synonyms proposed for the extraction skills B 3.6.1 / G 3.2.1: "risk-based capital ratio", "RBC ratio", "total adjusted capital to ... action level", "company action level (CAL)", "authorized control level (ACL)", "ACL RBC ratio", "solvency ratio", "SCR ratio", "solvency margin ratio" - each with the basis in the same sentence.
**Recommendation:** `life_dominant_na` - adopt (small and principled: LNC +1.3, coverage 75 -> 90%; nothing else moves; the owner may want to extend the definition to the composites). `reg_basis_from_text` - adopt (UNM +1.7, coverage 100%; nothing else moves).

---

## 3. Rule M10 (a suspect figure) - how it works today, in rulebook language

*"A figure that fails a plausibility control is held back: it is not used in any calculation, the user sees it as missing and the coverage falls; the administrator sees it as wrong, with the reason."* In practice:
1. **Which controls trigger it.** One control today: `suspect_magnitude` (`src/pipeline/dq.py`): a monetary figure (revenue, total assets, total liabilities, equity, deposits, loans) that is more than 20 times (or less than 1/20) of **both** neighbouring years while the two neighbours are within 2.5 times of each other. A year at the edge of the series has one neighbour and is not judged. The control sees only figures that reached the pipeline; an AI extraction rejected by its own checks does not go through it.
2. **What the calculation sees.** The figure is removed from the list of facts before storing; `drop_facts` (new in this stage) also removes the same figure if an earlier load had already stored it. The engines see no value -> the item is *missing* (state), not zero.
3. **What the user sees.** Missing. **Coverage:** a missing item stays out of the computed points of its criterion and so lowers the criterion's share and the model's coverage (M4); if the criterion falls below 70% valid share it counts as not covered (M2). `ai_pending` and `not_applicable` do not lower coverage; `missing` does. Code matches the rule; a unit test was added (`test_m10_a_held_back_figure_is_missing_and_lowers_coverage`).
4. **What the administrator sees.** A row in `data_gap_review`, family `suspect_data`, priority 1, state `open`, reason "wrong (suspect_magnitude): <figure> against <neighbours> ...". The test database has 0 such rows today (no figure is currently held).
5. **How a figure leaves the state.** (i) The pipeline is fixed or the source corrected and the company is loaded again: the figure is no longer held, it is stored and used. (ii) `gaps fill` enters the figure by hand with a quote and a source; the facts are rescored. **Gap found: nothing closes the `suspect_data` row in either case** - `record_suspects` only opens rows; the closing logic (`refresh`, `record_core`) covers the other families, and `suspect_data` is excluded from it ("own lifecycle") that does not exist yet. A figure that was repaired would stay "wrong" in the administrator's list.
**Proposals (not implemented, for the owner's decision):** (a) close a `suspect_data` row (`fixed`) when the same figure is stored without being held in a later load, or entered by `gaps fill`; (b) record an extraction rejected by its own control as `suspect_data` too (today it is dropped quietly).

---

## 4. H-01 (Graham price score of banks and insurers)

**No code change was needed: the code already shows the Graham price score for banks and insurers as rulebook A.5 / X1 / P3 requires** (`src/scoring/bank.py:1199`, `src/scoring/insurance.py:1001`: below quality 55 the score stays shown and labelled; the buy price is "not suitable"). The sentence in the rulebook that says it is open is stale (a rulebook correction is the owner's).
Unit tests exist and pass: `test_v5_price_score_shown_labelled_when_graham_quality_below_55` (`tests/test_bank.py`), `test_graham_price_score_shown_labelled_when_quality_below_55` (`tests/test_insurance_pricing.py`).
Before/after for all banks and insurers = identical (no change). The stored valuations of banks/insurers with quality under 55: MET (Buffett 54.9, price score 0.0, scored), AIG (28.4, 0.0, scored), LNC (51.2, 5.82, scored), all with no buy price; FLG (Buffett 24.0 / Graham 43.4) is "cannot be valued" (no fair value), which is a valuation limit, not H-01.

---

## 5. Price scale (analysis only - no code change) - `scripts/state/cal_price_scale.txt`

**Buffett discount rate (DCF companies with stored inputs, 43: STANDARD 26, TECH 17):** price score above 0 for 17 companies at 9%, **14 at 10% (today)**, 12 at 11%; median price/fair value 1.37 / 1.64 / 1.96. STANDARD: 14 / 12 / 10 of 26 (median price/FV 1.23 / 1.42 / 1.61); TECH: 3 / 2 / 2 of 17 (2.25 / 2.57 / 2.89).
**Alternative scale** (0 at a 20% premium, 2 at par, 10 at a 40% discount, against today's 0 at 25% premium, 2.5 at par, 4.5 at +10%, 10 at +40%): Buffett - 6 of 96 valued companies move by more than 0.5 point (all down); zero price scores 52 -> 56; mean 1.91 -> 1.73. Graham - 2 of 95 move (down), zero 64 -> 69, mean 0.86 -> 0.77. The buy price does not change (it comes from the margin of safety of the quality score, M7).
**Price against quality (Spearman):** Buffett -0.06 (n=96), Graham -0.24 (n=94): no tendency of the scale to prefer weak companies that are cheap. Weak (quality under 55) and cheap (price score 5 or more): Buffett 3 (CAG 47 / 5.6, CNC 50 / 10.0, LNC 51 / 5.8); Graham 1 (CAG 37 / 6.0). Median price score of companies with quality 55-85 and 85+ is 0.0 in both models.
By profile (Buffett): BANK +0.49, TECH +0.39, STANDARD -0.30, REIT -0.01, INSURANCE +0.01. **Recommendation: do not change the scale.** The low price scores come from prices (median price/fair value 1.4-1.6 at 10%), not from the shape of the scale: moving the discount rate by one point changes 2-3 companies, the alternative scale moves 6 companies by about half a point. If the owner wants more spread, the discount rate (9%) is the larger lever and should be decided on a methodology basis, not on this table.

---

## 6. The AI answers stored as "insufficient evidence" with all sections present

Experiment: `scripts/cal_reask_ai.py` asked again 20 answers (test database, flash-lite, 23 attempts, shared counter), each with a sharpened instruction for the reason the code had rejected it. The new answers are in
`scripts/state/cal_ai_experiment.jsonl`, NOT in the database and NOT in the approval flow. Verification of the quotes: `scripts/cal_verify_quotes.py` (no model call; same normalisation as the production check),
full output in `scripts/state/cal_quote_check.txt`.

**Result in numbers (a correction of the earlier recap, which said 14):** 17 of the 20 came back as an answer; 3 stay "insufficient evidence" (ANET B3.1-Q3, AFG B3.8-Q6 and MKL B3.1-Q4, the last two with `quote_not_found` again).
All 24 quotes of the 17 answers are found word for word in the annual report (the code check passes) - **but a quote that exists in the report is not a quote that supports the level.** I read every quote against the scale of its question:

| # | Company / question | Level | Quote found word for word | Does the quote support the level? |
|---|---|---|---|---|
| 1 | UBER G3.1-Q3 | 2 | yes | **NO - topic only.** The quote lists the three segments. The claim "no customer above 10%" has no sentence behind it. (Mobility is $29.7B of $52.0B revenue, 57% - the quote does not address that either.) |
| 2 | EWBC G3.1-Q3 | 2 | yes | **NO - topic only.** Names the three operating segments; says nothing about customers above 10%. |
| 3 | LNC G3.1-Q3 | 2 | yes | **NO - topic only.** Lists four segments; nothing about customers or a critical product/license. |
| 4 | WY G3.1-Q3 | 2 | yes | **NO - topic only.** "We break out financial information ... by the business segments" is a sentence about reporting, not about dependence. WY is a housing-cycle business; the answer is unsupported either way. |
| 5 | SUI G3.1-Q3 | 2 | yes | Partly. 513 properties across three countries supports "no single-asset dependence"; it does not show "no customer above 10%" (plausible for residents, but not quoted). |
| 6 | ANET G3.1-Q3 | 0 | yes | **YES.** "Two customers ... 26% and 16%": 26% > 25% is exactly the scale for 0. (The earlier rejection `exposure_inconsistent` is gone.) |
| 7 | ANET G3.8-Q3 | 2 | yes | **NO - topic only.** "Gross margin remained constant at 64.1%" does not show that there are no one-time items; the scale needs impairments/restructuring/gains over 5 years relative to net income. |
| 8 | WY B3.1-Q5 | 2 | yes (2 quotes) | Partly. Quotes say what is owned and what is made; "to whom" is not in them. |
| 9 | NKE B3.1-Q5 | 2 | yes (2 quotes) | **YES.** What is sold, how (own stores / digital / wholesale), where. |
| 10 | ZION B3.1-Q5 | 2 | yes | Partly. What and where; "how money is made" is not in the quote. |
| 11 | INTC B3.7-Q3 | 0 | yes (2 quotes) | **YES.** "$3.1 billion of non-cash charges associated with the impairment of goodwill" = material goodwill impairment = level 0. |
| 12 | INTC B3.8-Q6 | 1 | yes (2 quotes) | **NO for the level.** The quotes are the industry's demand drivers (AI, PC refresh). The reasoning's key claim (growth "depends on cyclicality ... partnerships", "supply constraints") is not in any quote; the quotes are about the market, not the company's own growth record. |
| 13 | RF B3.7-Q3 | 2 | yes | Partly. Goodwill tested, fair value above carrying amount = no impairment; "acquisitions integrated and generated growth" is not shown. |
| 14 | **HRL B3.7-Q3** | 2 | yes | **NO - and the reasoning is contradicted by the report.** The quote is "continues to look for opportunities to make investments and acquisitions" (intent only). The reasoning says "zero goodwill impairments". The same 10-K says: a $71 million intangible impairment of the Planters trade name in Q4 FY2025, a $164 million non-cash impairment of the Indonesia minority investment, and the International reporting unit goodwill ($258.9M) "at heightened risk of impairment". Level 2 ("no material goodwill impairments") is not supported by the report; the model's answer is likely wrong. |
| 15 | ORI B3.1-Q1 | 2 | yes (3 quotes) | **YES.** Insurance underwriting (specialty commercial lines, title policies) described in plain words. |
| 16 | ADSK B3.1-Q2 | 2 | yes (2 quotes) | **YES.** Customer industries named (architecture, engineering, construction, design, media); BuildingConnected for general contractors and owners. |
| 17 | VICI B3.7-Q3 | 2 | yes | **NO - topic only.** A quote about combining two leases into one master lease says nothing about value created or about goodwill impairment. |

Count (17): supports the level - 5 (ANET G3.1, NKE, INTC B3.7, ORI, ADSK); partly - 4 (SUI, WY B3.1-Q5, ZION, RF); **does not support - 8 (UBER, EWBC, LNC, WY G3.1-Q3, ANET G3.8, INTC B3.8-Q6, HRL, VICI), of which HRL is contradicted by the report.**

### What the experiment shows

1. The sharpened `no_quote` instruction ("a quote is required even when no customer reaches 10%; quote the sentence that describes the customer base") makes the model **find a nearby sentence to satisfy the check, not evidence for the answer**. Of the 6 G3.1-Q3 answers it produced, 4 have a topic-only quote (UBER, EWBC, LNC, WY), 1 is partial (SUI) and only ANET is supported; ANET G3.8-Q3 has the same flaw. The code check passes them (quote exists, scale consistent), so in the normal flow they would have looked clean. That is worse than the stored "insufficient evidence", which at least tells the user the evidence is missing.
2. The code check verifies that a quote EXISTS; nothing verifies that it SUPPORTS. For the "absence" questions (no dependence, no one-time items, no impairments) a supporting sentence usually does not exist - the evidence is the absence of a disclosure.
3. HRL shows the danger concretely: a passing answer, 2 of 2, against a report that contains the impairments.

### Decision

**The sharpened instructions are NOT adopted and nothing was written to the database or sent for approval.** Not adopted until we understand how absence-type answers should be evidenced. Proposals for the owner's decision (not implemented):
- G3.1-Q3 / G3.8-Q3 / B3.7-Q3 ("absence" questions): accept `quote: none` when the model states which disclosures it looked for and did not find (e.g. "no customer table in the segment note"), and let a person approve it - rather than forcing a decorative quote.
- A mechanical "support" check for numeric scales: G3.1-Q3 levels 0/1 need a percentage in the quote (ANET passes it); level 2 with a quote that contains no percentage and no phrase such as "no customer" gets a flag `quote_does_not_address_scale`.
- For B3.7-Q3 the facts block should carry the impairment lines the code already extracts (HRL's intangible impairments were in the filing and were missed by the model); a contradiction check (answer 2 while the notes contain "impairment" with an amount above a threshold) would have caught HRL.
- The 3 remaining "insufficient evidence" (ANET B3.1-Q3, AFG, MKL) stay as they are: for AFG and MKL the model quotes a sentence that is not in the report, which is the correct reason to reject.

---

## 7. What to adopt - summary (every decision is the owner's; nothing is switched on)

| # | Item | Parameter / change | State now | Recommendation | Score impact when adopted (measured) |
|---|---|---|---|---|---|
| 1a | REIT 3.4.1 anchors | none | - | do not change | none (+1.3 of 4 points for 3 REITs if the zero moved to -2pp) |
| 1b | 10-year growth | `growth_window_10y` | off | do not adopt for the REIT gap | Buffett only; 44 of 115 move by more than 2 points; REIT mean 76.3 -> 75.7, others +0.5 to +2.3; REIT gap 0.5 -> 2.6 (wider) |
| 1c | REIT AI wording | notes in the skills (no skill-version change) | not done | adopt after a 20-call re-ask test | not measured; expected: REIT 17/17 share (81%) falls |
| 1d | weak REIT reference set | MAC, BDN, PK, DHC, HPP loaded in test | kept | keep; review rule for coverage under 80% with a dividend cut | BDN 48.9, DHC 56.3, PK 46.0 (separated); MAC 78.0 and HPP none (not caught) |
| 2a | life insurers 3.5 | `life_dominant_na` | off | adopt | LNC 51.2 -> 52.6, coverage 75% -> 90%; all other insurers unchanged |
| 2b | capital ratio basis in words | `reg_basis_from_text` | off | adopt | UNM Buffett 79.6 -> 81.3, coverage 90% -> 100%; all other insurers unchanged |
| 3 | M10 | code matches the rule (new test); `drop_facts` | on (a fix, no parameter) | close `suspect_data` rows when the figure is repaired; record control-rejected extractions as suspect | none today (0 held figures) |
| 4 | H-01 | none needed | already aligned | correct the stale rulebook sentence (owner) | none |
| 5 | price scale | none | - | do not change | none (alternative: 6 of 96 move by about 0.5 down) |
| 6 | 17 AI answers that were "insufficient evidence" | none | not adopted | **do not adopt the sharpened instruction** | none (8 of 17 answers not supported by their quote; HRL contradicted by the filing) |

Not decided here (owner): turning any parameter on; the rulebook corrections (the stale H-01 sentence, the REIT wording, the M10 lifecycle); extending `life_dominant_na` to composites.

### A bug found on the way (fixed, tested)
`WorkQueueRepository` read the whole queue with one request, and the API returns at most 1000 rows. The test queue passed 1000 rows (939 done + 55 queued + 6 failed = 1000), so the newest tasks (ids above about 1078) were **invisible to the runner**: the AI work of the new companies (PK, BDN, DHC) never ran, and `queue status` counted 1000 rows. Fixed: `_all()` reads page by page (used by `runnable`, `next_wait`, `list`, `counts`);
the fake database of the tests now also caps an un-ranged read at 1000 rows like the real API; test `test_a_queue_of_more_than_1000_rows_is_read_page_by_page`. The scheduler in production would have hit the same limit when its queue passed 1000 rows. One place was not changed: `src/sched/cleanup.py:161` reads the done/failed rows older than the retention without a range (it deletes less than it should, never more).

### Stage data kept (created by this stage, not deleted)
Companies MAC, BDN, PK, DHC, HPP in the test database (data, scores, AI answers, queue rows); `scripts/state/cal_ai_experiment.jsonl` is a file, not a table. Nothing in production.


---

# Part 2 - owner decisions of 2026-11-04 (what was done after the first report)

Test database only; nothing in production; golden, rulebooks and branch `security` untouched. Tests: 1001 passed.

## 2.1 Parameters switched on (decision 1)
`life_dominant_na` and `reg_basis_from_text` are now `true` in `config/calibration.yaml`; `growth_window_10y` stays `false`. All 115 companies rescored with no model calls. Only two companies moved:

| Company | Buffett before | after | Coverage before | after |
|---|---|---|---|---|
| LNC | 51.23 | 52.56 | 75% | 90% |
| UNM | 79.62 | 81.30 | 90% | 100% |

The price-scale change and the sharpened "no evidence" instruction were not adopted (decision 2).

## 2.2 M10 - suspect rows close themselves (decision 3)
`gap_review.close_suspects`: a `suspect_data` row is closed (`fixed`) when the figure is no longer held back by the pipeline (called from the runner after `record_suspects`) or exists in `financial_facts` (entered by `gaps fill`; also called from `refresh`). Unit test `test_m10_a_suspect_row_is_closed_when_the_figure_is_not_held_back_any_more_or_is_entered_by_hand`.

## 2.3 The 44 companies with `ai_pending` (decision 5)
Reason, one for all 44: they were created on 2026-10-25 as K5 companies and **no AI question was ever asked for them** (no row in `ai_assessments`, no `ai_assess` task in the queue). It is not a missing approval rule and not an experiment leftover. Separately, 537 extraction rows wait for manual approval (mostly REIT FFO/NAV); `approvals recheck` with the existing rules would approve only 2 (BDN, rule `b11_xbrl`) - not applied.
Proposal (nothing was approved or enqueued): enqueue `ai_assess` for the 44 at low priority, spread over about 3 days (about 20 calls each, about 900 attempts, against the shared 450/day cap); the answers then go through the existing approval rules, and what no rule covers stays for manual review.

## 2.4 REIT AI wording (decision 4) - NOT ADOPTED, the previous version stays active
Experiment: questions B3.2-Q4, B3.2-Q5, B3.7-Q5, B3.8-Q6 re-asked with the reworded 2/1/0 levels (profile INCOME_REAL_ESTATE only, version "<v>-reit", answers in `scripts/state/cal_reit_reask.jsonl`, not in the database). Questions 3.1.x were not changed (the first analysis found no REIT bias there). Scoring: `scripts/cal_reit_score.py`, full dump in `scripts/state/cal_reit_score.txt`.
Limits of the run: the 150-attempt cap was reached before every REIT was done; PK failed at setup (`KeyError: 'inputs'`), HPP has no Buffett score, one call failed on a network error (KIM B3.7-Q5). Fifteen REITs have a before/after comparison (12 strong, 3 weak: BDN, DHC, MAC).

(a) Distribution (17/17 on the nine AI items): before 12 of 15, after 6 of 15 (strong 11 -> 6 of 12; weak 1 -> 0 of 3). New answers: 63 x 2, 20 x 1, 5 insufficient evidence (earlier answers of the same questions: 53 x 2, 5 x 1, 2 x 0, rest missing).
(b) Quotes: 4 quotes are not found word for word in the report (BXP 3.8.6, HPP 3.8.6 twice, REXR 3.2.4 - all became "insufficient evidence", so they do not enter the score). The remaining quotes of the 63 answers of 2 were found verbatim; I read the reasoning and quote for the weak REITs and a sample of the others and they support the level (e.g. MAC 3.2.4: same-property NOI +1.8% and "seventeenth consecutive quarter of positive base rent leasing spreads"). **I did not read all 63 individually**; the full list is in the dump for the owner.
(c) Separation: strong REITs Buffett 76.6 -> 75.9 (-0.7), weak 61.0 -> 60.2 (-0.8): the gap is unchanged. Per weak REIT: BDN 48.9 -> 48.9, DHC 56.3 -> 56.1, **MAC 78.0 -> 75.7 (still above the strong mean)**, HPP none, PK not measured.
Decision by the owner's rule: the separation does not improve, so the reworded version is not adopted; `scoring.yaml` was not changed.

## 2.5 `growth_window_10y` - analysis before a decision (decision 6; the parameter stays off)
Method: `scripts/cal_growth_movers.py` records, for the 44 companies that move by more than 2 Buffett points, the series behind each growth call (5-year window vs the 10-year first-3 against last-3); `scripts/cal_growth_table.py` holds the classification; series in `scripts/state/cal_growth_classify.txt`. Sub-items that move: 3.3.3 (revenue), 3.8.2 (EPS), 3.8.3 (FCF / book value per share). Years are oldest first, so the ten years are FY2016-FY2025 and the 5-year window FY2021-FY2025.
**Limit:** the causes (events, years) come from the series themselves and from my general knowledge of the companies. I did **not** check each event against a quote from the filings, so class (b) rows are "event named, quote pending".
Classes: (a) the 5-year window is distorted by an abnormal period (COVID, the 2021-22 peak, the rate cycle, impairments); (b) material business change (merger/split/sale), where 5 years is right; (c) old years with wrong or inconsistent data.

By class and profile (n / up / down / mean change in Buffett points):

| Class | BANK | INCOME_REAL_ESTATE | INSURANCE | STANDARD | TECH | All |
|---|---|---|---|---|---|---|
| (a) abnormal period | 7 / 6 / 1 / +2.2 | 9 / 3 / 6 / -2.3 | 6 / 5 / 1 / +2.8 | 10 / 9 / 1 / +4.2 | 2 / 2 / 0 / +3.0 | 34 / 25 / 9 / +1.7 |
| (b) material change | 3 / 3 / 0 / +2.8 | 2 / 1 / 1 / +0.7 | 2 / 2 / 0 / +2.9 | 3 / 3 / 0 / +4.2 | - | 10 / 9 / 1 / +2.8 |
| (c) data bug | 0 | 0 | 0 | 0 | 0 | 0 |
| All | 10 / 9 / 1 / +2.4 | 11 / 4 / 7 / -1.8 | 8 / 7 / 1 / +2.8 | 13 / 12 / 1 / +4.2 | 2 / 2 / 0 / +3.0 | 44 / 34 / 10 / +2.0 |

(c): no wrong values found. Only data gaps (AMT and LNC first-year revenue missing, EXR three early EPS years missing, MAA nine years only), which shorten the 10-year window but do not distort it.

Findings:
- In class (a) the 10 years reflect the business better: in 25 of 34 cases the 5-year window starts on a peak (2021-22 demand, steel, chips, investment banking, low rates) or ends on a trough, and the 5-year growth is then understated. For REITs it is the opposite: the 5-year window starts in the COVID trough (HST, VTR, SLG, EPR, OHI), so the 5-year growth is a rebound that is overstated and the 10 years lower it (6 of 9 down).
- In class (b) the 10 years are inflated by acquisitions (CI revenue 27.6% a year, CNC, TFC, FHN, RNR, MOH, EXR): 9 of 10 go up, but because of purchased growth, so 5 years is right there. DLR and ONB are the exceptions where the window itself begins at the merger.
- Because of (b), 10 years without an exception would reward serial acquirers.

**Recommendation: 10 years with an exception for material business change.** Concretely: use 10 years unless a year-on-year revenue jump above about 1.5x (or a fall below about 0.6x) falls inside the ten years; in that case use the years after the break (at least 5). On the 44 companies this would send the 10 class (b) companies back to the shorter window. It is not enabled and is not coded: a decision on the exception rule, and checking the (b) events against filings, come first. As the first report found, 10 years does **not** close the REIT gap (REIT mean 76.3 -> 75.7, gap 0.5 -> 2.6), so it should be decided as a general rule and not as a REIT fix.

### Classification of the 44 companies
| Ticker | Profile | Class | Buffett off -> on | Delta | Sub-items moved (points) | Cause (years / event) |
|---|---|---|---|---|---|---|
| BOKF | BANK | a | 81.8 -> 84.2 | +2.4 | 3.3.3 +0.54, 3.8.2 +1.85 | Rate cycle: FY21-22 earnings on the low-rate/reserve-release peak; 10y growth 7.5%. |
| C | BANK | a | 57.1 -> 59.2 | +2.1 | 3.3.3 -1.56, 3.8.2 +3.0 | FY17 tax-reform charge and FY22 peak; 5y EPS start avg 4.7+10.1 vs end 7.0 - rate cycle and one-offs. |
| GS | BANK | a | 66.1 -> 72.9 | +6.8 | 3.3.3 +3.0, 3.8.2 +2.74 | FY21 record IB year (EPS 59) opens the 5y window; 10y first-3 vs last-3 smooths it. |
| RF | BANK | a | 87.0 -> 89.9 | +2.9 | 3.3.3 +0.12, 3.8.2 +2.78 | FY21-22 low-rate/reserve-release peak (EPS 2.49/2.28). |
| WAL | BANK | a | 80.6 -> 83.6 | +3.0 | 3.8.2 +3.0 | FY21 revenue/EPS peak at 5y start; rate cycle. |
| WFC | BANK | a | 76.5 -> 72.9 | -3.6 | 3.3.3 -0.84, 3.8.2 -1.75 | FY20 EPS 0.43 and FY22 litigation/reserve charges; 5y 11.7% is rebound from a conduct-penalty year. |
| ZION | BANK | a | 79.7 -> 81.8 | +2.1 | 3.3.3 -0.44, 3.8.2 +2.54 | Rate cycle: FY21-22 low-rate peak at the start of the 5y window. |
| AMT | INCOME_REAL_ESTATE | a | 76.2 -> 84.0 | +7.8 | 3.3.3 +1.03, 3.8.2 +3.0, 3.8.3 +2.61 | EPS FY21-22 start vs FY16-18 base; 5y EPS growth -4% only because FY24 EPS dip (7.4) from a one-off impairment year. |
| EPR | INCOME_REAL_ESTATE | a | 82.0 -> 79.1 | -2.9 | 3.3.3 -0.81, 3.8.2 -0.84, 3.8.3 -0.84 | COVID FY20 (EPS 0.58) sits at the start of the 5y window region; 10y shows the true slower trend. |
| EQR | INCOME_REAL_ESTATE | a | 85.7 -> 79.6 | -6.1 | 3.3.3 -1.44, 3.8.2 -0.93, 3.8.3 -2.02 | EPS FY21-22 (2.5-3.0) start from gain-on-sale distorted years; 10y gives 2.9%. |
| HST | INCOME_REAL_ESTATE | a | 91.2 -> 84.0 | -7.1 | 3.3.3 -2.61, 3.8.2 -1.73, 3.8.3 -1.73 | COVID FY20 revenue 1.6bn (from 5.4bn) just before the 5y window: 5y 'recovery growth' 20% is a rebound, 10y 0.7% is the real trend. |
| MAA | INCOME_REAL_ESTATE | a | 73.0 -> 76.0 | +3.0 | 3.8.2 +1.27, 3.8.3 +1.27 | FY21-22 start vs FY25 trough; only 9 years of data. |
| OHI | INCOME_REAL_ESTATE | a | 73.4 -> 70.4 | -3.0 | 3.3.3 -0.24, 3.8.2 -1.14, 3.8.3 -1.14 | COVID years FY20-22 (EPS 1.96-1.99); 5y start low in 5y/10y differs by base. |
| PSA | INCOME_REAL_ESTATE | a | 76.7 -> 79.2 | +2.6 | 3.8.2 +1.12, 3.8.3 +0.88 | Acquisition of Simply Self Storage (2023) is small; EPS FY21-22 step-up; cycle. |
| SLG | INCOME_REAL_ESTATE | a | 57.8 -> 48.5 | -9.3 | 3.3.3 -2.33, 3.8.2 -2.8, 3.8.3 -2.8 | COVID/office downturn plus FY22-23 impairments (EPS 2.5, -1.1); 5y 21% is the rebound from FY23. |
| VTR | INCOME_REAL_ESTATE | a | 89.0 -> 83.0 | -6.0 | 3.8.2 -3.0, 3.8.3 -3.0 | COVID FY20-21 dip (EPS 2.1-2.2) at the start of the 5y window: rebound growth 14%, 10y -2.6%. |
| AFL | INSURANCE | a | 80.4 -> 82.5 | +2.1 | 3.8.2 +0.58, 3.8.3 +0.82 | 5y window starts FY21-22 on a 2021 EPS peak; 10y steady 9-10% EPS growth. |
| ALL | INSURANCE | a | 66.0 -> 68.2 | +2.1 | 3.8.2 +1.5, 3.8.3 -0.33 | EPS FY20-22 swings (5.0, -5.1, -1.2) from the 2022 catastrophe/inflation year; 5y start sits in the trough/peak pair. |
| LNC | INSURANCE | a | 51.2 -> 48.0 | -3.3 | 3.3.3 +0.56, 3.8.3 -2.61 | Annuity/derivative-mark volatility (EPS 19.96 .. -4.92); FY25 recovery. Revenue FY16 missing (data gap, not a wrong value). |
| ORI | INSURANCE | a | 77.4 -> 84.7 | +7.3 | 3.3.3 +2.63, 3.8.2 +2.87, 3.8.3 +0.53 | FY21 peak EPS (5.05) at the start of the 5y window; 10y 9.6%. |
| RLI | INSURANCE | a | 87.6 -> 91.4 | +3.8 | 3.8.2 +3.0 | FY21 special dividend/investment-gain year (EPS 6.37) in the 5y window start. |
| SIGI | INSURANCE | a | 82.3 -> 87.0 | +4.8 | 3.8.2 +2.31, 3.8.3 +1.4 | FY21-22 EPS spike vs trough; growth is smooth over 10y. |
| ELV | STANDARD | a | 88.0 -> 94.3 | +6.3 | 3.8.2 +2.67, 3.8.3 +2.27 | EPS 5y flat (FY21-22 peak vs FY24-25 fall on Medicaid cost trend); 10y trend is a smooth 10%. FCF FY21 9.7bn is a one-off timing peak. |
| HD | STANDARD | a | 83.9 -> 90.5 | +6.6 | 3.3.3 +1.7, 3.8.2 +2.84, 3.8.3 +0.83 | FY21-22 pandemic-demand peak at the start of the 5y window; 10y 9.5% vs 5y -3%. |
| KHC | STANDARD | a | 38.7 -> 40.9 | +2.2 | 3.8.3 +1.71 | Impairment years (FY18 EPS -8.4, FY25 -4.9) drive the series; no sustainable base in either window (no growth rate in either). |
| KR | STANDARD | a | 73.3 -> 76.8 | +3.5 | 3.3.3 +0.8, 3.8.2 +0.14, 3.8.3 +2.53 | FY17 and FY21-22 one-off gains (FCF 1.2bn / 3.9bn); EPS FY25 1.54 from impairment. 5y start/end ratios are dominated by single years. |
| NKE | STANDARD | a | 80.7 -> 84.4 | +3.7 | 3.3.3 +2.37, 3.8.2 +1.13, 3.8.3 +0.23 | FY21 post-COVID rebound opens the 5y window; FY24-25 downturn at the end. 10y smooths the cycle. |
| NUE | STANDARD | a | 64.4 -> 74.8 | +10.4 | 3.3.3 +3.0, 3.8.2 +3.0, 3.8.3 +2.48 | FY21-22 steel-price super-cycle (EPS 23-29) opens the 5y window; 10y 13.5%. |
| PG | STANDARD | a | 91.5 -> 94.7 | +3.2 | 3.3.3 +0.91, 3.8.2 +1.44, 3.8.3 +0.85 | FY17-19 impairment/divestiture one-offs (Gillette impairment FY19, brand sale FY17) depress the 10y base; effect small (3.9% vs 8.7%). |
| SJM | STANDARD | a | 41.1 -> 37.5 | -3.6 | 3.3.3 -0.68, 3.8.3 -2.88 | Impairment years FY19-24 (EPS -11.6, -0.9); FCF dip FY22-24. (Hostess 2023 acquisition adds a small b.) |
| TGT | STANDARD | a | 75.7 -> 78.2 | +2.4 | 3.3.3 +3.0, 3.8.2 +2.29, 3.8.3 -2.85 | FY21 pandemic peak opens the 5y window; FY23 loss year (-1.5bn FCF/ -.). 10y 7.6% vs 5y -5.4%. |
| UNH | STANDARD | a | 73.2 -> 80.0 | +6.8 | 3.8.2 +2.48, 3.8.3 +2.82 | FY24-25 Optum/medical-cost year hits the end of both windows; difference is the early years (EPS 7->14 ramp) vs 2021-22. (Change Healthcare 2022 acquisition is small vs revenue.) |
| ADI | TECH_ASSET_LIGHT | a | 78.2 -> 81.5 | +3.3 | 3.8.2 +2.17, 3.8.3 +1.12 | FY21-22 start of window is the post-COVID chip peak; EPS/FCF 5y start avg high vs 10y start (FY16-18) low base; FY24 dip is the cycle. (Acquisition of Maxim 2021 also lifts revenue: partial b.) |
| TXN | TECH_ASSET_LIGHT | a | 72.4 -> 75.1 | +2.7 | 3.3.3 +1.23, 3.8.2 +1.47 | FY21-22 cycle peak opens the 5y window; FY24-25 FCF collapse from the capex programme (an investment cycle, not a data issue). |
| FHN | BANK | b | 76.1 -> 79.1 | +3.1 | 3.3.3 +1.36, 3.8.2 +1.7 | IBERIABANK acquisition (Jul 2020): revenue 1.9bn->3.2bn; 10y 12% is partly M&A. |
| ONB | BANK | b | 77.6 -> 79.6 | +2.1 | 3.8.2 +1.78 | First Midwest merger (Apr 2022): revenue 0.81bn->1.7bn. The 5y window starts at the merger year. |
| TFC | BANK | b | 65.8 -> 69.2 | +3.3 | 3.3.3 +3.0 | BB&T/SunTrust merger (Dec 2019): revenue 12.6->22.7bn; FY23 revenue 13.3bn = securities-repositioning loss. |
| DLR | INCOME_REAL_ESTATE | b | 88.5 -> 85.5 | -3.0 | 3.8.2 -1.27, 3.8.3 -1.27 | Interxion acquisition (2020) lifts revenue 3.2->3.9bn; EPS 10y 4.2% vs 5y 8.4% - 5y reflects the larger company. |
| EXR | INCOME_REAL_ESTATE | b | 70.1 -> 74.4 | +4.3 | 3.8.2 +2.14, 3.8.3 +2.14 | Life Storage merger (Jul 2023): revenue 1.9->2.6->3.3bn. EPS series has 3 missing early years (data gap, not a wrong value). |
| AIG | INSURANCE | b | 28.4 -> 31.8 | +3.4 | 3.8.2 +1.5, 3.8.3 +0.13 | Corebridge deconsolidation FY22-24: revenue 49.9bn->29.2bn; EPS series FY16-22 swings (-6.5 .. +13) from hurricane/reserve losses. 10y mixes a different, larger company. |
| RNR | INSURANCE | b | 74.2 -> 76.4 | +2.3 | 3.8.2 +1.5, 3.8.3 -0.0 | Validus (Nov 2018) and Tokio Millennium Re (2019) acquisitions; revenue 1.6bn->11.7bn. EPS swings from catastrophe years. |
| CI | STANDARD | b | 71.7 -> 75.9 | +4.2 | 3.8.2 +3.0, 3.8.3 +0.3 | Express Scripts acquisition (Dec 2018): revenue 48.7bn -> 153.6bn in one year; 10y revenue CAGR 27.6% is M&A, not organic. 5y window (FY21+) excludes it. |
| CNC | STANDARD | b | 49.6 -> 53.5 | +3.8 | 3.8.3 +3.0 | Health Net (2016) and WellCare (Jan 2020) acquisitions; revenue 60bn->111bn. FY25 EPS -13.5 is a one-off loss year in the 5y end. |
| MOH | STANDARD | b | 84.4 -> 89.1 | +4.7 | 3.8.2 +1.27, 3.8.3 +2.38 | Acquisitions: Magellan Complete Care (2022), ConnectiCare (2022); revenue 17.8->45bn. FY25 FCF/EPS fall is a one-off year. EPS 10y 52.9% is from a near-zero FY17-18 base. |
