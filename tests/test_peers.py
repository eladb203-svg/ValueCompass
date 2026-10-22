"""Code stage K5c: peer group and percentiles."""
from src.scoring import peers as P


def rec(t, profile="STANDARD", industry="Software", b=50.0, g=60.0, **metrics):
    base = {"revenue": None, "net_income": None, "eps": None, "roe": None, "fcf": None, "leverage": None}
    base.update(metrics)
    return {"ticker": t, "profile": profile, "industry": industry, "buffett": {"score": b, "range_min": b, "range_max": b, "status": "full"},
            "graham": {"score": g, "range_min": g, "range_max": g, "status": "full"}, "metrics": base}


def test_full_group_is_same_profile_and_industry_without_the_company_itself():
    R = [rec(f"S{i}") for i in range(6)] + [rec("O1", industry="Other"), rec("B1", profile="BANK", industry="Software")]
    g = P.peer_group(R[0], R)
    assert g["ids"] == ["S1", "S2", "S3", "S4", "S5"] and g["n"] == 5 and not g["fallback"] and "industry Software" in g["definition"]


def test_fewer_than_five_peers_falls_back_to_the_profile_only_and_says_so():
    R = [rec("A"), rec("B"), rec("C"), rec("X1", industry="Other"), rec("X2", industry="Other"), rec("BK", profile="BANK")]
    g = P.peer_group(R[0], R)
    assert g["fallback"] and g["ids"] == ["B", "C", "X1", "X2"] and g["n"] == 4 and "profile only" in g["definition"]


def test_single_company_in_its_profile_has_an_empty_group_and_no_percentiles():
    R = [rec("A", profile="INSURANCE", revenue=5.0), rec("B")]
    g = P.peer_group(R[0], R)
    out = P.peer_percentiles(R[0], g, R)
    assert g["n"] == 0 and g["fallback"] and out["quality"]["buffett"]["percentile"] is None and out["metrics"]["revenue"]["percentile"] is None


def test_percentile_counts_ties_as_half_and_inverts_leverage():
    assert P.percentile(5, [1, 2, 3, 4]) == 90.0                      # 4 below, itself half: (4 + 0.5) / 5
    assert P.percentile(2, [2, 2, 2]) == 50.0                         # all equal
    assert P.percentile(None, [1, 2]) is None and P.percentile(1, [None]) is None
    assert P.percentile(1, [2, 3, 4], lower_is_better=True) == 87.5   # lowest leverage is the best
    R = [rec("A", leverage=0.1)] + [rec(f"P{i}", leverage=0.5 + i) for i in range(5)]
    out = P.peer_percentiles(R[0], P.peer_group(R[0], R), R)
    assert out["metrics"]["leverage"]["percentile"] > 90 and out["metrics"]["leverage"]["lower_is_better"]
    bank = [rec("B", profile="BANK", industry="Banks", leverage=15.0)] + [rec(f"K{i}", profile="BANK", industry="Banks", leverage=10.0 + i) for i in range(5)]
    assert P.peer_percentiles(bank[0], P.peer_group(bank[0], bank), bank)["metrics"]["leverage"]["percentile"] > 50      # CET1: higher is better


def test_a_quality_range_enters_with_its_middle_and_is_marked():
    c = rec("A")
    c["buffett"] = {"score": 70.0, "range_min": 60.0, "range_max": 80.0, "status": "full"}
    R = [c] + [rec(f"P{i}", b=40.0 + 10 * i) for i in range(5)]
    q = P.peer_percentiles(c, P.peer_group(c, R), R)["quality"]["buffett"]
    assert q["score"] == 70.0 and q["range_midpoint"] is True and q["percentile"] > 50
    c["buffett"] = {"score": 55.0, "range_min": 50.0, "range_max": 90.0, "status": "partial"}
    assert P.score_of(c["buffett"]) == (70.0, True)
    assert P.score_of({"score": 55.0, "range_min": 55.0, "range_max": 55.0}) == (55.0, False) and P.score_of(None) == (None, False)
