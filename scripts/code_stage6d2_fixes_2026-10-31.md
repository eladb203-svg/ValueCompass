# K6d-2 fixes after acceptance run 2 - 2026-10-31

Database: test only. Production was not touched. Model: Gemini flash-lite. Deleted data: none.
Tests: all pass (see the end). Golden files: not changed.

## 1. The queue (decisions of 2026-10-29)

| # | Rule | Where | Test |
|---|---|---|---|
| 1 | Company after company until it is finished. The turn of a company = the best priority among its open tasks, then its arrival (its oldest open task); fixed for the length of a run. Tasks of different companies do not mix. | `WorkQueueRepository.runnable(sticky)` | `test_companies_run_one_after_the_other_until_each_is_finished` |
| 2 | `load <T>`, `score <T>` and `ai-queue --tickers T` run only the tasks of T. The rest of the queue belongs to the scheduler. | `scripts/vc.py` | `test_only_the_tasks_of_the_given_ticker_run` |
| 3 | Limit per company = 40 request attempts per annual report (tasks of that fiscal year), counted per company, kept in each task's payload (`calls`). Over the limit: the company is `failed` with the reason "חריגה ממספר הקריאות — חשד ללולאה", its open tasks fail, the administrator is alerted. `support_tickets` does not exist yet (it is in the security spec), so the alert is a line marked `admin_alert` in `scripts/state/admin_alerts.log` and on stderr. No postponement to another day. | `QueueRunner._trip`, `alert` | `test_a_company_that_uses_its_call_limit...`, `test_calls_of_earlier_tasks_count...` |
| 4 | `deferred_quota` only when the daily cap (450) is spent, with the reason. A spent run budget (`--budget`) leaves the task `queued`, due now (the attempt does not count). | `WorkQueueRepository.release`, runner | `test_the_daily_cap_defers_but_a_spent_run_budget_does_not`, `test_the_budget_stops_ai_tasks...` |
| 5 | Temporary network error (ConnectError, ReadError, timeout, DNS, WinError 10054/10060, also inside a wrapper): back to the queue with a wait of 1, 2, 4, 8 minutes, up to 5 attempts; only a permanent error (3 attempts) or exhausted attempts make it `failed`. From the command line the run waits for a retry that is due within 15 minutes; the wait is reported separately (`waited for network retries`). | `is_transient`, `_failed`, `_wait_retry` | `test_a_temporary_network_error_waits...` (5 error types), `test_a_permanent_error...`, `test_the_run_waits_for_a_due_network_retry...`, `test_is_transient_sees_through_a_wrapper` |
| 6 | Stay awake: `SetThreadExecutionState(ES_CONTINUOUS \| ES_SYSTEM_REQUIRED)` while `vc.py scheduler` runs (released when it stops), and in `load`, `score`, `ai-queue`. The screen turns off as usual. | `src/sched/awake.py` | `test_keep_awake_asks_windows_and_releases` |
| 7 | AFG completed with the ordinary command (`vc.py ai-queue --tickers AFG --budget 40`): the deferred task was already due (10:00 Israel had passed), `ai_assess`, final score, D2 and the background text ran. AFG is `complete`, no manual step. | | |

A note on item 3: the limit counts the attempts that were made, including the retries inside one call (the shared guard counts every attempt).

## 2. Data bugs

### 2.1 CFG, CET1 requirement 7.00 (found: a wrong entity, not a default)
- The 10-K table lists the group (CFG: required 9.0, ratio 10.6) and its subsidiary bank (CBNA: required 7.0, ratio 12.3). Both were stored (`...|CFG...|0`, `...|CBNA...|1`). `to_reg` put them in one dictionary and the last row won: the subsidiary's requirement **and ratio** (7.0 / 12.3) replaced the group's (9.0 / 10.6). The "V9 computed 9.00 != stated 7.00" warning was this. My earlier statement that 7.00 was the documented default was wrong.
- Fix (`src/scoring/ext_items.py`, banks only): one value per item - the entity named like the ticker, else the first one listed; two rows of the same entity keep the later one. Order of priorities as asked: the requirement stated in the filing, then 4.5 + SCB + G-SIB (V9), then the marked default. The filing states 9.0 for CFG (SCB 4.5 also gives 9.0), so V9 now agrees and the warning is gone.
- Only CFG among the banks in test has duplicated entities (checked in `extraction_items`). Insurers were left as they were on purpose.
- CFG before -> after: Buffett 70.35 -> 68.55, Graham 69.73 -> 64.62 (coverage 98% / 96% unchanged).
- Tests: `tests/test_k6d2_entity_choice.py` (3).

### 2.2 NKE, EBIT and interest
- NKE has no `OperatingIncomeLoss` and no gross interest-expense tag; it has `InterestIncomeExpenseNonoperatingNet` (positive = net interest income; 161m in FY2024).
- Fix (`sec_companyfacts.py`): when a year has no gross interest tag and a net line exists, interest expense = - net line (`DERIVED: ...`, stored `source_kind=derived`), and EBIT = pretax + interest expense (the existing derived formula) = pretax - net interest income. A net interest income gives a non-positive "interest expense", so the coverage state is `zero_interest` (the net line cannot tell the gross interest). A gross tag is never replaced.
- Tests: `tests/test_k6d2_net_interest.py` (3: income, expense, gross tag wins).
- Other companies in the local cache that this touches when reloaded: HBAN (2 yrs), PNC (2), NUCOR (1), AGNC (2), ABNB (5). Golden files were not changed (no golden is regenerated).
- NKE before -> after: Buffett 69.83 -> 80.67 (coverage 61% -> 98%), Graham 80.99 -> 82.70 (83% -> 100%).

### 2.3 VICI, "fewer than 5 years of net income" and EBITDAre
- For a REIT the Graham series "net income" and "EPS" are normalized FFO (`_View.series`), so the message names a different thing than what is missing. The real cause: FFO needs the gains-on-sale line and VICI's XBRL has **no gain/loss on sale or disposal element at all** (checked: no such tag in any namespace of companyfacts), so FFO, normalized FFO and EBITDAre were empty in every year. The rule "gains on sale are not assumed zero" is deliberate (they decide FFO).
- Fix (`realestate_facts.py`, `has_sale_gain_tag`): if the company's XBRL has no gain/loss-on-sale-or-disposal element with an annual value in any namespace, the missing line is 0, flagged `assumed_zero (no gain / loss on sale element ...)`. The company's own FFO reconciliation (AI extraction) still overrides it. **This narrows a deliberate rule; it needs your approval to stay.** Companies that tag any such element keep the old behaviour.
- Test: `test_a_company_without_any_sale_gain_element...` in `tests/test_realestate.py`.
- VICI before -> after: Buffett none (coverage 10%) -> 86.70 (81%); Graham none (10%) -> none (55%, below the 60% needed).

### 2.4 AVB, "possibly delisted" (it is: the company merged)
- SEC submissions of CIK 0000915912 (read from the cache, 2026-10-30): Form **25-NSE filed 2026-08-17**, Form **15-12G 2026-08-27**, **15-15D 2026-09-16**, merger communications (425) and an S-4 on the successor from May-June 2026; the entity has **no current ticker**. The entity of EQR (CIK 0000906107) was renamed **VIVMARK RESIDENTIAL (VMRK)** on 2026-08-12.
- Fix: `resolve.delisting_reason` -> `unsupported` with the evidence ("Form 25-NSE filed ..., Form 15-12G ..., merger filings ...; no price and no score until a successor files its own annual report (E2)"). `CIK_OVERRIDE_STALE` marks AVB and EQR as stale: a warning is printed and E2 is no longer waived for them. A Form 25 for another class of security does not delist a company whose common ticker is still current (test).
- AVB in test after `vc.py load AVB`: `unsupported`, with the reason above. Its history stays in the database.
- Tests: `tests/test_pipeline_core.py` (3, including the replaced AVB test: the "manual map" feature is tested with a made-up ticker).

### 2.5 AFG, investments and debt
- Regulatory capital ratio (B 3.6.1, G 3.2.1): the 10-K says only "the capital ratios of all AFG insurance companies exceeded the RBC requirements" - no number. Correctly `not_disclosed`. **Not a bug.**
- XBRL: AFG has `AvailableForSaleSecuritiesDebtSecurities` (11,052m = the fixed maturities already extracted), `EquitySecuritiesFvNi` (785m), mortgage loans (947m), `LongTermDebt` (1,820m, already a fact `debt_lt`), `DebtInstrumentCarryingAmount` (1,848m). There is **no `Investments` total tag**; a sum of these would be a partial numerator (Q8b says no), so no XBRL total was invented.
- The balance sheet shows "Total cash and investments 17,182". The block EXT-INS-INV did not look at the balance sheet. Fix: the block now also reads the balance-sheet section (`X-BS`) and the item says "when only a total that includes cash is stated, report it with INCLUDES_CASH in the basis" (block version 2 -> 3). **Stored answers now belong to a skill version: a changed version is asked again** (`ask_block`).
- Result: `inv_total` = 17,182m (INCLUDES_CASH) was extracted, but the block control `inv_sum` fails (the model returned the mortgage-loan line twice for FY2025: 947 and 791, 791 being FY2024's, so the categories sum to 17,723 vs 17,182, 3.1%) and the 12 rows of the block are `pending`. Rule not changed. So G 3.2.2 and G 3.7.3 are still missing; **this one is an extraction-quality problem (duplicate row), waiting for approval.**
- Graham coverage of AFG: before 82% -> after 82% (score 72.39 unchanged); Buffett 88% (77.90) unchanged.

### 2.6 REITs, Graham score (MAA, DLR, VICI, AVB)
Total debt, a generic fallback (`realestate_facts.py`): a REIT without a hand-made debt entry and no `LongTermDebt` total now takes a tagged `NotesPayable` total, else the sum of at least two of SecuredDebt, UnsecuredDebt, SeniorNotes, LineOfCredit, ConvertibleDebt (flagged `SUM:`; the 9% interest plausibility check still applies). MAA: 5,405m (= secured 360 + unsecured 5,045); DLR: sum of four lines.

| Graham criterion | MAA | DLR | VICI | AVB | What is missing | Source to complete it |
|---|---|---|---|---|---|---|
| 3.2.1 / 3.3.1 net debt, EBITDAre | fixed (debt total) | fixed (debt total) | fixed (gains) | had | XBRL, was a bug | done |
| 3.2.2 debt maturities | missing | missing | missing | missing | year-1/2 maturities: AI rows rejected (`period_mismatch`, `quote_not_found`); XBRL tags exist for MAA only to FY2021 (years 2-5) and DLR to FY2023, none for AVB; VICI has them, but the criterion there needs committed undrawn facilities (pending approval) | text of the debt note (AI), or later XBRL tags; VICI/AVB/DLR undrawn facilities are `pending` |
| 3.3.2 unencumbered NOI | missing | missing | missing | not computed | `not_disclosed` by the AI in all four | not in the 10-K as a ratio; needs the supplemental package (not a filing) |
| 3.3.3 stabilized NOI | missing | missing | missing | missing | stabilized NOI `pending` (AVB 3, MAA 1) or `not_disclosed` (DLR, VICI) | 10-K MD&A text (AI), approval |
| 3.5.4 / 3.8.2 owner earnings level, gap | missing | missing | missing | missing | maintenance capex: AI `not_disclosed` (MAA, AVB), `rejected` quote_not_found (DLR), `pending` (VICI) | text of the capital-expenditure section (AI), approval |
| 3.7.1 occupancy | missing | missing | missing | missing | the extraction has the current and the prior year (2 values); the criterion needs 3 years | extraction from the two earlier 10-Ks (3 more calls per company); XBRL has no occupancy |
| 3.7.2 same-property NOI growth | missing | missing | missing | missing | `not_disclosed` (MAA, DLR, VICI), 1 value (AVB) | MD&A text (AI), earlier 10-Ks |
| 3.7.3 largest tenant (DLR) | - | missing | - | n/a | `not_disclosed` | 10-K risk factors / properties text |

Result of the first pass (before section 4 below): the four stayed at Graham coverage 55-66%. Section 4 replaces this table's "missing" cells with the classification from the 10-K text itself and the fixes it led to.

## 3. Acceptance run 3 (RF bank, ORI insurer, VTR healthcare REIT, GIS regular, FTNT technology)

Preflight (printed, `scripts/state/acceptance_preflight_3.txt`): none of the five is in test or prod `companies`, in a CSV, in the golden files or in the cache. (KEY, CINF, MTB and HIG were refused by the same check - they are golden.) Log: `scripts/state/acceptance_run_4.log`. The computer stayed awake for the whole run (keep-awake on every `load`); one command per company, one after the other, `--budget 40`.

| Company | Result | Model calls (limit 40) | Time | Buffett / Graham (coverage) | Missing |
|---|---|---|---|---|---|
| RF (bank) | complete | 18 | 8 m 14 s | 87.00 (96%) / 87.40 (94%) | B 3.6.5 + G 3.2.2 LCR: NR in the 10-K and the public sources (D12); B 3.7.3 AI insufficient evidence (rejected); G 3.7.3 RWA not extracted (EF) |
| ORI (insurer) | complete | 17 | 6 m 00 s | 77.38 (88%) / 71.64 (85%) | B 3.6.1 + G 3.2.1: no numeric group capital ratio in the 10-K (NR, same wording as AFG); B 3.1.1 AI insufficient evidence |
| VTR (healthcare REIT) | **failed at first, completed after a fix** | 9 + 16 | 13 m 21 s (+ ~4 m after the fix) | 44.29 (99%) / 41.71 (81%) | B 3.6.3, G 3.2.1-3.2.3, G 3.3.2: current assets / liabilities not reported (unclassified balance sheet) - NR |
| GIS (regular) | complete | 16 | 4 m 22 s | 56.15 (100%) / 38.89 (100%) | nothing |
| FTNT (technology) | complete | 14 | 3 m 28 s | 96.76 (100%) / 78.79 (100%) | nothing |

Network waits: none in the data loads (no `RETRY` line). The 592 s "waited for network retries" of VTR was not a network wait (stall 2).

Stalls (every place the run stopped or needed contact):
1. **VTR, `ai_assess`: `KeyError: 'inputs'` (twice) - a bug.** The router's extraction pass of the same process had set `K5.ENGINE_OF['VTR'] = realestate`; the router then decided STANDARD (RE10/RE11: investment property 87% passes, rental revenue only 26% < 50% fails - a senior-housing operator; a decision by the rulebook, not a bug), but the helper kept the engine of the first pass and read the real-estate shape from a general result. Fix: the engine is assigned, not set once (`_meta_context`, `exec_extract`); `load_result` prefers the engine of the company's profile. VTR then finished with no manual step (`ai-queue --tickers VTR`): `ai_assess`, final score, D2, background.
2. **Wait logic, a bug of my queue change:** the run waited 592 s for the retry of a task that had failed for a permanent reason (KeyError), as if it were a network error. Fix: only a task marked `[network]` is waited for; a permanent failure is retried by a later run.
3. No other stall. No manual contact in RF, ORI, GIS, FTNT. In VTR the only action after the failure was a code fix and the ordinary `ai-queue` command.

**Gate (two consecutive batches of 5 new companies, all final, no contact): not passed in this batch - 4 of 5.** VTR needed a code fix. A second batch of new companies on the fixed code is still needed, and since this batch was not clean the pair starts again.

## 4. MAA, DLR, VICI: Graham data against the text of the 10-K (keyword search, no model)

Method: the cached 10-K of FY2025 and the cached or downloaded earlier 10-Ks; patterns searched in the text; classification: (A) in the last report and not extracted / rejected, (B) only in earlier reports, (C) not in the 10-K at all (supplemental package only). Tool for the occupancy completion: `scripts/keyword_backfill.py`.

| Item | Company | Class | What is written, where | Why it was not taken | What was fixed |
|---|---|---|---|---|---|
| Debt maturities (principal, years 1-2) | MAA | A | debt note: "Maturities 2026 $976,000, 2027 600,000 ..." (net of costs 975,516 / 598,907) | the model gave the period as the maturity year (2026, 2027); the check allowed only the report year and the two before it: `period_mismatch` | rule: year 1 and 2 maturities are valid for fy+1 / fy+2 and stored for the report year (`FORWARD_PERIOD`). Re-judged from the stored answers (no new call): rows for FY2025, `pending` - the block control (coverage band) is `na` because the committed undrawn facility is missing (below) |
| same | DLR | A | debt note table: "Total Debt 2026 $904,683 / 2027 1,441,254" | same period rule **and** `quote_not_found`: the page text has zero-width spaces between the cells | both fixed (`normalize` drops zero-width characters; forward period); Graham 3.2.2 is now computed |
| same | VICI | A | contractual obligations table: senior notes 2026 $1,750,000, 2027 1,500,000 (+ revolver) | period rule | fixed, rows `approved` |
| Committed undrawn facility | DLR | A | "At December 31, 2025, approximately $3.3 billion was available under this facility" | the year was changed to FY2023 by the "newest column first" rule, which treated the sentence as a table row | rule: a sentence (10 or more words) is not a table row, the model's year stays |
| same | MAA | A (derived) | revolver "$1.5 billion" capacity and "$5.0 million used for letters of credit" (two figures) | the model gave 1,495 (= 1,500 - 5): not in the quote, `number_not_in_quote` | **not changed** (a derived number the rule rejects; your decision) |
| Recurring capital expenditures | DLR | A | MD&A table: "Recurring capital expenditures 343,925 / 305,712" | `quote_not_found` (zero-width spaces) | fixed; rows FY2025/FY2024 stored, `pending` (block control Q6 `na`: needs reported AFFO and OE) |
| same | MAA | C | only a description of what recurring capital replacements are; no amount | not a figure in the 10-K (the supplemental has it) | true gap; the rulebook rule "OE proxy -> level item missing" applies |
| same | VICI | C | only the cash-flow line "Capital expenditures (1,238)", total capex of a net lessor; no recurring / maintenance concept | not a maintenance figure | rows stay `pending`; true gap for this item |
| Unencumbered NOI | all three | C | only covenants ("maintain total unencumbered assets of not less than 150%..."); no NOI, no share | not in the 10-K | **the backup exists in the engine** (`unencumbered_assets_share`, flagged) but its input is not in the 10-K either, so it is not triggered; a proxy from the Schedule III "encumbrances" column would be new, not in the rulebook |
| Stabilized / same-property NOI | MAA | A | segment table: "Same Store NOI $1,304,264 / 1,322,186 / 1,339,810" (three years) | the model answered `not_disclosed`; the item asks for a growth percentage, the report shows levels | **not fixed**: growth is derivable by code (-1.4% in 2025); needs a derivation rule |
| same | DLR | A | MD&A: "Stabilized" revenue 4,272,850 vs 4,028,165 and stabilized expense lines; no NOI line | same | not fixed: derivable (revenue - expenses of the stabilized portfolio); needs a rule |
| same | VICI | C | "same-store" appears only for the Partner Property Growth Fund capital-improvement programme | no like-for-like NOI | true gap |
| Occupancy, 3 years | DLR | A + B | "approximately 84.7% leased" (FY2025); 84.1, 81.7, 84.7, 83.6 in the earlier 10-Ks | model: `not_disclosed`; the criterion needs 3 years | completed by keyword search from five reports; rows `approved` by the block rule (bounds 0-100) |
| same | MAA | B | "Same Store 278 communities 96,568 units 95.6%" (average physical occupancy) in each report | the model had only the last two years | completed from five reports |
| same | VICI | B | "our properties are 100% leased" | only the last year | completed from three reports (FY2022 and FY2021 use other wording: no match, not forced) |

Graham coverage before -> after (this section):

| | before section 4 | after |
|---|---|---|
| DLR | 55% (no score) | 70% - **85.75** (Buffett 89.50, 83%) |
| VICI | 55% (no score) | 70% - **79.17** (Buffett 86.70, 81%) |
| MAA | 55% (no score) | 55% (no score; Buffett 73.22, 83%): still missing maturities (rows `pending`), unencumbered, stabilized NOI, recurring capex, same-store growth |

The approval rules (nothing was changed): the maturity and capex rows of MAA and DLR are `pending` because the block control is `na` - it needs the undrawn facility (MAA: rejected, number not in the quote) and reported AFFO. A chain of controls, not a rule that rejects a correct figure.

## 5. Open items

1. A second clean pair of batches of 5 for the gate.
2. Your approval of the narrowed rule on gains on sale (2.3).
3. Derivation rules for same-store NOI growth from the stated levels (MAA) and from the stabilized portfolio (DLR).
4. MAA committed undrawn facility (a derived figure the rule rejects).
5. AFG: a duplicate mortgage-loan row blocks the investments block (2.5).
6. Security stage (as agreed): `CIK_OVERRIDE` into a table `ticker_overrides`, an administrator ticket for an unknown ticker; `support_tickets` then replaces the `admin_alert` log.
7. EQR / VMRK: the ticker EQR is stale (merger); the company must be loaded as VMRK once a successor annual report exists.

## 6. Decision of 2026-10-31: SIC 6798 that is not a mortgage REIT is always INCOME_REAL_ESTATE

**Code**
- `router.evaluate_year`: in row 3, a failing property test for SIC 6798 no longer gives STANDARD. The profile is INCOME_REAL_ESTATE; RE10/RE11 only set the NOI method: rental revenue below 50% of revenue -> `operating_reit` (field `operating_reit` on `YearResult` and `RouterResult`, a note in the reasons). Other property SICs (65xx) keep the old row 3.
- NOI method (`auto_config.is_operating_reit`, `reit_noi_method(..., operating)`; engine `derive_re`): the engine did not support an operating NOI, so it was added. Operating NOI = **total revenue (all operating revenue: resident fees, operating revenue) - property operating expenses** (the property-level expense line, else cost of revenue, flagged); `noi_basis` says "operating NOI ... (operating_reit)", the result flags carry `operating_reit`. Decided from the latest year's rental share in the facts; REITs with hand-made entries (the golden set) are never switched.
- Tests (8 new): router (operating / mostly rent / property below half but not a mortgage REIT / another SIC unchanged), operating NOI and its fallback, detection from the latest year only, the result flag.

**Golden:** not changed and not affected: all ten golden REITs (AMT, ARE, BXP, EQIX, EQR, FRT, O, PLD, PSA, SPG) were already INCOME_REAL_ESTATE and are in the hand-made set; no golden company was STANDARD by RE10/RE11 (0 companies, 0 points).

**REITs in test classified STANDARD by RE10/RE11:** only **VTR** (SIC 6798). VICI and DLR were already INCOME_REAL_ESTATE but through the SIC fallback; they were re-routed (reason now "row 3 -> INCOME_REAL_ESTATE" for VICI) and their scores did not change.

**VTR before -> after** (healthcare REIT, rental income 26% of revenue, resident fees and services the rest)

| | before (STANDARD) | after (INCOME_REAL_ESTATE, operating NOI) |
|---|---|---|
| Buffett | 44.29 (coverage 99%) | **90.90** (83%) |
| Graham | 41.71 (81%) | no score (55%, below the 60% needed) |

To get there one more gap had to be closed: from FY2022 Ventas tags the gain on real estate dispositions with its own element (`vtr:GainLossOnDispositionOfRealEstate`), so FFO was empty for 2022-2025 and the REIT profile first came out with no score at all (coverage 10%). A generic search of the company's own elements in the inline XBRL now finds it (`discover_extension_elements`; used for four years of VTR).

What changed, criterion by criterion (full list: `python scripts/score_snapshot.py --diff scripts/state/snap_before_6798.json scripts/state/snap_after_6798.json`):
- **Depreciation against FFO (the earnings base).** In STANDARD, depreciation of 1.1 bn (2025) against a net income of 0.25 bn hits every earnings criterion; as a REIT the base is normalized FFO (net income + real-estate depreciation - gains). Buffett 3.3.1 profitable years 2.0 -> 6.0 of 6, 3.3.2 EPS falls 3.0 -> 4.0 of 4, 3.3.4 weakest year 0.0 -> 2.0 of 2; Graham 3.4.1 profitable years 5.0 -> 9.0 of 9, 3.4.2 EPS falls 0.0 -> 1.5, 3.5.3 dividends / earnings 0.0 -> 1.32, 3.6.2 EPS rises 1.17 -> 0.33 (worse).
- **Cash flow replaced by owner earnings (FFO less maintenance capital).** Buffett 3.5.1 years with positive FCF 0.0 of 5 -> CAGR of OE per share 8.0 of 8, 3.5.2 5.25 of 7, 3.7.4 payout 0.0 -> 2.0 (dividends / OE), 3.8.3 FCF growth 0.0 -> 3.0; Graham 3.8.1 0.0 -> 3.75 of 5, 3.8.3 0.0 -> 2.0.
- **Leverage on EBITDAre instead of EBITDA / EBIT.** Buffett 3.6.1 net debt / EBITDAre 3.4 of 4 (before 0.0 of 3, ND/EBITDA 5.6x), 3.6.2 3.01 of 4 (before 0.0); Graham 3.2.1 (new) 5.48 of 7, 3.3.1 net debt / EBITDAre 5.18 of 7 (before debt / equity 1.92 of 5).
- **NOI (operating).** Buffett 3.4.3 NOI margin range 4.24 of 5 (new).
- **Operating margin -> FFO margin:** 3.2.2a 0.99 -> 0.68 of 1.5.
- **No longer applicable:** 3.2.3 ROIC (not applicable to a REIT).
- **Missing as a REIT (extraction / approval):** Buffett 3.4.1, 3.4.2 (NOI yield and same-property growth); Graham 3.3.3, 3.5.4 and the balance-sheet items 3.7.1-3.7.3, 3.8.2 (tangible equity and share-count items are not defined for the REIT model).

The other REITs in test (MAA, DLR, VICI, AMT, O): unchanged scores. A note for decision: for VICI the rental share by the tags is below 50% only if its lease income counts as "rent" (it reports most income as sales-type and financing leases); VICI stays on the rent-based NOI because the facts the test reads were not below 50% in its latest year.

Also fixed on the way: stray control characters (backspace) in a regex I had written, which silently made the extension search return nothing; the files were checked (`grep` for \x08 in `src` and `tests`: none left; two older scripts, `build_bank_regulatory.py` and `insurance_extraction_spec.py`, were not touched by this stage).

## 7. Review of the VTR score (Buffett 90.90), the rent definition, network retry in `load` (2026-11-01)

### 7.1 Owner earnings (OE) of VTR, MAA, DLR
How OE is built for a REIT: `OE = normalized FFO - straight-line rent adjustment - maintenance capex - income-preserving TI/LC` (rulebook C.B3.5-RE). When any of the three deductions is missing, the engine does **not** compute OE: it uses normalized FFO per share, `metric_basis = FFO_PROXY` (flagged), and the rulebook allows that **only for growth and stability sub-items; level-based sub-items (dividend coverage) are Missing** (FFO proxy rule; Graham 3.5 card: "Missing when OE is a proxy").

All three are on the proxy, for all 5 years: straight-line rent (not tagged, `not_disclosed` by the AI), maintenance capex (MAA, VTR `not_disclosed`; DLR: the 2025/2024 figures 343.9 / 305.7 m exist but are `pending` and two years are not the five that OE needs) and TI/LC (VTR `not_disclosed`; MAA and DLR `NA` by the asset type). So in the three of them "OE" = normalized FFO, without any maintenance deduction.

Item by item (the proxy rule against the code):

| Item | Kind | Rule | Code before | Now |
|---|---|---|---|---|
| Buffett 3.5.1 OE per share growth | growth | allowed with flag | scored, `FFO_PROXY` | same |
| Buffett 3.5.2 OE per share stability | stability | allowed with flag | scored, `FFO_PROXY` | same |
| Buffett 3.8.3 smoothed OE growth | growth | allowed with flag | scored, `FFO_PROXY` | same |
| Graham 3.8.1 OE stability | stability | allowed with flag | scored, `FFO_PROXY` | same |
| Graham 3.8.3 per-share discipline | share CAGR, else OE per share growth | growth: allowed with flag | scored, `FFO_PROXY` | same |
| Graham 3.5.4 dividends / OE | level | Missing | Missing | same |
| Graham 3.8.2 reported vs economic | level (gap) | Missing | Missing | same |
| **Buffett 3.7.4 dividends / OE** | **level** | **Missing** (general proxy rule; the Buffett card line says "(FFO proxy flag)", which contradicts the proxy rule and Graham 3.5.4 - I applied the proxy rule) | **scored on FFO** (VTR, MAA, DLR, VICI: 2.0 of 2) | **Missing** |

So one item did not match: Buffett 3.7.4 was scored on FFO. Fixed (`b37`). Effect: VTR 90.90 -> **89.92**, MAA 73.22 -> 72.99, DLR 89.50 -> 88.52, VICI 86.70 -> 89.37 (its coverage fell 81% -> 73%, the other items moved because the score is the points over the covered weight). AMT and O have a full OE and did not change. Golden: the ten golden REITs all have a full OE (`metric_basis OE`), so none changes.

The remaining VTR numbers on the proxy: 3.5.1 = 8.0 of 8 comes from a normalized-FFO-per-share CAGR of 12.5% (from the FY2021 base, depressed by the pandemic, to FY2025); 3.5.2 5.25 of 7 (one decline of more than 5%); 3.8.3 3.0 of 3 (smoothed growth 10.8%); Graham 3.8.1 3.75 of 5; 3.8.3 2.0 of 2. MAA: 3.5.1 1.49 (CAGR 1.5%), 3.5.2 3.5, 3.8.3 0.37. DLR: 3.5.1 6.29 (CAGR 6.3%), 3.5.2 5.25, 3.8.3 2.53. VTR's high growth score is therefore a FFO recovery effect, flagged `FFO_PROXY`, not a verified owner-earnings growth.

### 7.2 Rent includes financing and sales-type leases
Decision: lease income of any kind (operating, direct financing, sales-type) is rent; only revenue from the company's own operations (resident fees, hotel revenue) is not. The provider now adds `SalesTypeAndDirectFinancingLeasesRevenue`, `SalesTypeLeaseRevenue`, `SalesTypeLeaseInterestIncome`, `DirectFinancingLeaseRevenue` and `DirectFinancingLeaseInterestIncome` to `rental_revenue` (tag log `SUM: ... (lease income of any kind is rent)`), for tickers outside the hand-made set. VICI: rent 2,125 of 4,006 m = 53% in FY2025 (before: 5 years of a small operating-lease line), so it is **not** an operating REIT and keeps the rent-based NOI; the earlier note in section 6 is settled. Its router reason is now "row 3 -> INCOME_REAL_ESTATE". Test: `test_financing_and_sales_type_lease_income_is_rent...` (the 50% test on 2,125/4,006 against VTR's 1,497/5,834).

### 7.3 Network retry in `load` / `--job repair`
`src/pipeline/net_retry.py`: a temporary network error (also wrapped) waits 60, 120, 240, 480 s and tries again, 5 attempts, other errors at once; the waited time is printed ("waited for network retries"). Used by `vc.py load` for every job. Tests: success after two failures (waits 60 + 120), a bug is not retried, five attempts then the error.

## 8. Acceptance run 4 (ZION bank, THG insurer, HST hotel REIT, HRL regular, ANET technology) - 2026-10-31/11-01

Preflight (`scripts/state/acceptance_preflight_4.txt`): all five new (test, prod, CSV, golden, cache). Log: `scripts/state/acceptance_run_5.log`. Computer awake, one `load` per company, `--budget 40`, company after company.

| Company | Result | Calls (limit 40) | Time | Buffett / Graham at the end of the run |
|---|---|---|---|---|
| ZION | complete, no failed task | 19 | 7:06 | 82.72 (71%) / 80.87 (93%) |
| THG | complete | 16 | 5:13 | 79.86 (90%) / 87.03 (75%) |
| HST | complete | 21 | 6:03 | no score (39%) / no score (33%) |
| HRL | complete | 16 | 4:44 | 69.11 (98%) / 70.21 (100%) |
| ANET | complete | 16 | 3:36 | 95.71 (98%) / 86.07 (96%) |

**Stalls: none.** No failed or retried task, no network wait, no manual contact, no code change in the middle; every company reached `complete` by itself. By the gate's definition this batch is clean: **5 of 5**. The gate asks for two such batches in a row; run 3 was not clean (VTR), so this is **the first of the pair**. The code changed after the run (below), so the second batch has to run on the new code.

What the missing data showed afterwards (bugs in the data layer, not stalls), all fixed and checked on test:
1. **HST - no score (coverage 39%).** (a) The total debt: the chain took `LongTermDebt` (1.3 bn), the plausibility check dropped it, nothing replaced it, so net debt and EBITDAre were empty; the generic fallback now also tries `DebtAndCapitalLeaseObligations` and `DebtInstrumentCarryingAmount` after the check. (b) Share counts reported in millions (739.1 in FY2017-2020) were dropped by the scale guard, which knew only x1000; it now also rescales x1e6. (c) The gain on disposals in FY2019 sits in `DisposalGroupNotDiscontinuedOperationGainLossOnDisposal`: added to the chain. (d) FY2024 has no gain line (no sale; the line is blank in that year's 10-K and the next one): a year between reported years is zero, flagged `assumed_zero` (new, narrow - **needs your approval like the gains rule of 2.3**). (e) A hotel REIT has no lease income at all: `is_operating_reit` is true when no lease income exists in any year, so the operating NOI method is used. After the fixes: HST Buffett **91.15** (81%), Graham no score (55%, the same extraction gaps as the other REITs).
2. **ZION - Buffett coverage 71%.** No pretax-income tag: PPNR-based items and Graham 3.8.2 were missing; pretax is now derived as net income + income tax expense (`DERIVED`, stored as derived). After: Buffett 79.68 (96%), Graham 79.51 (96%). Left: B 3.1.5 (AI insufficient evidence), LCR (B 3.6.5, G 3.2.2) not reported numerically - real gaps.
3. THG: B 3.6.1 and G 3.2.1 (no numeric group capital ratio in the 10-K, real); G 3.2.2 and G 3.7.3 (balance-sheet categories: the block control `inv_sum` of the earlier AFG finding; the skill now also reads the balance sheet from this version on, THG was extracted before it); G 3.7.2 (credit-quality share not extracted).
4. HRL: B 3.7.3 (AI insufficient evidence). ANET: B 3.1.3, G 3.1.3, G 3.8.3 (AI insufficient evidence). Real AI answers, counted as missing by rule R16.

Calls this stage: the shared daily counter stood at 92 before this run and 180 after it (limit 450).

## 9. Approvals, rulebook note, REIT sanity check (2026-11-01)

**Approved by you and recorded:** (a) gain on sale = 0 when the company's XBRL has no gain / loss on sale or disposal element at all (VICI); (b) a year without a gain value between years that have one = 0 (HST FY2024). Both are stored as `status = assumed_zero`, `source_kind = derived` in `financial_facts` (checked: HST 2024, VICI 2024-2025) and listed in the load output as `gains_sale: ... assumed_zero in ...` (`data_problems` of the result).

**Rulebook correction to make (Buffett 3.7.4, INCOME_REAL_ESTATE):** EN line 638 now reads `Σ dividends / Σ OE: ≤100% = 2, ≥150% = 0 (FFO proxy **flag**)`; HE line 637 `... (**סימון** כשחלופת FFO)`. Per the FFO proxy rule (EN lines 499 and 1342, HE 498 and 1336) and the Graham 3.5 card (EN 939) it should read: `... **Missing** when OE is a proxy (FFO_PROXY: the proxy is allowed only for growth and stability sub-items)`. The code already does this (`b37`). I did not edit the rulebook files.

### REIT sanity check (report only, no rule changed)
Tables: `scripts/state/reit_sanity.md`, `reit_sanity_criteria.txt`, `reit_sanity_exai.md` (scripts `reit_sanity.py`, `reit_sanity_criteria.py`, `reit_sanity_exai.py`). Format: score / coverage / points earned on `FFO_PROXY` items.

| source | company | Buffett | Graham |
|---|---|---|---|
| golden | AMT | 78.3 / 83% / 0 | 92.1 / 75% / 0 |
| golden | ARE | 77.7 / 98% / 0 | 82.7 / 86% / 0 |
| golden | BXP | 56.0 / 83% / 0 | 55.4 / 75% / 0 |
| golden | EQIX | 93.9 / 83% / 0 | 98.6 / 75% / 0 |
| golden | EQR | 85.6 / 92% / 0 | 86.8 / 86% / 0 |
| golden | FRT | 78.7 / 98% / 0 | 78.5 / 85% / 0 |
| golden | O | 79.4 / 83% / 0 | 84.8 / 86% / 0 |
| golden | PLD | 77.9 / 98% / 0 | 94.7 / 75% / 0 |
| golden | PSA | 76.7 / 98% / 0 | 85.8 / 85% / 0 |
| golden | SPG | 70.6 / 94% / 0 | 79.0 / 81% / 0 |
| test | VTR | 89.9 / 81% / 16.2 of 72.6 (22%, 3 items) | none / 55% / 5.8 of 44.6 (13%) |
| test | VICI | 89.4 / 73% / 16.2 of 63.9 (25%) | 79.2 / 70% / 5.8 of 65.3 (9%) |
| test | HST | 91.2 / 81% / 16.2 of 74.9 (22%) | none / 55% / 3.8 of 52.1 (7%) |
| test | DLR | 88.5 / 81% / 14.1 of 66.8 (21%) | 85.8 / 70% / 5.8 of 66.3 (9%) |
| test | MAA | 73.0 / 81% / 5.4 of 55.6 (10%) | none / 55% / 2.5 of 61.8 (4%) |
| test | AMT | 76.2 / 83% / 0 | 85.9 / 75% / 0 |
| test | O | 88.6 / 83% / 0 | 84.8 / 86% / 0 |

**Are the new ones consistently high?** Buffett: yes for four of five. VTR, VICI, HST and DLR are 88.5-91.2 (mean 89.8) against a golden mean of 77.5 (range 56.0-93.9); MAA (73.0) is not. Graham: no. VICI 79.2 and DLR 85.8 are inside the golden range (55.4-98.6, mean 83.8); the other three have no Graham score.

**Where it comes from** (measured, nothing changed):
1. **AI answers.** The golden results still had the AI questions pending; the database results have them, and all seven REITs earned 17 of 17 AI points. On the golden basis (without the AI items) the Buffett scores fall: VTR 89.9 -> 87.2, VICI 86.1, HST 88.8, DLR 85.2, MAA 65.2, AMT 70.2, O 85.7 (a drop of 2.4 to 7.8 points). The same effect lifts the re-scored AMT and O, which are not new companies.
2. **Method and data drift since the golden run:** O is 79.4 in the golden file and 85.7 on the same basis in the database (+6). So of the 12 points between the new four and the golden mean, about 6-8 are not specific to the new companies.
3. **The growth criterion (3.8).** New REITs 82-100% of the available points (VTR 100%, HST 100%, DLR 94%, VICI 90%) against a golden mean of 53% (33-87%). The five-year window is FY2021-2025; for VTR, HST, DLR and VICI the start is the pandemic and acquisition years, so revenue and FFO per share grow strongly from a low base (VTR normalized FFO per share CAGR 12.5%). The largest genuine difference, and a base effect, not a data error.
4. **Margin criterion (3.2):** 33-48% against 16%; 3 of its points are AI items.
5. **Coverage is lower, 73-81% against 83-98%:** Buffett 3.4 (return on capital: NOI yield, same-property growth) is missing for all of them, as are 3.6.3 and 3.7.4. The score is a share of the covered points; the missing criterion is around 76% for golden REITs, so it moves the scores little.
6. **FFO_PROXY is not the cause.** 21-25% of the earned Buffett points of VTR, VICI, HST and DLR come from proxy items (growth and stability), but taking them out leaves the scores about where they are (VTR 89.9 -> 89.8, VICI 89.4 -> 89.1, HST 91.2 -> 91.4); for MAA the proxy items pull the score down (73.0 against 80.7 without them).

## 10. Acceptance run, batch 5 (FHN bank, SIGI insurer, EXR storage REIT, SJM regular, NTAP technology) - 2026-11-01

Preflight: `scripts/state/acceptance_preflight_5.txt` (all new; WRB was refused: golden). Log: `scripts/state/acceptance_run_6.log`.

| Company | Result | Calls (limit 40) | Time | Buffett / Graham (coverage) |
|---|---|---|---|---|
| FHN | complete | 17 | 6:06 | 76.08 (98%) / 77.54 (96%) |
| SIGI | complete | 17 | tasks done in 7 min; the process ended 2 h 35 min later (below) | 82.27 (90%) / 85.46 (60%) |
| EXR | complete | 23 | 4:57 | 69.10 (81%) / 76.72 (70%) |
| SJM | complete | 18 | 3:52 | 41.08 (98%) / 31.90 (97%) |
| NTAP | complete | 16 | 4:01 | 90.82 (100%) / 75.90 (100%) |

**(a) Without contact: 5 of 5.** No failed or retried task, no network wait, no manual action.
Unexplained time in SIGI: its last task was written at 23:11 UTC (01:11 Israel), seven minutes after the start; the process printed its report at 03:46. No task was waiting and there is no `RETRY` line. The most likely cause is the computer going to sleep despite the keep-awake request (the clock jumped with no activity); I could not confirm it.

**(b) Every missing item classified. Result: not clean - two companies have items that are bugs.**

| Company | Item | Class | Evidence |
|---|---|---|---|
| FHN | B 3.6.5, G 3.2.2 LCR | real - not reported | no numeric LCR in the 10-K (D12) |
| NTAP | none | - | 100% / 100% |
| SJM | B 3.7.1 P/E, 5 years | real - not relevant | diluted EPS is negative in FY2023, FY2025 and FY2026 (-0.86, -11.57, -1.30): fewer than 3 valid P/E years |
| SJM | G 3.7.3 tangible BVPS | real - not relevant | goodwill and intangibles exceed equity: negative tangible equity |
| SIGI | B 3.6.1, G 3.2.1 capital ratio | real - not reported | the 10-K mentions RBC only in general terms, no numeric ratio |
| SIGI | **B 3.6.3, G 3.3.2 financial debt** | **BUG - in XBRL, not pulled** | `LongTermDebt` is tagged 2019-2024 (about 0.5 bn) but only FY2024 reached the facts (`financial_debt`: 1 of 10 years); FY2025 is tagged by instrument (notes by member), no total |
| SIGI | **G 3.2.2, G 3.7.3 balance-sheet categories** | **BUG - in the report, not extracted / blocked** | the 10-K states "Total investments and cash"; the investments block (the AFG finding of 2.5: duplicate rows and the `inv_sum` control) leaves the rows pending |
| SIGI | **G 3.7.2 investment-grade share** | **BUG - in the report, not extracted** | the credit-quality passages are in the 10-K (21 "investment grade / NAIC" passages) |
| EXR | B 3.6.3 economic LTV | real - not reported | no fair value of real estate in the 10-K |
| EXR | B 3.7.4, G 3.5.4, G 3.8.2 | real by rule | OE is the FFO proxy: no recurring capex amount in the 10-K (only the words), so level items are Missing by the rulebook |
| EXR | G 3.7.3 largest tenant | real - not relevant | self-storage: individual customers, no tenant disclosure |
| EXR | **B 3.4.2, G 3.7.2 same-property NOI growth** | **BUG - in the report, not extracted** | "Total same-store net operating income $1,884,797 / $1,917,206" (2025 / 2024): -1.7% |
| EXR | **G 3.3.2 unencumbered** | **BUG - in the report, not extracted; the rulebook backup is not triggered** | "unencumbered asset value $30,247,545 and total asset value $35,894,312" (84%); the backup (unencumbered assets share) exists in the engine, but the AI returned `not_disclosed` |
| EXR | **G 3.7.1 occupancy (3 years)** | **BUG - in the report and in earlier reports, not extracted** | "average occupancy for our same-store pool for 2025 was 93.7%"; the earlier 10-Ks are in the cache |
| EXR | B 3.4.1 NOI yield / proxy | short history, partly a consequence of the above | the property operating expense is tagged only for FY2023-2025, the NOI proxy needs a longer series |
| EXR | G 3.3.3 | real by rule | needs a stabilized portfolio with economic value |

**Gate: not passed.** (a) holds, (b) does not: six items (SIGI financial debt, investment categories, credit-quality share; EXR same-store NOI, unencumbered share, occupancy history) exist in XBRL or in the report and were not taken. They are the same two families as before: REIT depth items (same-property NOI, unencumbered assets share, occupancy history - done by hand for MAA, DLR, VICI with `scripts/keyword_backfill.py`, not part of the pipeline) and the insurer investments block. A batch can be called clean only after these are in the pipeline, not patched by hand per company.

## 11. Pipeline steps for the two families, and acceptance batch 6 (2026-11-01)

**Rulebook:** version 2026-11-01_07-00 (CL19-CL24) added to git; 2026-10-21_19-26 (4 files) removed; `tests/test_ai.py` now reads the new file. The task "bank / entity and CET1 order" (CL23), "gains assumed_zero" (CL21), "same-property NOI growth derived" (CL22) are what the code does.

### 11.1 What was put into the pipeline (no per-company hand step)
1. **REIT depth** (`src/ai/keyword_depth.py`, called from the extraction task of every INCOME_REAL_ESTATE company, no model call): occupancy of the last 5 annual reports (one wording for all years: the first of five patterns that matches the latest report), same-property NOI growth = current / prior - 1 from the two stated levels (CL22, flagged derived, both numbers in the quote), unencumbered assets share from "unencumbered asset value $A ... total asset value $B" when the model returned `not_disclosed` for both unencumbered items. Earlier reports are downloaded through the rate-limited SEC client. A model value is never replaced.
2. **Insurer investments block:** (a) `inv_sum` control: a total that includes cash ("Total cash and investments") is compared with the categories with cash, otherwise without; when the model gave two values for one category and year (AFG mortgage loans 947 and 791) the combination that adds up is used and the other row is rejected as a duplicate; (b) the skill reads the balance sheet and "other invested assets" now says what belongs there (version 3, 4; a changed skill version is asked again); (c) financial debt reported only per instrument (SIGI FY2025: `LongTermDebt` once per note) is added up from the inline XBRL (`instrument_sum_series`, flagged `SUM`); (d) the investment-grade share from the sentence or table line of the report (SIGI "non-investment grade ... 3%" -> 97, THG 95, AFG 96) when the model returned none.
3. Tests: 15 new (keyword depth, inv_sum, instrument sum, share-scale and the others of this section); 941 pass.

### 11.2 Check without the manual backfill
The manual rows (`model = keyword-search`, `kw1`) of MAA, DLR and VICI were deleted and the extraction task was run through the queue (cached model answers, no call):
- **EXR:** same-property NOI growth (4 years), unencumbered assets share (5 years, rulebook backup `fallback`), occupancy history now exist. Buffett 69.10 -> 72.59; Graham 3.4.2 6/6, G 3.3.2 4/4, G 3.7.1 2.4/4, G 3.7.2 4/4, G 3.7.3 not applicable.
- **MAA:** same-property NOI growth (5 years: +6.2%, +17.1%, +6.0%, -1.4%, -1.4%) -> B 3.4.2 6/6, G 3.7.2 4/4; occupancy as before. **DLR and VICI: the scores are the same as with the manual rows** (85.75, 79.17), i.e. the pipeline reproduces them.
- **SIGI:** B 3.6.3 1.98/2, G 3.2.2 5/5, G 3.3.2 5.97/6, G 3.7.2 3/3, G 3.7.3 2.31/3; Graham coverage 60% -> 85%. **THG:** G 3.7.2 3/3 (IG share 95%). **AFG, THG:** the balance-sheet categories still do not add up to the total (AFG 7.2%: equity-method investments of 2.4 bn are not among the categories; THG 2.4%, above the 2% of the control) - rows stay pending; a real extraction-quality limit, the control was not loosened.

### 11.3 Batch 6 (WAL bank, ERIE insurance agent, KIM retail REIT, CAG regular, PANW technology)
Preflight `scripts/state/acceptance_preflight_6.txt` (all new). Log `scripts/state/acceptance_run_7.log`.

| Company | Result | Calls | Time | Buffett / Graham (coverage) |
|---|---|---|---|---|
| WAL | complete | 18 | 7:46 | 79.70 (90%) / 84.80 (83%) |
| ERIE | complete, **profile INSURANCE by the router fallback** | 16 | 4:32 | none (33%) / none (15%) |
| KIM | complete | 25 | 9:27 | 66.25 (81%) / 62.98 (65%) |
| CAG | complete | 17 | 5:09 | 46.52 (100%) / 37.04 (100%) |
| PANW | complete | 14 | tasks done in minutes, the process ended at 09:37 (see below) | 85.70 (100%) / 49.14 (100%) |

**(a) Without contact: 5 of 5.** No failed task, no retry, no network wait. PANW: its report was printed about two hours after the start (07:41 -> 09:37) with all tasks done early, the same pattern as SIGI in batch 5: most likely the computer sleeping despite the keep-awake request; not confirmed.

**(b) Missing items classified. Result: not clean - three bugs.**

| Company | Item | Class | Evidence |
|---|---|---|---|
| CAG, PANW | none | - | 100% / 100% |
| WAL | B 3.6.5, G 3.2.2 LCR | real - not reported | no numeric LCR |
| WAL | **B 3.6.1, G 3.2.1 CET1; G 3.7.3 RWA** | **BUG - in the report, extracted, then held back** | "Common equity tier 1 ratio 11.0 %", "Risk-weighted assets $63,408": both were extracted (11.0, 63,408) but the rows are `pending`: the model's CET1 capital is stored under FY2023 / FY2024 instead of FY2024 / FY2025 (a one-year shift of the periods), so the block control `cet1_vs_rwa` fails and everything of the block waits |
| KIM | **G 3.2.2 debt maturities** | **BUG - in the report, rejected** | the table "Principal $881.7 $1,176.5 ..." is in the 10-K; both rows were rejected `quote_not_found` (the quote does not match the text as written) |
| KIM | B 3.6.3 economic LTV; B 3.7.4, G 3.5.4, G 3.8.2 (OE proxy); G 3.3.2 unencumbered; G 3.3.3 | real | no fair value of real estate, no recurring-capex amount, no unencumbered figure in the 10-K |
| KIM | B 3.4.1, B 3.4.3 | short history | the NOI series is shorter than 3 years of property expenses |
| ERIE | **all (33% / 15% coverage)** | **BUG - misrouting** | Erie Indemnity manages the Erie Insurance Exchange for a fee; its balance sheet has no claims liabilities (total liabilities 1.07 bn, no liability for claims). The row 2 test is "undetermined" because the claims component is missing and the fallback of 2026-10-29 sends it to INSURANCE by its SIC (6411); on the insurance engine nearly everything is missing. A fee business is not an insurer; the profile should be STANDARD |

**Gate: not passed** (second batch in a row with bugs, though of different kinds: the REIT and insurer depth items of batch 5 are fixed and did not recur). Nothing of batch 6 was repaired by hand.

### 11.4 Open for the next round
1. WAL: the period assignment of capital tables ("$ 7,003 $ 6,311" under "December 31, 2025 / 2024") - a shift of one year.
2. KIM: why the maturity quotes are not found (the check of the quote against the text).
3. ERIE: row 2 fallback for an issuer with no insurance liabilities at all (a missing component that is zero by the balance sheet), so it ends STANDARD.
4. AFG / THG: the categories of the investments block against the total (equity-method investments).
5. The unexplained idle time at the end of two runs (SIGI, PANW).

## 12. Fixes after batch 6, and acceptance batch 7 (2026-11-01)

### 12.1 The five fixes (all on test, 947 tests pass)
1. **WAL - year shift in capital tables.** The row "Common equity tier 1 | $ | 7,003 | | | $ | 6,311" has a "1" in its label ("tier 1") that the column logic counted as the first cell, so every year moved back one (cet1 capital stored as FY2023 / FY2024). Fix (`ext_norm.data_tokens`): a one- or two-digit number right after a label word such as tier, level, class, series, stage, group is part of the label. Re-judged from the stored answers: WAL B 3.6.1 4/4, G 3.2.1 8/8, G 3.7.3 1.27/2 (Buffett 79.70 -> 80.59, Graham 84.8 -> 86.35).
2. **KIM - debt maturities.** The model quoted only the cell ("$881.7"; the report has "$ 881.7"), shorter than the minimum quote. When such a quote occurs once in the text sent, it is extended to the words before it (the table row), as written in the report (`quote_extended_to_the_row`); an ambiguous cell stays rejected. No hidden characters were involved this time (those were DLR's). KIM G 3.2.2 4.45/8 now scored.
3. **ERIE - SIC fallback.** The fallback to INSURANCE when the row test is undetermined applies only to carriers, SIC 63xx; 64xx (agents, brokers, insurance services) go on as STANDARD (`fallback_by_sic_allowed`). ERIE's stored profile came from the old rule and, by the stability rule, carried over, so its profile was cleared once and the company re-routed (one data step on a company of batch 6): ERIE is now STANDARD, Buffett 97.29 (91%), Graham none (55%).
4. **AFG - equity-method investments** are a category of the investments block (`inv_equity_method`, skill version 5; the `inv_sum` control, the engine and the complex-assets numerator include it; the control was not loosened): 2,421 m added, every row `approved`, G 3.2.2 4.89/5, G 3.7.3 0.57/3 (before: both missing). New: rows of an older skill version are rejected as `superseded` when the current version has the period (AFG's two stale mortgage-loan rows).
5. **Heartbeat.** `keep_awake` now also writes `[heartbeat] HH:MM:SS +N s` every 5 minutes (and at start and end); a gap well over the interval is printed as `GAP ... the computer was probably asleep`. `vc.py load` covers the whole command, not only the queue part. 14 heartbeat lines in batch 7, no GAP.

### 12.2 Batch 7 (BOKF bank, RLI insurer, REXR industrial REIT, TSN regular, CDNS technology)
Preflight `scripts/state/acceptance_preflight_7.txt` (all new). Log `scripts/state/acceptance_run_8.log`.

| Company | Result | Calls | Time | Buffett / Graham (coverage) |
|---|---|---|---|---|
| BOKF | complete | 16 | 6:45 | 81.77 (98%) / 90.46 (94%) |
| RLI | complete | 16 | 6:41 | 87.59 (90%) / 77.97 (75%) |
| REXR | complete | 23 | 6:34 | 87.95 (81%) / 92.06 (70%) |
| TSN | complete | 14 | 5:16 | 49.86 (100%) / 55.43 (98%) |
| CDNS | complete | 16 | 4:13 | 97.36 (100%) / 84.96 (100%) |

**(a) Without contact: 5 of 5.** No failed task, retry or network wait; heartbeat every 5 minutes, no gap (the computer did not sleep).

**(b) Missing items classified. Result: not clean - three companies with bugs.**

| Company | Item | Class | Evidence |
|---|---|---|---|
| CDNS | none | - | 100% / 100% |
| BOKF | B 3.6.5, G 3.2.2 LCR | real - not reported | no numeric LCR |
| BOKF | G 3.7.3 RWA | real - not in the report text | "risk-weighted assets" appears only in prose, no figure |
| RLI | B 3.6.1, G 3.2.1 capital ratio | real - not reported | "RBC amount in excess of the authorized control level", no number |
| RLI | **G 3.7.2 investment-grade share; G 3.7.3 (needs the below-IG part)** | **BUG - in the report as dollar amounts, not as a share** | "Non-investment grade bonds totaled $148 million while non-rated Regulation D securities totaled $90 million": the share is derivable from these and the fixed-maturity total; the sentence/table forms of the keyword step (a stated percentage) do not cover it |
| REXR | **B 3.4.2, G 3.7.2 same-property NOI growth** | **BUG - derivable from the report** | the same-property table gives revenues 759,209 / 745,932 and property expenses 170,034 / 163,053: NOI +1.1%; the NOI rows of the keyword step need an "NOI" line, this table has revenues and expenses |
| REXR | **G 3.7.3 largest tenant** | **BUG - in the report, not extracted** | "no single tenant accounting for more than 2.4% of our total annualized in-place base rent"; the 10 largest tenants 13.9% (table) |
| REXR | G 3.3.2 unencumbered | real | covenants only, no NOI or asset figures |
| REXR | B 3.6.3, B 3.7.4, G 3.5.4, G 3.8.2, G 3.3.3, B 3.4.1 | real by rule / no value basis / short NOI history | as for the other REITs |
| TSN | **G 3.5.2 DPS cuts ("dividend per share missing for most years")** | **BUG - in the report; XBRL by class** | the 10-K states Class A dividends of $2.00 / $1.96 / $1.92 per share; the XBRL per-share dividend is reported per share class (members), no undimensioned total |

**Gate: not passed** (third batch in a row). Nothing of batch 7 was repaired by hand. Each batch removed the families found in the one before and showed new ones (this time: dollar-amount credit quality, same-property tables without an NOI line, a largest-tenant sentence, a dividend per share by class). The three new ones are of the same kind as before: facts that the report gives in a form the extraction and the keyword steps do not read.

### 12.3 Open for the next round
1. RLI: investment-grade share from dollar amounts (non-investment grade + non-rated over fixed maturities).
2. REXR (and DLR): same-property NOI growth from a same-property table of revenues and expenses.
3. REXR: largest tenant share from the sentence "no single tenant ... more than X%".
4. TSN: dividend per share by share class (take the primary class) from XBRL members.
5. AFG, THG: THG's categories are 2.4% from the total (above the 2% of the control).
6. A question for you: batches 5, 6 and 7 each found three to six new bugs of the "present in the report, not read" kind. The strict gate remains open unless these families are closed one by one or the gate changes (for example: a list of families that count as "derivable, not stated" and are reported but do not fail a batch).

## 13. Four fixes, three general mechanisms, the updated gate, batch 8 (2026-11-01)

### 13.1 The four fixes (test database; reload without a model call, Buffett / Graham, coverage)
| Company | Fix | Before | After |
|---|---|---|---|
| TSN | dividend per share of the traded class (Class A) from the inline XBRL (`DERIVED ... class=CommonClassAMember`; shares by class summed) | 49.86 / 55.43 (G coverage 98%) | 49.86 / 55.43 (100%); G 3.5.2 missing -> 2.0/2.0 |
| REXR | same-property NOI = revenues - property expenses (+1.08% for 2025; 7.40, 8.19, 4.11 for 2022-2024), growth by CL22, `derived` with the formula | 87.95 / 92.06 (81% / 70%) | 85.76 / 92.99 (96% / 80%); B 3.4.2 6/6, G 3.7.2 4/4 |
| REXR | "no single tenant ... more than 2.4%" stored as a ceiling (`bound=max`), scored at 2.4; 10 largest tenants 13.9% a separate item `top10_tenants_share` | G 3.7.3 missing | G 3.7.3 2/2 |
| RLI | investment-grade share = 1 - (non-IG + non-rated) / fixed income (total from the report row, else XBRL), `derived`; no total = stays missing | 87.59 / 77.97 (90% / 75%) | 87.59 / 76.59 (90% / 85%); G 3.7.2 2.62/3, G 3.7.3 0/3 |
BOKF and CDNS unchanged. Other companies affected by a per-class XBRL: not scanned yet (open).
Notes: REXR B 3.4.1 became 0/4 (the NOI history now exists). `custom_tag` is stored as source_kind `ixbrl` (tag text `ixbrl:custom_tag ...`) so that the `financial_facts` constraint is unchanged.

### 13.2 The mechanisms
1. **`data_gap_review`** (migration `20261101150100`, test only; no access for anon / authenticated; closed rows older than 180 days go in the weekly cleanup). Written after every score; family, reason, passage (about 300 characters, no model). `vc.py gaps [--family X] [--state S] [--refresh]`. Run on all companies of test: 233 rows added, 150 open, 91 genuine (by rule). Largest open families: same_property_noi 16 companies, unencumbered 14, capital_ratio 11, ai_insufficient 10. Full output `scripts/state/k13_gaps.txt`.
2. **Derivation hints**: `derivation_hints` on `inv_ig_share`, `largest_tenant_share`, `same_property_noi_growth` (EXT-INS-INV v6, EXT-RE-OPS v2) and B14 `gross_profit`. The model returns components with quotes (`value_state = components`), the code computes and checks (`ext_checks.derive_item`); a final number from the model is refused. NOT yet exercised against the real model.
3. **Wide XBRL search** (`src/providers/xbrl_wide.py`, in all four providers): class of stock, close-named company elements, conflicts leave the year missing and go to the list.
All with unit tests (`tests/test_k6d2_gaps_wide.py`); 975 tests pass.

### 13.3 Batch 7 under the new gate
Fails: TSN dividend per share is a core item that was in the report and not read; REXR same-property NOI moved Buffett by 2.2 points (87.95 -> 85.76 with the tenant and NOI items). RLI (Graham -1.4) and the REXR tenant item are below 2 points and not core: recorded, not failing.

### 13.4 Batch 8 (CMA bank, UNM life insurer, OHI healthcare REIT, CLX regular, TXN technology)
Preflight `acceptance_preflight_8.txt`; log `acceptance_run_9.log`. Calls: OHI 23, TXN 16 (daily counter 140 of 450).
| Company | Result |
|---|---|
| OHI | complete, B 73.39 (81%), G none (55%) |
| TXN | complete, 72.38 / 77.12 (100%) |
| CLX | **ai_extract FAILED** (`AttributeError: NoneType has no attribute text`): scored 68.21 / 42.68 before the extraction |
| CMA | **not loaded**: the ticker is not in the SEC company list (Comerica merged); an unsuitable ticker, not a pipeline defect, but the load ended `failed` |
| UNM | **not loaded**: a network outage of about 40 minutes (all 5 retry rounds used; a heartbeat GAP of 931 s: the computer or the network was suspended) |

**Gate: not passed (batch 8 fails (a) and the rule "stop at a new kind of bug").**
- CLX is a new kind of bug: its FY2026 annual report (June 2026) is the latest 10-K in the filing cache, while `filing_periods` and the engine stop at FY2025, so `find_filing` finds no report for the engine's latest year and the extraction task crashes. Fix to design: the filing for the engine's latest fiscal year must be the one fetched, and the FY2026/FY2025 mismatch between the XBRL years and the filing periods must be understood first.
- OHI open items (7): same-property NOI, largest tenant (operator concentration is stated in other words), occupancy, unencumbered, debt maturities: passages mostly empty, so likely not reported in the usual form; NOT classified as real or bug yet.
- Batch 9 was not run (batch 8 not clean).

## 14. Fixes before the new batch 8, and batch 8 (2026-11-01)

### 14.1 CLX and non-calendar fiscal years
- **Cause.** CLX (June year end) filed its FY2026 10-K in August 2026, but SEC `companyfacts` does not carry it yet (only DEF 14A facts for 2026-06-30). The facts and `filing_periods` stop at FY2025 (the plan listed 2026 as "missing", nothing to write); the filing cache fetched "the latest 10-K" (FY2026). `find_filing(ticker, FY2025 end)` found nothing and the extraction task crashed (`AttributeError`).
- **Fix.** The extraction and the assessments read the 10-K of the latest LOADED fiscal year end (`latest_period_end`, within 20 days); if it is not cached it is downloaded; the documents of the filing are completed (cached files are not fetched again). Second finding: CLX files its financial statements in a companion document of the same inline-XBRL filing (`clx-20250630_d2.htm`), which was never downloaded (so B14 found no sections); `filing_documents` now takes `<primary>_d<n>.htm`, and an extraction call stored as "no call" is asked again.
- **Other companies** (`scripts/k14_fy_check.py`, 95 companies of test): the report read by the old rule differs from the engine's year only for CLX. MSFT, GIS, HRL, CAG, SJM, NTAP, PANW and the rest: no difference, nothing to re-run. Companion documents (`scripts/k14_companions.py`, 96 companies): only CLX has one; data missing because of it: CLX only (B14, 4 assessments).
- **A score is final only after the extraction; partial is marked.** When an AI task of the score (extract / assess / classify) fails for good the company becomes `failed`, the reason goes to the queue row and the administrator log, and the latest score run is flagged `partial` (`score_runs.flags.partial`). Unit test.

### 14.2 Assessments answered "insufficient evidence" while sections were missing
`assess.stale_insufficient`: an answer with `section_not_found:<id>` in its flags (or no call because the primary section was missing) is asked again when the section exists now; an answer the model gave with all sections is never asked again. Twenty such answers exist in test: 3 no-call (all CLX), 3 with a section missing (CLX B3.2-Q4, VICI and HRL B3.7-Q3: `NOTE-ACQ`, the note probably does not exist), 14 the model's own "insufficient" with all sections (KO, INTC x2, UBER, AFG, NKE, RF, ORI, ZION, ANET x3, EWBC and others): not re-asked.
CLX re-asked (4 calls): B3.7-Q5 and G3.8-Q3 now answered (gaps closed), B3.2-Q4 the model again says insufficient (all sections present), B3.1-Q4 still has no primary section. CLX before 72.22 / 40.68 (coverage 94% / 98%), after 72.37 / 39.68 (96% / 100%).

### 14.3 Tickers not on the SEC list, network, preflight
- `load` of a ticker that is not on the SEC list: `unsupported` with "the ticker was not found on the SEC list - the company may have merged or been delisted" (was `failed`). The preflight of a batch now checks the SEC list and Form 25 / merger: it rejected CMA (merged) and SNV (merged) - SNV was in the instruction, EWBC took its place. (No "request-company" code exists in the repository.)
- Five attempts lost to a network error: the task is `deferred_network` for 30 minutes and returns, up to 6 rounds; failed only for a permanent error (migration `20261101160100`, applied to test; unit test).

### 14.4 OHI, the 7 items
Real (not reported in the usual form): same-property NOI growth (B 3.4.2, G 3.7.2) - the report has no such measure; occupancy (G 3.7.1) - only in risk text; unencumbered (G 3.3.2) - only a joint-venture mortgage; stabilized yields (B 3.4.1) - only the contractual yield of existing triple-net leases (10.4%); debt maturities (G 3.2.2) - no maturity table found (not verified in depth). Largest tenant (G 3.7.3): the report says "one operator represented greater than 10% of our investments" - a floor, not a share. Synonyms added (operator / lessee / customer for tenant); a floor is stored as `largest_tenant_floor` (`bound=min`) and is not scored. EBITDARM does not occur in the report.

### 14.5 Batch 8 (new): EWBC bank, LNC life insurer, SUI manufactured-housing REIT, SBUX (September year end), ADI technology
Preflight `acceptance_preflight_9.txt`; log `acceptance_run_10.log`; calls EWBC 17, LNC 16, SUI 24, SBUX 15, ADI 15 (daily counter 244 of 450).
| Company | Result | Buffett / Graham (coverage) |
|---|---|---|
| EWBC | complete | 96.63 / 97.62 (90% / 79%) |
| LNC | complete | none (32%) / 67.21 (70%) |
| SUI | complete | 82.07 / 89.11 (81% / 68%) |
| SBUX | complete | 78.07 / 39.47 (100% / 100%) |
| ADI | complete | 78.22 / 75.62 (100% / 100%) |
**(a) Without contact: 5 of 5**; no failure, retry or heartbeat gap.
**Gate: not passed - three new kinds of data that are in the filing and not read (core items):**
- **EWBC:** nonaccrual loans / ACL missing (B 3.6.3, B 3.6.4, G 3.3.2, G 3.3.3). `companyfacts` has `FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest` (2022-2025), `FinancingReceivableAllowanceForCreditLosses` (2018-2021) and `FinancingReceivableNonaccrualNoAllowance`: the bank tag chains do not use them (a tag-chain gap; CET1 was fixed by the extraction).
- **LNC (life insurer):** Buffett score impossible (coverage 32%): premiums earned jumps from 5.4 bn (2020) to 11.7 bn (2021) (tag change), realized investment gains only for 2024-2025, claims series end in 2022, so the margins and ROE need "3 years" and are missing; life-insurer float cost, capital ratio, categories and credit-quality table (the table exists in the text: "Investment Grade Securities ... 60.3%") not read. Life-insurer tag chains are the family to design.
- **SUI:** same-property NOI growth ("Same Property NOI growth" is named in the text; the table is not in a form the steps read), occupancy, largest tenant, unencumbered: not classified further.
SBUX and ADI: no open item. EWBC LCR is real (not reported); the OE-proxy and economic-value items of SUI are genuine by rule.
Batch 9 was not run (batch 8 not clean). Open: EWBC tags, LNC life-insurer chains, SUI same-property table, the 14 "model said insufficient" answers, CLX B3.1-Q4/B3.2-Q4.

## 15. Banks, life insurers, SUI, batch 8 (new) (2026-11-01 / 02)

### 15.1 EWBC and the banks (tag chains)
The ACL and loan tags were already in the chain. The missing item was the TOTAL nonaccrual for 2023-2025: the standard nonaccrual tag has no undimensioned value, `FinancingReceivableNonaccrualNoAllowance` is only the part without an allowance (93.4 m of 165.8 m) and was NOT used as the total. The total sits in the 10-K inline XBRL as the loans before allowance with the member `NonperformingFinancingReceivableMember` of the past-due axis (165,842 thousand, equal to "Total nonaccrual loans" in the text). `xbrl_wide.member_search` (all four providers; tag text `DERIVED ... at the member ... (the total only exists as a member)`) fills the years still missing.
EWBC before 96.63 / 97.62 (coverage 90% / 79%), after 96.97 / 95.98 (98% / 94%); B 3.6.3, B 3.6.4, G 3.3.2, G 3.3.3 now scored. The other banks (BOKF, CFG, FHN, FITB, HBAN, JPM, RF, WAL, ZION) were reloaded: only EWBC received a value (the "before" snapshot of the banks was lost because TBNK has no score run and stopped the script; the others are reported as unchanged because no wide-search note appeared for them). Banks after: BOKF 81.77/90.46, CFG 68.55/64.62, FHN 76.08/77.54, FITB 85.33/78.29, HBAN 80.39/83.31, JPM 94.04/87.03, RF 87.00/87.40, WAL 80.59/86.35, ZION 79.68/79.51.

### 15.2 LNC and the continuity of insurer series
- Premiums use one tag in all years; the jump 2020 -> 2021 (5.4 -> 11.7 bn) is a change of definition (LDTI restatement): in the overlap years the later filing differs from the original by 2.08x (2021) and 1.92x (2022), not a constant ratio, so the years cannot be connected. `series_basis.basis_break`: when a later filing restates a year by more than 15% and the year before it is not shown on the new basis, the older years are set missing with the reason (LNC premiums and total expenses: 2016-2020; also found: AFG 2019 (nii, revenue, expenses), THG 2016). Scores of AFG, THG, ACGL, CB, ORI, RLI and SIGI did not change.
- Realized gains: `DebtAndEquitySecuritiesRealizedGainLoss` (all years) added to the chain. Net investment income and benefits incurred exist in XBRL for all years (nothing to complete).
- Credit quality from the text ("Total investment grade ... % of total"): a derivation hint on `inv_ig_share` (EXT-INS-INV version 7); not yet exercised against the model.
LNC before: Buffett none (coverage 32%), Graham 67.21 (70%). After: Buffett 51.23 (75%), Graham 62.60 (80%).

### 15.3 Life insurers (partial support, no sub-profile)
What does not fit a life insurer in the INSURANCE criteria (stays Missing, no score when coverage is low), as input for the methodology work:
- B 3.5.1, B 3.5.2, B 3.5.4 (cost of float): a property-casualty concept; for LNC "fewer than 3 years", the float components changed.
- B 3.6.1 and G 3.2.1 (regulatory capital ratio): no numeric group ratio in the report (UNM: "regulatory basis not usable for a multiple").
- G 3.2.2 and G 3.7.3 (balance-sheet categories, credit-quality table): the categories are those of a property-casualty balance sheet; a life insurer's investment table has other lines (policy loans, limited partnerships).
- B 3.2.x (operating margin / ROE), B 3.5.3, B 3.8.5 (net margin) and the reserve-deviation items (B 3.6.2, G 3.3.1) depend on definitions that changed with LDTI (the basis break); their meaning for a life insurer needs checking.
- Not applicable by the matrix already: gross margin, cash-flow coverage (G 3.5.4), B 3.8.4.
**UNM (an ordinary load outside the gate, after the failed network attempt):** complete, 16 calls, Buffett 79.62 (90%), Graham 88.89 (82%). Open: G 3.7.3, G 3.2.2 (categories), B 3.6.1 / G 3.2.1 (capital ratio); G 3.7.2 closed. A second life insurer therefore scores with 82-90% coverage; its gaps are the same family as LNC's.

### 15.4 SUI
The same-property NOI row with the segments side by side ("Real Property NOI $ 686.9 $ 276.8 $ 963.7 $ 630.9 $ 280.9 $ 911.8") is read: the last column of each half is the total and the segment columns must add up to it; 2025: +5.69% (the report states 5.7%). Two bugs found on the way: a pattern that matched but failed its check stopped the table from being tried; and model rows (three per year - MH, RV, Total - all pending) counted as an answer, so the code never read the table (a model answer counts now only when approved). Years 2021-2024 use other column layouts: only one year is read, so B 3.4.2 and G 3.7.2 stay Missing (a layout family, open). Occupancy: "Same Property adjusted blended occupancy ... to 99.1%" is read (G 3.7.1 4.0/4.0). Manufactured housing is a residential asset type (the largest-tenant criterion is not applicable). Unencumbered (G 3.3.2): covenants only, no figure: real.

### 15.5 TBNK and housekeeping
- **TBNK** (id 2, exchange TEST) is "Test Bank Co", a synthetic fixture company of the first ETL stage (2026-10-19): 37 facts, 2 extraction items, no filing periods, no score, no queue. It is not an SEC company, so it has no score and cannot be loaded. It stays; reloads and "before" snapshots skip the TEST exchange from now on.
- My bank reload loop ran `load TBNK`, which created a duplicate company row TBNK/US (id 120, `unsupported`) and one log row (id 211). Deleted with the owner's approval after checking every child table (`valuations` is linked by run_id and the company had no score runs): `data_update_log` id 211, then `companies` id 120. TBNK id 2 remains.
- UNM id 106 had stayed `failed` from the network outage of the first batch-8 attempt; it was loaded on its own (15.3).

### 15.6 Batch 8 (new): WTFC bank, KNSL P&C insurer, WY timber REIT, KR (January year end), KLAC (June)
Preflight `acceptance_preflight_10.txt`; log `acceptance_run_11.log`; calls 20, 19, 23, 15, 16.
| Company | Result | Buffett / Graham (coverage) |
|---|---|---|
| WTFC | complete | 87.70 / 93.94 (90% / 83%) |
| KNSL | complete | 97.88 / 97.16 (90% / 75%) |
| WY | complete | 42.32 / 57.13 (79% / 68%) |
| KR | complete | 73.33 / 42.46 (100% / 100%) |
| KLAC | complete | 95.60 / 91.56 (100% / 100%) |

**(a) 5 of 5 without contact**; no failure, retry or network wait. The heartbeat shows one gap of 41,530 s (the computer slept overnight between KNSL and WY despite the keep-awake request; the run resumed by itself).
**Gate: not passed.** WTFC: the CET1 ratio of the company (10.3%) is in the capital table of the report after the minimum columns ("Common Equity Tier 1 Capital Ratio 4.50 7.00 N/A 10.3") and was not read: B 3.6.1 and G 3.2.1 are Missing - a core bank item present in the report. RWA not read either (G 3.7.3). WTFC LCR: real (not reported). KNSL: no numeric statutory capital ratio (real); the investment-grade share is not stated as a percentage ("rated A- or better" for the whole portfolio) - open, not verified. WY: same-property NOI, occupancy, largest tenant and unencumbered are missing; a timberland company has none of these measures - the engine does not yet mark them not applicable for this asset type (real by nature, open as a rule). KR, KLAC: no open item.
Batch 9 was not run. Open: WTFC CET1 table (columns minimum / buffer / well-capitalized / actual), SUI layouts of 2021-2024, KNSL IG wording, WY asset type, EXT-INS-INV version 7 with the model.

## 16. Column roles, IG share, timberland, SUI layouts, insufficient history, batch 8 (new) (2026-11-02)

### 16.1 WTFC - the company column of a capital table
The table is "Minimum | Minimum + buffer | Well-capitalized | The Company" with no year columns. The position logic counted three numbers as three years and stored the CET1 ratio 10.3% as FY2023. Now a table whose preceding header (900 characters) names roles (minimum, well-capitalized, required, buffer ...) and has no year header keeps the period of the model (`column_roles`, flag `period_kept_columns_are_roles`). WTFC before 87.70 / 93.94 (coverage 90% / 83%), after 88.93 / 94.85 (98% / 94%): B 3.6.1 4/4, G 3.2.1 8/10. A stale row of the old run (FY2023, 10.3) was rejected with a reason. RWA stays Missing (the model returned not_disclosed; the table of the report has no RWA amount that I found). The other ten banks were re-judged from the stored answers (no model): scores and coverage unchanged (CFG 11 and HBAN 10 internal rows were re-judged, none reached a score).

### 16.2 Investment-grade share (KNSL)
The report says 81.9% rated A- or better and 1.4% unrated or below investment grade: the share is 100 - 1.4 = 98.6% (unrated counted as not investment grade), not 100% (the statement "all ... rated X or better" is a separate pattern that gives 100). Both patterns and the derivation hint (EXT-INS-INV version 8) added; unit tests. KNSL before 97.88 / 97.16 (90% / 75%), after 97.88 / 95.85 (90% / 85%): G 3.7.2 3.0/3.0, G 3.7.3 1.6.

### 16.3 "Not applicable" only where the concept does not exist
Only `timberland` and `farmland` (new asset types, detected from the business text; utilization not applicable) turn same-property NOI growth (B 3.4.2), occupancy (G 3.7.1), property-income resilience (G 3.7.2), tenant concentration (G 3.7.3) and the unencumbered share (G 3.3.2) from Missing into Not applicable. An operating REIT (hotels, senior-housing operations) and a lease-based type stay Missing. WY: 42.32 / 57.13 unchanged, Graham coverage 68% -> 87%. (An earlier broader rule, by operating_reit, made DLR lose 7.7 Graham points because its rent tag is missing: withdrawn.)
Operating REIT wording added to the keyword step and the hint (EXT-RE-OPS version 3): SHOP / hotel occupancy sentences, "same-store (SHOP / cash) NOI grew X%", "comparable hotel EBITDA / NOI ...".
**VTR and HST re-extracted with version 3 (2 calls each):** VTR 89.92 / none (81% / 55%) -> 92.64 / 67.07 (81% / 70%); HST 91.15 / none -> 91.15 / 75.06 (81% / 70%). The Graham score appears because G 3.2.2 (debt maturities / liquidity) is now scored (VTR 4.69, HST 8.0) and the coverage is 70%; it is not an effect of "not applicable". The synonyms read two same-store growth years for HST only; VTR none.
**VTR, what changed in the rows:** 31 rows were written. (a) 14 occupancy rows of EXT-RE-OPS version 1 were rejected by the explicit rule "superseded by skill version 3" (`retire_old_skill_rows`, approval_source empty = not a person) and replaced by 14 version-3 rows with the same values (78.7/79.7, 84.5/87.3, 86.1/88.9, 88.3/88.6, 90.0/90.4, 54.8/57.8 ...), approved by the control bounds_0_100. (b) 4 rows of EXT-RE-LIQ (debt maturities 2.17 bn, 1.63 bn) and EXT-RE-FFO (reported FFO FY2023) were inserted - they had no row before, nothing was replaced. (c) EXT-GENERAL was asked for the first time (4 items): 9 rows with value null approved (not_disclosed items), 3 `cost_of_revenue` rows rejected (label mismatch with "triple-net leased properties"). The same stored answers judged by the code of 0c1614f and by today's code give identical rows (121 of 121): the code changes of this stage changed no value. No approved row was replaced without an explicit rule.
**VTR text, same-store / SHOP / occupancy (no model): the data is in the report and was not read - a bug.** "Same-Store NOI-SHOP ... NOI $ 877,998 $ 760,531 $ 117,467 15.4 %", "Same-Store NOI-OM&R ... NOI $ 554,606 $ 542,451 ... 2.2 %", "Same-Store NOI-NNN ... NOI $ 470,254 $ 444,322 ... 5.8 %" (FY2025 10-K; the FY2024 report has the same three tables). The company-wide same-store NOI is the sum of the three segments (1,902,858 vs 1,747,304, +8.9%) - not read. Occupancy: "Average Unit Occupancy ... 88.9 % 86.1 %" (SHOP) and OM&R "Occupancy at December 31" are read as separate rows per segment (approved); the engine takes one series per year, so the segments are not combined (a rule is missing: which basis or weights). No sentence of the form "occupancy ... N%" exists. These two items are the VTR family for the next round.

### 16.4 EXR and SUI (same-property tables)
EXR: every year is read from the table "Total same-store net operating income $ X $ Y" of the reconciliation, which is the NOI of the whole same-store pool of that year (not a segment): FY2021 898,815 vs 750,838 (+19.71%), FY2022 1,104,132 vs 917,970 (+20.28%), FY2023 1,186,120 vs 1,153,795 (+2.80%), FY2024 1,233,706 vs 1,252,777 (-1.52%), FY2025 -1.69%. The 2020 report's own line "Same-store net operating income $ 769,936 $ 775,273 (0.7)%" agrees in form. EXR 72.59 -> 70.14 (B 3.4.2 6.0 -> 4.2 because the 5-year median is now 2.8%; G 3.7.1 2.4 -> 3.27).
SUI: three layouts are read (segments side by side with a footnote mark; the first block "Total Same Property" with a change column that must agree; segments that add up to the total): 2021 +11.19%, 2022 +5.43%, 2023 +7.27%, 2024 +4.05%, 2025 +5.69%. SUI 82.07 / 89.11 (81% / 68%) -> 80.76 / 90.39 (96% / 78%); B 3.4.2 6/6, G 3.7.2 4/4.
**Input for the REIT calibration: Buffett 3.4.1 (incremental return over WACC) is 0/4 for both SUI and REXR** (the NOI history now exists, the incremental return does not exceed the WACC proxy).

### 16.5 A short history is a final state of its own
`insufficient_history` (new processing_state; migration `20261102120100`, applied to test; the reason is kept in `unsupported_reason`): a company with fewer than 3 loaded annual reports ends there with "היסטוריה קצרה מדי לציון (X שנים; נדרשות 3)"; no score / analysis / AI task is queued, an open one ends as "not relevant", a later one neither runs nor fails; the data jobs still run. The SEC daily index already queues a `new_report` load (priority 3) for every company by CIK; after the load, with 3 years the company returns to the normal path and the first score is queued. Unit test of the whole sequence (1 year -> 2 years -> third report -> first score).
**PNFP** (the successor registrant after the merger with Synovus has one annual report): after `load PNFP --job repair` the state is insufficient_history with the reason; its old analysis task (959) was closed as "not relevant: ..." with the reason, not deleted; no score run, one period.
**For merging with the `security` branch:** `v_stocks` and `v_stock_page` (security branch) must show `insufficient_history` as "היסטוריה קצרה — יקבל ציון כשיהיו 3 דוחות שנתיים", not as "not supported". `v_company_status` (main) returns the state and the reason as they are.
The batch preflight now requires at least 5 annual reports (10-K fiscal years) under the same CIK (selection of gate companies only).

### 16.6 Batch 8 (new): PNFP bank, MKL P&C insurer, EPR experiential REIT, COST (August year end), AMAT
Preflight `acceptance_preflight_11.txt`; log `acceptance_run_12.log`. Scored again with the final code (no model) before the classification.
| Company | Final state | Buffett / Graham (coverage) | Calls |
|---|---|---|---|
| PNFP | insufficient_history (1 year) - the final state is right, no touch | - | 2 |
| MKL | complete | 64.88 / 61.11 (88% / 75%) | 29 |
| EPR | complete | 82.01 / none (81% / 55%) | 25 |
| COST | complete | 95.62 / 83.00 (100% / 100%) | 15 |
| AMAT | complete | 98.30 / 98.22 (100% / 100%) | 15 |
**(a) 5 of 5 without contact** (PNFP counted by its final state; its analysis task failed in the first run - the cause fixed in 16.5). One heartbeat gap of 390 s.
**(b) Missing items:**
- COST, AMAT: none.
- MKL: capital ratio - real (no numeric ratio); investment-grade share - the report says "96% ... rated AA or better" (a floor, not the share) - real; **G 3.2.2 and G 3.7.3 (balance-sheet categories, credit table): the data is in the report, in TWO balance sheets** (the parent-only statements "Total Investments 28,801,550" and the consolidated "Total Investments 32,835,960") **and was not read - a bug of the family "second statement of the same report"** (not measured; G 3.2.2 is 5 and G 3.7.3 3 points of the Graham quality score, so a 2-point effect is likely). B 3.1.4: the model said insufficient evidence.
- EPR: same-property NOI, unencumbered share, largest tenant, occupancy - not in the report (real; occupancy closed by the keyword step); committed undrawn facilities - "funds available under our unsecured revolving credit facility" without an amount in the text I searched (not verified); OE-proxy and economic-value items genuine by rule.
**Gate: not passed** - MKL (the second balance sheet). Batch 9 was not run.

### 16.7 Open
MKL: the two balance sheets (parent-only against consolidated: take the consolidated); VTR: same-store NOI as the sum of the segments and a rule for the occupancy of several segments; HST/VTR synonyms for the stated growth; EPR facility amount; EXT-INS-INV version 8 against the model (KNSL used the keyword step, not the hint); the `v_stocks` / `v_stock_page` text (security branch).

## 17. The gate of 2026-11-02, parent-company pages, wrong data, administrator tools, batch 9 (2026-11-02 / 03)

### 17.1 The gate (decision of 2.11, replaces the earlier definition)
A batch fails only when (1) there is a manual touch or a failure of the pipeline, or (2) a wrong figure that was not recognised entered the score (wrong source, wrong balance sheet, wrong year, wrong units). A missing figure - a core one too - does not fail: it is written to `data_gap_review` and handled. Two clean batches in a row of five new companies (bank, insurer, REIT, regular company, technology; at least 5 annual reports under the same CIK) pass the gate.

### 17.2 Parent-company pages are never a source (E)
`src/ai/parent_only.py` finds the pages of "Schedule II - Condensed Financial Information of Registrant (Parent Company Only)" (a reference such as "See Schedule II" is not the schedule) and removes them from the text before sections are searched, for the extraction and for the AI questions; a quote inside them is refused. Unit test. Check on all 23 banks and insurers of test (`scripts/k17_parent_check.py`, every extraction row of every status against the parent pages of the latest report): **0 rows read from the parent company alone** (ACGL, AFG, CB, KNSL, LNC, MKL, ORI, RF, RLI, THG, UNM, AIZ have such pages; none was used). XBRL cannot bring them in: `companyfacts` carries no dimensioned facts and the inline-XBRL searches read only the dimension they name (class of stock, past-due member, debt instrument, segment).
**Correction of section 16.6:** the "second balance sheet" of MKL is the table "Markel Insurance" of the MD&A, not the parent company. The real cause of the pending rows: the equity-method investments (737.6 m) are held in other assets, not in Total Investments, so the categories added up 2.2% above the total. `control_inv_sum` may now leave an optional category (equity method, other) out of the sum when the others add up to the total (AFG, whose equity-method line belongs to the total, is unchanged); the control was not loosened. MKL: G 3.2.2 is scored 5.0/5.

### 17.3 Wrong data (D) - the controls on XBRL figures
Existing before this stage (`src/pipeline/dq.py` and the providers): reporting currency (a non-USD filer's monetary figures are held), share-count scale (the provider guard rescales x1000 / x1e6 or sets missing; the second look on the whole series holds a larger mismatch), sign of revenue and total assets (flag), the balance identity assets = liabilities + equity + noncontrolling interests within 1% (flag), restatement against the stored value (flag), year coverage (note); in the providers: the 9% plausibility check on total debt, the debt-component totals, the pre-tax / interest derivations marked derived. Added in this stage: **`suspect_magnitude`** - a revenue, total assets, total liabilities, equity, loans or deposits figure more than 20x (or less than 1/20) of both neighbouring years while the neighbours are within 2.5x of each other is held back: it is not in the calculation, the user sees it as missing, the administrator sees it as WRONG with the reason (`data_gap_review`, family `suspect_data`, priority 1; unit test); **`basis_break`** (a definition change between filings: older years set missing with the reason: LNC, AFG, AIZ); **the parent-company exclusion** (17.2); the quote / number / period checks of the extraction (existing) with the new **column roles** (the position of a number in a regulatory table does not give the year) and **`stale_insufficient`**. Light cross-check added (`scripts/k17_facts_in_report.py`): the latest-year revenue, net income, total assets, equity and EPS of each company must appear in the printed report.

### 17.4 Core figures and the administrator (B, C)
After every score: a core figure missing in the latest loaded year (general: revenue, net income, EPS, equity, operating cash flow, capex, diluted shares; bank: net income, equity, loans, deposits, EPS and an approved CET1; insurer: premiums earned, net income, equity, EPS; REIT: revenue, net income, EPS, total assets - the REIT dictionary has no equity item) writes a row of `data_gap_review` (family `core_missing`, priority 1; new column `priority`, migration `20261102150100`, applied to test) and an `admin_alert` (a mail when Resend is connected). The score is given at a coverage of 60% or more as before. (A first version listed "equity" as a core figure of a REIT: a false alarm for SLG, corrected.)
**`vc.py gaps fill <ticker> <item> <fiscal_year> <value> --quote "..." [--source-url URL] [--by NAME]`:** an approved `human_review` row with the quote; the pipeline's rows for the same item and year are set aside (rejected, with the reason); the audit row in `data_update_log` (`update_scope = gaps_fill`: who, when, before, after, quote, source); the score is calculated again and the rows of the list that the new score no longer holds are closed. Refused without a quote. Unit tests. Only when the administrator decides that the pipeline does not manage.

### 17.5 VTR (F)
The same-store NOI of the segments (SHOP, OM&R, triple-net) is summed when the report says that it gives it "for each of our reportable segments" (at least two segments, the quote holds every segment row, the basis holds the formula): 2022 +7.57%, 2023 +4.26%, 2024 +6.87%, 2025 +8.90% (2025: 877,998 + 554,606 + 470,254 against 760,531 + 542,451 + 444,322). A model answer counts as covering a year only when it is ONE approved value (VTR's three approved segment rows are no usable answer). VTR 92.64 / 67.07 (coverage 81% / 70%) -> 88.99 / 67.07 (96% / 70%): B 3.4.2 6/6, G 3.7.2 4/4, B 3.4.1 0/4 (VTR joins SUI and REXR in the REIT calibration list). Occupancy between segments is still Missing (no rule for the basis).
A backspace character that an earlier edit had put into a pattern (`\b` written in a non-raw string) was found because it silently disabled this pattern; all files of the project were scanned (two old scripts, `build_bank_regulatory.py` and `insurance_extraction_spec.py`, had them before this stage and were left untouched).

### 17.6 Batch 9: ONB bank, AIZ insurer, SLG office REIT, TGT (January year end), ADSK (technology)
Preflight `acceptance_preflight_12.txt` (all new, at least 5 annual reports under one CIK); log `acceptance_run_13.log`; 17, 16, 23, 16, 16 calls.
| Company | Final state | Buffett / Graham (coverage) |
|---|---|---|
| ONB | complete | 77.58 / 82.73 (96% / 94%) |
| AIZ | complete | 73.84 / 90.26 (90% / 75%) |
| SLG | complete | 57.81 / none (81% / 55%) |
| TGT | complete | 75.75 / 66.13 (100% / 100%) |
| ADSK | complete | 95.04 / 58.83 (98% / 100%) |
**Manual touch / failure of the pipeline: none.** Two temporary network errors (ONB score: ReadTimeout, 39 s; ADSK: ConnectError, 30 s) were retried by the pipeline by itself; the computer slept between TGT and ADSK (heartbeat gaps) and the run resumed. **Wrong data that entered the score: none found:** no row from the parent company, no `suspect_data` row, no DQ flag; the latest-year revenue / net income / total assets / equity / EPS of all five are printed in their reports; AIZ's net investment income before 2019 was set missing by the basis-break control (a restated definition).
**Missing figures (do not fail; in `data_gap_review`, handled in the background):** ONB LCR (not reported), ONB RWA (not read); AIZ regulatory capital ratio (no numeric ratio) and the investment-grade share ("below investment grade securities represented approximately 6% of our total investments" and fixed maturities 85%: derivable, not read); SLG: committed undrawn capacity ("total undrawn capacity of $602 ..." is in the report, not read), largest tenant ("our five largest tenants ..." is in the report, not read), occupancy table, same-property NOI and unencumbered share not stated; ADSK one AI answer. Core figure gaps: none (SLG's equity row was a false alarm of the first core list).
**Batch 8 under the same gate:** no manual touch (PNFP ends in its own final state `insufficient_history`), no wrong data (parent-company check 0, the equity-method line fixed, the five-figure cross-check passes for MKL, EPR, COST and AMAT): **clean**.
**Gate: PASSED** - two consecutive clean batches (8 and 9).

### 17.7 Open (background)
The values listed as present-but-unread: AIZ investment-grade share, SLG undrawn capacity and largest tenant, VTR occupancy between segments, MKL credit-quality table, EPR facility amount, ONB RWA; EXT-INS-INV version 8 against the model; `v_stocks` / `v_stock_page` text for `insufficient_history` (security branch); the REIT calibration list of Buffett 3.4.1 (SUI, REXR, VTR).
