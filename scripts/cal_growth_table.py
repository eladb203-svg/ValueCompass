"""Item 6: classification table (a/b/c) of the 44 companies that move by more than 2 points under growth_window_10y."""
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
it = json.load(open("scripts/state/cal_movers_items.json", encoding="utf-8"))
# class, cause (event / years). b = material business change (event named from general knowledge, NOT yet checked against a filing quote); a = abnormal period inside the 5y window
C = {
"ADI":("b","[relabelled b 2026-11-05: large acquisition] FY21-22 start of window is the post-COVID chip peak; EPS/FCF 5y start avg high vs 10y start (FY16-18) low base; FY24 dip is the cycle. (Acquisition of Maxim 2021 also lifts revenue: partial b.)"),
"AFL":("a","5y window starts FY21-22 on a 2021 EPS peak; 10y steady 9-10% EPS growth."),
"AIG":("b","Corebridge deconsolidation FY22-24: revenue 49.9bn->29.2bn; EPS series FY16-22 swings (-6.5 .. +13) from hurricane/reserve losses. 10y mixes a different, larger company."),
"ALL":("a","EPS FY20-22 swings (5.0, -5.1, -1.2) from the 2022 catastrophe/inflation year; 5y start sits in the trough/peak pair."),
"AMT":("b","[relabelled b 2026-11-05: large acquisition] EPS FY21-22 start vs FY16-18 base; 5y EPS growth -4% only because FY24 EPS dip (7.4) from a one-off impairment year."),
"BOKF":("a","Rate cycle: FY21-22 earnings on the low-rate/reserve-release peak; 10y growth 7.5%."),
"C":("a","FY17 tax-reform charge and FY22 peak; 5y EPS start avg 4.7+10.1 vs end 7.0 - rate cycle and one-offs."),
"CI":("b","Express Scripts acquisition (Dec 2018): revenue 48.7bn -> 153.6bn in one year; 10y revenue CAGR 27.6% is M&A, not organic. 5y window (FY21+) excludes it."),
"CNC":("b","Health Net (2016) and WellCare (Jan 2020) acquisitions; revenue 60bn->111bn. FY25 EPS -13.5 is a one-off loss year in the 5y end."),
"DLR":("b","Interxion acquisition (2020) lifts revenue 3.2->3.9bn; EPS 10y 4.2% vs 5y 8.4% - 5y reflects the larger company."),
"ELV":("a","EPS 5y flat (FY21-22 peak vs FY24-25 fall on Medicaid cost trend); 10y trend is a smooth 10%. FCF FY21 9.7bn is a one-off timing peak."),
"EPR":("a","COVID FY20 (EPS 0.58) sits at the start of the 5y window region; 10y shows the true slower trend."),
"EQR":("a","EPS FY21-22 (2.5-3.0) start from gain-on-sale distorted years; 10y gives 2.9%."),
"EXR":("b","Life Storage merger (Jul 2023): revenue 1.9->2.6->3.3bn. EPS series has 3 missing early years (data gap, not a wrong value)."),
"FHN":("b","IBERIABANK acquisition (Jul 2020): revenue 1.9bn->3.2bn; 10y 12% is partly M&A."),
"GS":("a","FY21 record IB year (EPS 59) opens the 5y window; 10y first-3 vs last-3 smooths it."),
"HD":("b","[relabelled b 2026-11-05: large acquisition] FY21-22 pandemic-demand peak at the start of the 5y window; 10y 9.5% vs 5y -3%."),
"HST":("a","COVID FY20 revenue 1.6bn (from 5.4bn) just before the 5y window: 5y 'recovery growth' 20% is a rebound, 10y 0.7% is the real trend."),
"KHC":("b","[relabelled b 2026-11-05: large acquisition] Impairment years (FY18 EPS -8.4, FY25 -4.9) drive the series; no sustainable base in either window (no growth rate in either)."),
"KR":("a","FY17 and FY21-22 one-off gains (FCF 1.2bn / 3.9bn); EPS FY25 1.54 from impairment. 5y start/end ratios are dominated by single years."),
"LNC":("a","Annuity/derivative-mark volatility (EPS 19.96 .. -4.92); FY25 recovery. Revenue FY16 missing (data gap, not a wrong value)."),
"MAA":("a","FY21-22 start vs FY25 trough; only 9 years of data."),
"MOH":("b","Acquisitions: Magellan Complete Care (2022), ConnectiCare (2022); revenue 17.8->45bn. FY25 FCF/EPS fall is a one-off year. EPS 10y 52.9% is from a near-zero FY17-18 base."),
"NKE":("a","FY21 post-COVID rebound opens the 5y window; FY24-25 downturn at the end. 10y smooths the cycle."),
"NUE":("a","FY21-22 steel-price super-cycle (EPS 23-29) opens the 5y window; 10y 13.5%."),
"OHI":("a","COVID years FY20-22 (EPS 1.96-1.99); 5y start low in 5y/10y differs by base."),
"ONB":("b","First Midwest merger (Apr 2022): revenue 0.81bn->1.7bn. The 5y window starts at the merger year."),
"ORI":("a","FY21 peak EPS (5.05) at the start of the 5y window; 10y 9.6%."),
"PG":("a","FY17-19 impairment/divestiture one-offs (Gillette impairment FY19, brand sale FY17) depress the 10y base; effect small (3.9% vs 8.7%)."),
"PSA":("a","Acquisition of Simply Self Storage (2023) is small; EPS FY21-22 step-up; cycle."),
"RF":("a","FY21-22 low-rate/reserve-release peak (EPS 2.49/2.28)."),
"RLI":("a","FY21 special dividend/investment-gain year (EPS 6.37) in the 5y window start."),
"RNR":("b","Validus (Nov 2018) and Tokio Millennium Re (2019) acquisitions; revenue 1.6bn->11.7bn. EPS swings from catastrophe years."),
"SIGI":("a","FY21-22 EPS spike vs trough; growth is smooth over 10y."),
"SJM":("b","[relabelled b 2026-11-05: large acquisition] Impairment years FY19-24 (EPS -11.6, -0.9); FCF dip FY22-24. (Hostess 2023 acquisition adds a small b.)"),
"SLG":("a","COVID/office downturn plus FY22-23 impairments (EPS 2.5, -1.1); 5y 21% is the rebound from FY23."),
"TFC":("b","BB&T/SunTrust merger (Dec 2019): revenue 12.6->22.7bn; FY23 revenue 13.3bn = securities-repositioning loss."),
"TGT":("a","FY21 pandemic peak opens the 5y window; FY23 loss year (-1.5bn FCF/ -.). 10y 7.6% vs 5y -5.4%."),
"TXN":("a","FY21-22 cycle peak opens the 5y window; FY24-25 FCF collapse from the capex programme (an investment cycle, not a data issue)."),
"UNH":("a","FY24-25 Optum/medical-cost year hits the end of both windows; difference is the early years (EPS 7->14 ramp) vs 2021-22. (Change Healthcare 2022 acquisition is small vs revenue.)"),
"VTR":("a","COVID FY20-21 dip (EPS 2.1-2.2) at the start of the 5y window: rebound growth 14%, 10y -2.6%."),
"WAL":("a","FY21 revenue/EPS peak at 5y start; rate cycle."),
"WFC":("a","FY20 EPS 0.43 and FY22 litigation/reserve charges; 5y 11.7% is rebound from a conduct-penalty year."),
"ZION":("a","Rate cycle: FY21-22 low-rate peak at the start of the 5y window."),
}
assert len(C) == 44, len(C)
rows = []
for t, (k, why) in C.items():
    o = it[t]; d = o["after"] - o["before"]
    moved = {a: round(v[1][1] - v[0][1], 2) for a, v in o["items"].items() if abs(v[1][1] - v[0][1]) > 0.001}
    rows.append((t, o["profile"], k, round(o["before"], 1), round(o["after"], 1), round(d, 1), moved, why))
if __name__ == "__main__":
    print("| Ticker | Profile | Class | Buffett off -> on | Delta | Sub-items moved (points) | Cause (years / event) |\n|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: (x[2], x[1], x[0])):
        print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} -> {r[4]} | {r[5]:+.1f} | {', '.join(f'{a} {v:+}' for a, v in r[6].items())} | {r[7]} |")
    print("\nBY CLASS x PROFILE (n, up, down, mean delta)")
    import collections, statistics as st
    g = collections.defaultdict(list)
    for r in rows: g[(r[2], r[1])].append(r[5]); g[(r[2], "ALL")].append(r[5]); g[("all", r[1])].append(r[5]); g[("all", "ALL")].append(r[5])
    for k in sorted(g):
        v = g[k]; print(k, len(v), sum(1 for x in v if x > 0), sum(1 for x in v if x < 0), round(st.mean(v), 2))
