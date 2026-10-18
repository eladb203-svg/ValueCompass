# מיפוי מילון הנתונים (Rulebook חלק E) מול Supabase — 2026-10-17

מסמך קריאה בלבד. נבדק: פרויקט Supabase `ValueInvestConsult` (סכמת `public`, 7 מיגרציות רשומות), תיקיית `supabase/migrations`, קוד `src/`, קובצי CSV/JSON ב-`scripts/`. לא נכתב דבר ל-DB ולא הורצה מיגרציה.

## 1. ממצאים עיקריים

1. **ה-DB כמעט ריק.** `companies` = 1, `company_listings` = 1; `financial_yearly`, `financial_ratios`, `market_snapshot`, `score_details`, `company_score_summary` = 0 שורות. כל הריצות של המנוע (`scripts/output*/*.json`) קוראות מ-cache של SEC companyfacts (`scripts/cache/sec`) וכותבות קובצי JSON — לא ל-DB.
2. **המיגרציות בריפו לא מסונכרנות.** בריפו קובץ אחד (`20260908142258_convert_sync_year_fields_to_arrays_v2.sql`); ב-DB רשומות 7 (`create_company_listings`, `rename_company_currency_to_reporting_currency`, `add_public_and_listing_dates`, `align_data_update_log_with_financial_etl`, `add_financial_yearly_reporting_currency`, `create_company_with_listing_rpc`, `convert_sync_year_fields_to_arrays_v2`). ששת האחרות לא קיימות כקבצים. לטבלאות הבסיס (companies, financial_yearly וכו') אין קובץ יצירה בריפו.
3. **`financial_yearly` שטוחה וצרה:** 37 עמודות עסקיות, PK (`company_id`, `fiscal_year`), עמודת `source` אחת לשורה. אין שם תגית, אין עדיפות בשרשרת, אין flags, אין בסיס (group/company share), אין מצב ערך (נמצא / דווח כאפס / חסר / ל"ר). `NULL` מסתיר את ההבדל בין "דווח כאפס" ל"לא נמצא" (חשוב ל-SBC, C5, goodwill).
4. **מאגר החילוץ (E9) לא קיים בטבלה.** קיים רק כ-3 קובצי CSV בסכמות שונות (סעיף 3).
5. **תוצרי המנוע לא נשמרים** מעבר לשלושה ציונים בטבלת הסיכום (סעיף 4). `ai_pending`, כיסוי, טווח, שווי הוגן, מחיר קנייה — אין להם מקום.
6. **פרופיל (Part B) ו-`scoring_model_version` לא נשמרים** (קיים רק `calculation_version` כללי).
7. RLS מופעל בכל הטבלאות; הפוליסות לא נבדקו.

מקרא לטבלה: `FY` = `financial_yearly` (לפי שנה ולפי חברה: PK `company_id, fiscal_year`). "—" = לא נשמר. "מפתח" = מפתח חילוץ (item) בקובצי ה-CSV. בכל שורה של `FY` הפער הכללי (תגית / flags / בסיס / מצב ערך) חל, ומצוין בעמודת הפער רק אם יש פער נוסף.

## 2. טבלת מיפוי

| מזהה | נתון | איפה היום | פער | הצעה (טבלה/עמודה) |
|---|---|---|---|---|
| FIN-001 | EBIT | FY.ebit (+ FY.operating_income) | אין סימון "נגזר מ-pretax+ריבית"; תגית/flags לא נשמרים | `financial_facts` item=ebit, flags=`derived_pretax_plus_interest` |
| FIN-002 | Income tax | FY.income_tax_expense | פער כללי | `financial_facts` item=tax |
| FIN-003 | Pretax income | FY.income_before_tax | אין סימון fallback domestic+foreign | `financial_facts` item=pretax, flags |
| FIN-010 | Equity | FY.total_equity | לא ידוע אם parent או כולל NCI (תגית חלופית) | `financial_facts` + שמירת התגית שנבחרה |
| FIN-011 | Financial debt | FY.total_debt | סימון "ללא מאזן=0", finance lease, DEBT_PARTS ל-RE לא נשמרים | `financial_facts` item=fin_debt, flags |
| FIN-012 | Cash | FY.cash_and_equivalents | הפחתת funds held for clients (C3) לא מתועדת | `financial_facts` item=cash, flags=`c3_adjusted` |
| FIN-013 | Short-term investments | FY.short_term_investments | "חסר=0" (C5) לא מובחן מ-NULL | `financial_facts` status |
| FIN-020 | Net income | FY.net_income | פער כללי | `financial_facts` item=net_income |
| FIN-021 | Preferred dividends | — | לא נשמר | `financial_facts` item=pref_div |
| FIN-022 | Preferred stock | — | לא נשמר (PNC מחילוץ) | `financial_facts` item=preferred |
| FIN-023 | Goodwill | FY.goodwill | C5 (חסר=0) | `financial_facts` status |
| FIN-024 | Intangibles | FY.intangible_assets | C5 | `financial_facts` item=intangibles |
| FIN-025 | Total assets | FY.total_assets | פער כללי | `financial_facts` item=assets |
| FIN-030 | Investment gains | — | לא נשמר | `financial_facts` item=gains_realized / securities_gain_loss |
| FIN-031 | MRB remeasurement | — | לא נשמר | `financial_facts` item=mrb_change, mrb_liability |
| FIN-032 | Goodwill impairment | — | לא נשמר | `financial_facts` item=goodwill_impairment |
| FIN-033 | AOCI by component | — | לא נשמר; רכיבים מ-inline XBRL | `financial_facts` item=aoci_afs, aoci_total, aoci_<רכיב> |
| FIN-040 | Rental revenue | — | לא נשמר | `financial_facts` item=rental_revenue |
| FIN-041 | Other property revenue | — | לא נשמר | `financial_facts` item=other_property_revenue |
| FIN-042 | Property opex | — | לא נשמר | `financial_facts` item=prop_opex |
| FIN-043 | New-investment yields | — (CSV: `acquisition_yield` וכו') | רק בקובץ | `extraction_items` |
| FIN-044 | Same-property NOI growth | — (CSV `same_property_noi_growth`) | בסיס (RE21) לא נשמר | `extraction_items.basis` |
| FIN-045 | Growth capital | — | לא נשמר | `financial_facts` item=acq_real_estate, development, ... |
| FIN-046 | Dispositions | — | לא נשמר | `financial_facts` item=sale_proceeds |
| FIN-047 | Gross RE at cost | — | לא נשמר | `financial_facts` item=re_gross, re_net |
| FIN-050 | Interest expense | FY.interest_expense | RE.interest_capitalized לא נשמר | `financial_facts` item=interest_expense, interest_capitalized |
| FIN-051 | Market cap | market_snapshot.market_cap (נוכחי, שורה אחת לחברה) | מחושב; אין היסטוריה לפי שנה | לא לשמור כעובדה; להשאיר מחושב |
| FIN-060 | Revenue | FY.revenue | BANK: nii+nonint ו-IN: premiums+fees לא נשמרים כרכיבים | `financial_facts` item=revenue + nii, nonint, premiums |
| FIN-061 | Cost of revenue / GP | FY.gross_profit | cost_of_revenue לא נשמר; לא ידוע אם נגזר (C4/C13) | `financial_facts` item=cost_of_revenue, claims_expense, flags |
| FIN-062 | Diluted EPS | FY.eps_diluted | לא ידוע אם מותאם ל-splits | `financial_facts` flags=`split_adjusted` |
| FIN-063 | Net interest income | — | לא נשמר | `financial_facts` item=nii |
| FIN-064 | Noninterest income | — | לא נשמר | `financial_facts` item=nonint |
| FIN-070 | Normalized FFO | — | מחושב; ללא שמירה | `financial_facts` item=ffo_normalized (derived) |
| TXT-001 | Business section | — | לא מיושם | `filing_text_chunks` section=business |
| TXT-002 | Risk Factors | — | לא מיושם | `filing_text_chunks` section=risk_factors |
| TXT-003 | Competition | — | לא מיושם | `filing_text_chunks` section=competition |
| TXT-004 | MD&A / governance | — | לא מיושם | `filing_text_chunks` section=mdna |
| TXT-005 | Segment/customer disclosures | — | לא מיושם | `filing_text_chunks` section=segments |
| FIN-080 | CFO | FY.operating_cash_flow | פער כללי | `financial_facts` item=cfo |
| FIN-081 | Capex | FY.capex | הערך נשמר כחיובי (נרמול); fallback inline לא מתועד | `financial_facts` item=capex |
| FIN-082 | D&A | FY.depreciation_and_amortization | בחירת C9 (סכום מול רכיבים) לא מתועדת | `financial_facts` item=da, flags |
| FIN-083 | Amortization of acquired intangibles | — | לא נשמר | `financial_facts` item=acq_amort |
| FIN-084 | SBC | FY.stock_based_compensation | **שלושה מצבים** (found/none/missing) לא נשמרים | `financial_facts.status` |
| FIN-085 | Current assets | FY.current_assets | הפחתת כספי לקוחות (C3) לא מתועדת | `financial_facts` item=cur_assets |
| FIN-086 | Current liabilities | FY.current_liabilities | C3 / C11 לא מתועדים | `financial_facts` item=cur_liab |
| FIN-087 | Dividends paid | FY.dividends_paid | C5 | `financial_facts` item=dividends |
| FIN-088 | Buybacks | FY.share_repurchases | C5 | `financial_facts` item=buybacks |
| FIN-089 | Acquisitions | — | לא נשמר (גם goodwill_acquired fallback) | `financial_facts` item=acquisitions |
| FIN-090 | Average share price (שנתי) | — (market_snapshot: מחיר נוכחי בלבד) | אין ממוצע שנתי | `price_history_daily` + view ממוצע שנתי |
| FIN-091 | Period-end shares | FY.shares_outstanding | cover-page fallback / C14 לא מתועדים | `financial_facts` item=shares_out, flags |
| FIN-092 | Weighted diluted shares | FY.weighted_avg_shares_diluted | התאמת OP units (RE28) | `financial_facts` item=shares_dil |
| FIN-093 | Deferred revenue, current | — | לא נשמר | `financial_facts` item=deferred_rev_current |
| FIN-100 | Provision for credit losses | — | לא נשמר | `financial_facts` item=provision |
| FIN-101 | Loans | — | לא נשמר | `financial_facts` item=loans |
| FIN-102 | Deposits | — | לא נשמר | `financial_facts` item=deposits |
| FIN-103 | NCO | — | לא נשמר | `financial_facts` item=nco_net, wo_gross, recoveries |
| FIN-104 | ACL | — | לא נשמר | `financial_facts` item=acl |
| FIN-105 | Nonaccrual loans | — | לא נשמר | `financial_facts` item=nonaccrual, past_due_90 |
| FIN-106 | CET1 / required CET1 | — (CSV `bank_regulatory.csv`) | בסיס/גישה (standardized/advanced) רק בשם המפתח | `extraction_items` |
| FIN-107 | LCR | — (CSV) | מצבי NA/MISSING לא מסוגי | `extraction_items.value_state` |
| FIN-108 | DPS | FY.dividends_per_share | fallback dividends/shares (C8) לא מתועד | `financial_facts` item=dps, flags |
| FIN-110 | Insurance revenue | — | לא נשמר | `financial_facts` item=premiums, policy_fees |
| FIN-111 | Claims and benefits | — | לא נשמר | `financial_facts` item=benefits |
| FIN-112 | Non-claims underwriting exp. | — | לא ממופה גם במנוע | נגזר; `financial_facts` item=uw_result (derived) |
| FIN-114 | Interest credited | — | לא נשמר | `financial_facts` item=interest_credited |
| FIN-116 | Float components | — | לא נשמר | `financial_facts` item=claims_gross, claims_net, reins_unpaid, fpb, pab, unearned, reins_prepaid |
| FIN-117 | Regulatory capital ratio | — (CSV `insurance_regulatory.csv`) | basis ACL/CAL/SCR/SMR רק ב-note חופשי | `extraction_items.basis` |
| FIN-118 | Prior-period development | — | לא נשמר | `financial_facts` item=prior_year_dev, ldti_remeasurement |
| FIN-119 | Government yield (annual) | — (קובץ `scripts/gov_yields.csv`) | לא ב-DB; אין ישראל (H-15) | `gov_yields` (currency, period_type, period, yield, series, source, retrieved) |
| FIN-120 | Straight-line rent | — | לא נשמר | `financial_facts` item=straight_line |
| FIN-121 | Maintenance capex (RE) | — | לא נשמר | `extraction_items` / `financial_facts` |
| FIN-122 | TI/LC | — | לא נשמר | `financial_facts` item=ti_lc_total |
| FIN-123 | EBITDAre components | — | לא נשמר | `financial_facts` item=gains_sale, impairment, ... |
| FIN-125 | Economic property value | — (מפתח `fair_value_real_estate`) | רק בקובץ | `extraction_items` |
| FIN-130 | FX rates | — | לא מיושם (H-11) | `fx_rates` (currency, period_type, period, rate, source) |
| FIN-131 | First annual report date | companies.public_since_date (קרוב, לא זהה) | ההגדרה שונה ("ציבורית לצורך כיסוי"); אין predecessor | `companies.first_annual_report_date` + `company_filings` |
| FIN-132 | Receivables | FY.accounts_receivable | פער כללי | `financial_facts` item=receivables |
| FIN-133 | Short-term borrowings | — | לא נשמר | `financial_facts` item=st_borrow |
| FIN-134 | Central bank / FHLB advances | — | לא נשמר | `financial_facts` item=fhlb |
| FIN-135 | Repo & securities lending | — (מפתחות `funding:repo:*`) | רק בקובץ | `extraction_items` |
| FIN-136 | Investment portfolio by category | — | לא נשמר | `financial_facts` item=investments, `extraction_items` לקטגוריות |
| FIN-137 | Committed undrawn facilities | — (מפתח בקובץ) | רק בקובץ | `extraction_items` |
| FIN-138 | Debt maturities | — | לא נשמר | `financial_facts` item=mat_year1, mat_year2 |
| FIN-139 | Long-term debt | FY.long_term_debt | פער כללי | `financial_facts` item=debt_lt |
| FIN-140 | Loan breakdown | — (`loan:<line>`) | רק בקובץ | `extraction_items` |
| FIN-141 | Total regulatory capital | — | נגזר ומסומן, לא נשמר | `extraction_items` + flags |
| FIN-142 | Unencumbered NOI/assets | — | רק בקובץ | `extraction_items` |
| FIN-143 | Stabilized vs development | — | רק בקובץ | `extraction_items` |
| FIN-144 | RWA | — | רק בקובץ | `extraction_items` |
| FIN-145 | Occupancy / utilization | — (CSV `occupancy`) | בסיס (RE21) רק בשדה note | `extraction_items.basis` |
| FIN-146 | Largest tenant share | — | רק בקובץ | `extraction_items` |
| PRC-001 | Share price | market_snapshot.current_price (+ previous_close, 52w, market_date, source) | שורה אחת לחברה (PK company_id) — אין היסטוריה, אין בדיקת טריות (E1), אין מחיר מתואם splits; FK ל-listing חסר | `price_history_daily` (listing_id, date, close, split_factor, fetched_at) + `market_snapshot.is_stale` |
| FIN-150 | Government yield (monthly) | — (קובץ CSV) | לא ב-DB | `gov_yields` period_type=month |
| FIN-151 | 10-year EPS history | FY.eps_diluted (שורה לכל שנה) | המבנה מתאים; חסרה התאמת splits | `financial_facts` item=eps |
| FIN-152 | NAV inputs (RP2a) | — (`bsa_<class>__<slug>`) | רק בקובץ; סיווג ללא ציטוט ואישור | `extraction_items` |
| FIN-153 | NCI and OP units | — | לא נשמר | `financial_facts` item=nci_*; `extraction_items` ל-OP units |
| FIN-160 | Goodwill acquired (N-01) | — | לא נשמר | `financial_facts` item=goodwill_acquired |
| FIN-161 | Total liabilities (N-02) | FY.total_liabilities | פער כללי | `financial_facts` item=liabilities |
| FIN-162 | Funds held / restricted cash (N-03) | — | לא נשמר | `financial_facts` item=funds_held_clients, restricted_cash |
| FIN-163 | Cover-page share count (N-04) | — | לא נשמר | `financial_facts` item=shares_cover |
| FIN-164 | Weighted basic shares (N-05) | — | לא נשמר | `financial_facts` item=shares_basic |
| FIN-165 | Pretax domestic/foreign (N-06) | — | לא נשמר | `financial_facts` item=pretax_domestic, pretax_foreign |
| FIN-166 | Depreciation; ROU amortization (N-07) | — | לא נשמר | `financial_facts` item=depreciation, rou_amort |
| FIN-167 | Non-current marketable debt securities (N-08) | — | לא נשמר | `financial_facts` item=mkt_sec_noncurrent |
| FIN-168 | Claims expense, STANDARD (N-09) | — | לא נשמר | `financial_facts` item=claims_expense |
| FIN-169 | NI to common; ProfitLoss; NCI (N-10) | — | לא נשמר | `financial_facts` item=ni_common, profit_loss, ni_nci |
| FIN-170 | 90+ past due; uninsured deposits (N-11) | — | לא נשמר | `financial_facts` / `extraction_items` |
| FIN-171 | SCB; G-SIB; LCR type (N-12) | — (CSV) | רק בקובץ | `extraction_items` |
| FIN-172 | Discontinued operations (N-13) | — | לא נשמר | `financial_facts` item=disc_ops |
| FIN-173 | Structural-change indicators (N-14) | — | לא נשמר | `financial_facts` + `extraction_items` (structural_event) |
| FIN-174 | Separate accounts; MRB; investments (N-15) | — | לא נשמר | `financial_facts` item=separate_accounts, ... |
| FIN-175 | Catastrophe losses; ALM (N-16) | — | רק בקובץ | `extraction_items` |
| FIN-176 | RE taxes; repairs (N-17) | — | לא נשמר | `financial_facts` item=re_tax, repairs |
| FIN-177 | Gains on RE entities (N-18) | — | לא נשמר | `financial_facts` item=gains_re_entities |
| FIN-178 | Unrealized FX; FX net (N-19) | — | לא נשמר | `financial_facts` + `extraction_items` (re29b_fx_net) |
| FIN-179 | Debt extinguishment; transaction costs (N-20) | — | לא נשמר | `financial_facts` item=debt_extinguishment, transaction_costs |
| FIN-180 | RE sale gains; non-RE items (N-21) | — | רק בקובץ | `extraction_items` |
| FIN-181 | Company FFO reconciliation (N-22) | — | רק בקובץ | `extraction_items` (reconciliation inputs, E11) |
| FIN-182 | NAV details (N-23) | — | לא נשמר | `financial_facts` + `extraction_items` |
| FIN-183 | Profile-test inputs (N-24) | — | רק בקובץ | `extraction_items` |
| FIN-184 | Single-basis items (N-25) | — | רק בקובץ | `extraction_items` |
| FIN-185 | Secured debt (N-26) | — | לא נשמר | `financial_facts` item=secured_debt |

עמודות קיימות ב-FY שאין להן שורה במילון: `ebitda`, `free_cash_flow`, `adjusted_free_cash_flow` (נגזרים), `operating_income` (כפיל חלקי של EBIT), `filing_date`, `fiscal_year_end_date`. טבלת `financial_ratios` (גם היא נגזרת) לא מופיעה במילון; חלק מהמדדים שלה (ROIC, current_ratio, net_debt) מחושבים במנוע (`derived`) בנוסחאות שעשויות להיות שונות מהספר — לבדוק לפני שמשתמשים בה.

### סיכום כיסוי

- נשמרים כעמודה (במבנה, כרגע ללא נתונים): FIN-001, 002, 003, 010, 011, 012, 013, 020, 023, 024, 025, 050, 060, 061, 062, 080, 081, 082, 084, 085, 086, 087, 088, 091, 092, 108, 132, 139, 151, 161, PRC-001 (חלקית).
- נשמר חלקית / בהגדרה שונה: FIN-051, FIN-131, PRC-001, FIN-090.
- לא נשמרים כלל: כל השאר, כולל כל פריטי הבנקים/ביטוח/נדל"ן, כל TXT, FX ותשואות ממשלתיות.
- מאגר חילוץ: קיים בקבצי CSV בלבד.

## 3. מאגר החילוץ (E9)

**אין טבלה.** החילוץ נשמר בשלושה קובצי CSV, כל אחד בסכמה שונה:

| קובץ | עמודות | שורות |
|---|---|---|
| `scripts/bank_regulatory.csv` | ticker, item, value, unit, 10-K section, exact quote, verified, note | 268 |
| `scripts/insurance_regulatory.csv` | ticker, item, **period**, value, unit, 10-K section, exact quote, verified, note | 127 |
| `scripts/realestate_extracted.csv` | ticker, item, **year**, value, unit, quote, source, verified, note (שורת הערה בראש הקובץ) | 872 |

השוואה לדרישת E9:

| דרישה | מצב |
|---|---|
| מסמך | רק בטקסט חופשי בתוך `source` (accession, תאריך הגשה, שם קובץ) ב-RE; בבנקים/ביטוח אין מסמך נפרד |
| סעיף | קיים (`10-K section`, או בתוך `source`) |
| ציטוט מדויק | קיים (`exact quote` / `quote`) |
| דגל אימות | `verified` (YES/NO) — אימות אוטומטי של הערך מול הציטוט, לא אישור אדם |
| **בסיס** (קבוצה מול חלק החברה) | **חסר** — רק ב-`note` חופשי (`basis=ACL; entity=...`); ב-RE (RE21) בסיס ה-same-property/occupancy לא נשמר |
| **אישור מנהל** | **חסר** — אין approval status, מי אישר, מתי |
| קישור לחברה | מחרוזת `ticker` בלבד (אין `company_id`); בבנקים אין שנה (item בלי period) |
| מצבי ערך | `NA` / `MISSING` / "not disclosed" מקודדים בתוך `value`/`note` |
| מפתח ייחוד | אין; כפילויות אפשריות |

## 4. תוצרי המנוע — מה נשמר

מנוע הציון (`src/scoring/*.py`) מפיק אובייקט JSON לחברה (`scripts/output*/`). בטבלאות ה-DB קיימות רק:

- `company_score_summary` (שורה אחת לחברה, ללא היסטוריה): `buffett_quality_score`, `buffett_price_score`, `graham_quality_score`, `graham_price_score`, `overall_status`, `missing_fields[]`, `as_of_fiscal_year`, `years_available`, `market_snapshot_at`, `calculation_version`.
- `score_details`: שורה לכל (company, model, score_type, criterion, sub_criterion): `criterion_score`, `max_score`, `score_status`, `missing_fields[]`, `evidence` (jsonb), `explanation`. מפתח ייחוד `score_details_unique_current` — שורה "נוכחית" אחת, בלי run/גרסה.

| תוצר | מצב |
|---|---|
| ציון לכל תת-סעיף | **קיים מבנית** (`score_details` ברמת `sub_criterion`), לא מאוכלס |
| מצב: חסר / ל"ר | חלקית — `missing_data` / `not_applicable` קיימים; **`ai_pending` לא קיים** ב-check (`calculated, partial, missing_data, not_calculated, not_applicable, error`); גם `unknown_items.state` של המנוע לא נשמר |
| כיסוי (coverage) | **לא נשמר** (אפשר לדחוף ל-`evidence`, אך אין עמודה) |
| טווח מינימום–מקסימום (`range_min/range_max`, `observed_points`) | **לא נשמר** (גם לא ברמת קריטריון/מודל) |
| שווי (fair value) | **לא נשמר** |
| ציון מחיר | נשמר כסיכום בלבד (`*_price_score` 0-10); פירוט השיטה (DCF, Graham Number/Tech, state, flags) לא |
| מחיר קנייה + margin of safety + `buy_price_allowed` | **לא נשמר** |
| פרופיל (STANDARD/BANK/…) ונימוק, `scoring_model_version` | **לא נשמר** |
| הקלטת המחיר ששימש (price_current, תאריך, מקור) | לא נשמר ב-score (קיים רק ב-`market_snapshot` הנוכחי, שנדרס) |
| flags / data_problems של הריצה | לא נשמרים (אפשר ב-`evidence` של שורה, אין ברמת ריצה) |
| רשת: פרמטרים של DCF (growth, terminal, WACC) / reverse DCF / implied return | לא נשמרים |

## 5. טיוטת תוכנית מיגרציה (טקסט בלבד — לא להריץ)

עקרונות: מיגרציות חדשות בלבד, בלי שינוי הרסני בעמודות קיימות; כל שלב מיגרציה נפרדת ו-commit נפרד; DB writes דרך `FinancialETLCapabilities` בלבד; בלי hardcode של חברה/סמל/שנים. ההחלטות 0–2 דורשות אישור לפני כתיבה.

**שלב 0 — סנכרון הריפו (לפני כל דבר)**
- ייצוא ה-DDL של 7 המיגרציות הרשומות ושל טבלאות הבסיס לתוך `supabase/migrations` (baseline), כך שהריפו משקף את ה-DB.

**שלב 1 — עובדות פיננסיות (`financial_facts`)**
- טבלה חדשה, מבנה long: `company_id` (FK), `fiscal_year`, `item_key` (text, מפתח מילון כגון `ebit`, `sbc`), `dict_id` (FIN-xxx), `value` numeric, `unit`, `status` ('found','reported_none','missing','not_applicable'), `source_kind` ('xbrl','ixbrl','quarterly_sum','extraction','derived'), `tag` (התגית שנבחרה), `tag_rank` (מקום בשרשרת), `flags` text[], `basis` text, `accession`, `calculation_version`, `created_at`, `updated_at`.
- PK/ייחוד: (`company_id`, `fiscal_year`, `item_key`). אינדקס על (`item_key`, `fiscal_year`).
- `financial_yearly` נשארת כמות שהיא (שכבת תאימות לקוד הקיים). אפשרות: להפוך אותה בהמשך ל-view מעל `financial_facts` — **החלטה 1**: להשאיר טבלה ולמלא משני המקורות, או view.
- `dictionary_items` (טבלת הגדרה): `dict_id`, `item_key`, `title`, `statement`, `extracts` (code/ai), `required_not_implemented` bool, `profile_scope[]`; ו-`dictionary_tag_map` (profile, item_key, rank, tag) כדי שמיפוי התגיות ייקרא מהמסד ולא מקוד.

**שלב 2 — מאגר חילוץ (`extraction_items`, E9)**
- עמודות: `id`, `company_id`, `item_key`, `period` (fiscal_year, או תווית רבעון/FY), `value` numeric, `value_state` ('value','NA','MISSING','not_disclosed'), `unit`, `document_ref` (accession, שם מסמך, תאריך הגשה), `section`, `exact_quote`, `quote_verified` bool, `basis` ('group','company_share', או ערך הבסיס לפי RE21/ACL...), `note`, `approval_status` ('pending','approved','rejected'), `approved_by` uuid, `approved_at`, `extractor_version`, `created_at`.
- ייחוד: (`company_id`, `item_key`, `period`, `document_ref`). המנוע קורא רק `approved` (או מציג סימון).
- טעינה חד-פעמית מ-3 קובצי ה-CSV, ממפה `ticker` ל-`company_id` (לא hardcode). **החלטה 2:** האם שורות שכבר `verified=YES` נטענות כ-`pending` או כ-`approved`.

**שלב 3 — ריצות ציון**
- `score_runs`: `id`, `company_id`, `run_at`, `profile`, `profile_reason`, `rulebook_version`, `calculation_version`, `price_current`, `price_date`, `price_source`, `flags` jsonb, `data_problems` jsonb.
- הרחבת `score_details`: עמודות `run_id`, `coverage`, `observed_points`, `range_min`, `range_max`; הרחבת ה-check של `score_status` ב-`ai_pending`; הוספת `run_id` למפתח הייחוד (או נשמרת "ריצה נוכחית" + היסטוריה).
- `valuations`: (`run_id`, `model`, `method`, `fair_value`, `price_current`, `price_score`, `price_state`, `margin_of_safety`, `buy_price`, `buy_price_state`, `buy_price_allowed`, `details` jsonb).
- `company_score_summary`: להוסיף `profile`, `scoring_model_version`, `buffett_quality_coverage`, `graham_quality_coverage`, טווחים, `buffett_fair_value`, `graham_fair_value`, `*_buy_price`, `latest_run_id`.

**שלב 4 — מחירים, FX, תשואות, פרופיל**
- `price_history_daily` (listing_id, date, close, split_factor, fetched_at) + `market_snapshot.last_price_at`/`is_stale` (E1); `fx_rates` (FIN-130); `gov_yields` (FIN-119, FIN-150; מקור מ-`scripts/gov_yields.csv`).
- `company_profile_history` (company_id, fiscal_year, profile, reason, borderline, override_by) ל-E10/S3a.
- `company_filings` (accession, form, filed_at, fiscal_year) לצורך FIN-131, E2 (CIK) ו-E5.
- `filing_text_chunks` (TXT-001..005): company_id, fiscal_year, section, chunk_no, text, source_ref.

**שלב 5 — מעבר הקוד**
- `FinancialETLCapabilities` כותב ל-`financial_facts` (+ ממלא `financial_yearly` לתאימות), המנוע קורא מ-`financial_facts` ו-`extraction_items`; סקריפטי ה-JSON נשארים כבדיקה עד אימות זהות תוצאות על חברות קיימות.

**סיכונים:** נפח (פריט×שנה×חברה, אלפי שורות לחברה — דורש אינדקסים ו-RLS מתאימים); RLS לטבלאות החדשות (כתיבה רק ל-service role); הרחבת check ב-`score_status` דורשת drop/add של constraint; `financial_ratios` נשענת על `financial_yearly` — לא לשנות את ה-FK.
