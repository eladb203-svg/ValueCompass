---
title: "ValueCompass — Display Specification"
subtitle: "2026-10-19_09-59 · English (source of truth)"
---

# ValueCompass — Display Specification

**Scope:** what the user sees and how it is computed for display. **Separate from the Rulebook:** the Rulebook governs scoring and pricing; nothing in this document changes a score, a value or a buy price. **Language:** English is the source of truth; the Hebrew version is a translation.

| Part | Content | Status |
|---|---|---|
| 1 | Key financial metrics (six per company) | ✅ approved 2026-10-19 |
| 2 | Quality and price scores, value and buy price | to come |
| 3 | Flags, coverage and missing data | to come |

## 1. Key financial metrics

**Rule:** display only — no effect on any score. Computed in the view `v_display_metrics` from `financial_facts` (raw items and engine-derived items), one row per company and fiscal year. The company's profile selects the definition. Amounts in the reporting currency.

| Metric | STANDARD / TECH_ASSET_LIGHT | BANK | INSURANCE | INCOME_REAL_ESTATE |
|---|---|---|---|---|
| Revenue | Revenue (FIN-060) | Bank revenue = net interest income + noninterest income (FIN-063 + FIN-064) | Operating revenue = total revenue − investment gains in profit or loss (FIN-060 − FIN-030) | Total revenue (FIN-060) |
| Net income | Net income attributable to the parent (FIN-020) | Same | Same | Net income (FIN-020) **and** normalized FFO (FIN-070) |
| Earnings per share | Diluted EPS (FIN-062) | Same | Diluted EPS **and** operating EPS (DRV-006) | Normalized FFO per share (DRV-001) |
| Return on equity | ROE = net income / average equity (FIN-020 / avg FIN-010) | ROTCE = (net income − preferred dividends) / average tangible common equity; TCE = equity − preferred stock − goodwill − intangibles | Operating ROE = normalized operating profit after tax / average adjusted equity (DRV-004 / avg DRV-005) | Normalized FFO / average equity (labelled: ordinary ROE is distorted by depreciation) |
| Free cash flow | CFO − capex (FIN-080 − FIN-081; SBC not deducted, as the quality cards) | **Not shown** (cash flow is not representative for a bank) | **Not shown** | Owner earnings (DRV-002) |
| Debt / equity | Financial debt / equity (FIN-011 / FIN-010) | **CET1 ratio** instead (FIN-106; deposits are a bank's raw material) | Financial leverage = debt / (debt + adjusted equity) (FIN-011, DRV-005) | Net debt / EBITDAre (DRV-003) |

**Conventions:**

- **Average** equity = (start of year + end of year) / 2; first available year: end of year only, flagged.
- **Missing input** → the cell shows "—" with the reason (missing data, not applicable). No imputation.
- **Denominator ≤ 0** (e.g., negative equity, EBITDAre ≤ 0) → "not meaningful", not a number.
- **History:** every fiscal year in `financial_facts` (up to 10); the latest year is highlighted.
- **Labels** name the metric actually shown (e.g., "ROTCE" for a bank, "Net debt / EBITDAre" for real estate), never the generic name alone.
