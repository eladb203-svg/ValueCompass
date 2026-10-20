# Golden baseline 2026-10-20 (includes K3 fixes)

Scoring outputs of the 54 companies (general 14, managed care 6, bank 12, insurance 12, real estate 10) from the cached SEC data, generated with
`make_golden.py --as-of=2026-10-20 --stub-yfinance`; compare with `compare_golden.py`.

Includes the K3 rulebook corrections (Part H: H-01..H-08, H-19, C5). Versus the K1 baseline only insurance (H-02) and real estate (H-04, H-08, H-19, C5) changed;
general, managed care and bank are byte-identical. See `scripts/code_stage3_2026-10-20.md`.
