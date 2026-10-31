# K6d-2 acceptance run on test — stalls report (6 companies), 2026-10-29

Database: test. Model: Gemini flash-lite. Shared daily counter at the end of the run: 249 of 450.
Preflight (all five were NEW in test, in the CSVs and in the golden files): `scripts/state/acceptance_preflight_2.txt`. AVB was added afterwards (it is not in the SEC ticker list; see the resolve fix).
Logs: `scripts/state/acceptance_run_2.log` (CFG, AFG, VICI, NKE, NOW), `scripts/state/acceptance_run_3_avb.log` (AVB).

## 1. Summary

| | Reached final without contact | Notes |
|---|---|---|
| CFG (bank) | yes | 7/7 tasks done; ~2.5 h, slowed by network retries |
| AFG (insurer) | **no** | `ai_assess` deferred to 2026-10-30 08:00 UTC after the run budget was spent; 3 more tasks queued behind it; 11 criteria `ai_pending` |
| VICI (REIT) | yes (final), but **33 extraction rows pending approval**; most REIT criteria missing |
| NKE (regular) | yes | EBIT / interest not derived although XBRL has net interest |
| NOW (tech) | yes | nothing missing |
| AVB (REIT) | yes | no price (yfinance returned none); 5 rows pending approval |

5 of 6 reached a final state with no manual contact in the run. AFG did not. One manual step during the closing work (not one of the 6): HSY task 65 was re-queued by hand.
Code changes made before the run to unblock AVB: resolve now reads `CIK_OVERRIDE` (AVB is missing from SEC company_tickers.json).

## 2. Stalls (every place the pipeline stopped or needed contact)

1. **AFG - run budget deferral until tomorrow (BUG).** `load` runs the whole queue, and the 40-request cap is per run, not per company. Other companies' tasks (HSY, KO, PEP, PG, HBAN, JPM, AVB retries) used the budget. When the cap was reached, the task was deferred with `next_run_at` = next daily quota reset (08:00 UTC next day), as if the daily cap had been hit. `ai-queue --tickers AFG` then ran nothing (0 tasks), because the task is not due. Fix needed: a run-budget stop must leave the task `queued` (due now), and the cap must count per company.
2. **CFG - 2.5 h load.** Network `ConnectError`, retried after 30 s several times; plus the whole-queue behaviour above. Not a data stall.
3. **JPM `ai_background`: `ReadError WinError 10054`** (a task of another company run by the CFG session). It came back and finished (`done`). No recovery code was needed.
4. **CFG - CET1 requirement.** Log: "V9 computed CET1 requirement 9.00 != stated 7.00; stated used". Approved extraction has SCB 4.5% (-> 9.0), no stated requirement row. I could not trace where the 7.00 "stated" value entered (the default 7.0 in `auto_config`/`scoring.py` line 113 is the suspect). **I earlier called it a documented default; that was not verified.** Treat as a suspected bug: the score uses 7.0 instead of 9.0. This counts as a stall.
5. **AVB - price.** `$AVB: possibly delisted; no price data found`. `price: no_price`. Buffett 3.7.1 (annual average prices) is missing because of it. Cause not investigated (symbol mapping / yfinance). Open.
6. **AVB - earlier `not_found`** (fixed in resolve before the run; the old failed task remains in the table as history).

## 3. Missing data per company (Buffett / Graham)

Legend: N/A = not relevant; NR = company does not report (not in XBRL or the filing); SH = short history; XNP = exists in XBRL, not pulled; EF = extraction failed; EREJ = extraction rejected; PA = waiting for approval. "Bug?" = whether it is a defect.

### CFG (bank)
- B 3.2.1a/b, G 3.5.4: N/A (matrix). Not a bug.
- B 3.6.5 and G 3.2.2 (LCR): NR in the 10-K; public disclosures not found (D12). Not a bug.
- CET1 buffer item: scored on 7.0 instead of 9.0 - see stall 4. Bug?: probably yes.

### AFG (insurer)
- B 3.2.1a/b, 3.8.4; G 3.5.4: N/A (matrix).
- B 3.1.1-3.1.5, 3.2.4, 3.2.5, 3.7.5, 3.8.6; G 3.1.3, 3.1.4: AI questions not run (stall 1). **Bug: yes** (queue).
- B 3.6.1, G 3.2.1 (regulatory capital ratio): EF - the AI found no numeric group ratio. 5 AFG rows were rejected. Whether the filing has one is not verified. Bug?: unknown.
- G 3.2.2, 3.7.2, 3.7.3 (fixed maturities, total investments, credit quality): XNP/EF - the known next-stage item (investments and debt of insurers from XBRL). **Bug: yes (known gap).**

### VICI (REIT)
- B 3.2.1a/b, 3.2.3, 3.7.1 (no buybacks): N/A.
- PA: 33 rows pending (reported FFO, AFFO, NOI by segment, maintenance capex, undrawn facilities). Items that depend on them: B 3.2.2a/b, 3.3.x, 3.4.1-3, 3.5.1-2, 3.7.3-4, 3.8.2-3, 3.8.5 and G 3.2.x, 3.3.1-2, 3.5.3-4, 3.7.1-2, 3.8.x.
- B 3.6.3 and G 3.3.3: NR (US GAAP, no fair value of real estate; rule). Not a bug.
- G 3.4.1-3 and 3.6.1-3 say "fewer than 5/6 years of net income / EPS" although the facts hold net income for 9 years and EPS for 8 (FY2018-2025). **Suspected bug** (the engine does not use these series, or it needs FFO/normalized values); to investigate.
- B 3.6.1/3.6.2, G 3.2.1, 3.3.1 (EBITDAre, fixed charges): interest expense is in XBRL (9 years); the message names the gains-on-sale line, D&A or a debt tag. Suspected XNP. To investigate.
- B 3.8.4, 3.8.5: depend on the above.
- Note: 33 pending rows at once is itself a finding: the approval rules leave all FFO/NOI rows pending for this REIT.

### NKE (regular)
- B 3.1.5: AI insufficient evidence, rejected. EREJ. Not a bug.
- B 3.2.2a/b, 3.2.3, 3.4.1, 3.6.1, 3.6.2, 3.6.4, 3.8.4; G 3.3.3, 3.3.4, 3.8.4: no EBIT, no interest expense in any year ("ebit: no data", "interest_expense: no data"). companyfacts has `IncomeLossFromContinuingOperationsBeforeIncomeTaxes...` (pretax, 10 years) and `InterestIncomeExpenseNonoperatingNet` (net interest, to FY2026), but no `OperatingIncomeLoss` and no gross interest expense. **XNP: yes - bug / derivation gap** (EBIT = pretax + net interest expense could be derived and flagged as derived).

### NOW (tech)
- Nothing missing. G 3.5.1-3.5.4, 3.6.1 are `true_zero` (no dividends) - correct by rule. Data warnings only: interest expense missing FY2023-2025, balance identity flagged for FY2016 (7.6%).

### AVB (REIT)
- B 3.2.1a/b, 3.2.3; G 3.7.3: N/A (matrix / residential tenants).
- B 3.4.1, 3.4.2, G 3.3.3, 3.7.1, 3.7.2: stabilized NOI / same-property NOI / occupancy not extracted; 5 rows PA (stabilized_noi 3, undrawn facilities 2). PA/EF. Bug?: to check whether the filing discloses them.
- B 3.6.3: NR (no fair value; rule).
- B 3.7.1: no annual average prices (stall 5).
- G 3.2.2: "debt maturities (XBRL) missing". **Suspected XNP** - to check the tags.
- G 3.5.4, 3.8.2: maintenance capex not extracted (EXT-RE-MAINT returned 3 rows, accepted as a bare list). EF.

## 4. Totals

- Reached a final state with no contact: 5 of 6 (CFG, VICI, NKE, NOW, AVB). AFG: no.
- Defects among the gaps (not "the data does not exist"): AFG queue deferral; CFG CET1 7.0 vs 9.0 (suspected); NKE EBIT/interest (XNP); AFG insurer investments (known); VICI net income/EPS windows and EBITDAre (suspected); AVB price and debt maturities (suspected). Genuinely absent or N/A: LCR (CFG), fair value of real estate (VICI, AVB), gross margin / matrix items, residential tenant concentration, no dividends / buybacks.
- Not yet verified against the filings: AFG capital ratio, VICI/AVB same-property NOI and occupancy.

## 5. Open items

1. Queue: run-budget stop must not defer to the next day; the cap must be per company; `load` should run only the loaded ticker's tasks.
2. CFG CET1: trace the 7.00 and fix.
3. NKE: derive EBIT from pretax and net interest (flagged as derived).
4. VICI: why net income/EPS are not used by the Graham real-estate items; why 33 rows stay pending.
5. AVB: yfinance returns no price; debt maturities.
6. Next stage (agreed): insurers' investments and debt from XBRL; what a REIT lacks for the Graham score.
7. **Security stage (not now, agreed):** move `CIK_OVERRIDE` to a DB table `ticker_overrides` that the admin edits; a ticker that is not in the SEC list and not in the mapping opens an automatic ticket to the admin.
8. Uncommitted: acceptance_preflight.py, stale-task recovery, d2/content fixes, resolve fix, tests (893 pass). Nothing applied to prod.
