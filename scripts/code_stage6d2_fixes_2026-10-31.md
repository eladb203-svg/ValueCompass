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
