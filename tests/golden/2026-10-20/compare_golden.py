"""Compare two golden trees (normalised JSON per company): .venv/Scripts/python compare_golden.py <dirA> <dirB> [--max=40]

Exact comparison, except the real-estate captured ``inputs.tag_log`` (only the tag text of cells that have a value is compared: the fact layer
keeps the tag text, not the provider's filed / form / value bookkeeping nor the reason text of a missing value)."""
import json
import sys
from pathlib import Path


def walk(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append((path + "/" + str(k), "missing in " + ("A" if k not in a else "B"), None))
            else:
                walk(a[k], b[k], path + "/" + str(k), out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((path, f"len {len(a)} != {len(b)}", None))
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append((path, a, b))


def strip_tag_meta(j):
    """tag_log of the captured inputs: tag text only, and only where the series has a value (a missing value has no fact row, so the provider's
    reason text for it - e.g. 'set missing: ...' - is not carried; the engines' results do not depend on it)."""
    inp = j.get("inputs")
    if inp and inp.get("tag_log"):
        fy, f = inp["fy"], inp["f"]
        inp["tag_log"] = {fld: {l: {"tag": (e or {}).get("tag")} for l, e in yrs.items()
                                if fld not in f or f[fld][fy.index(l)] is not None}
                          for fld, yrs in inp["tag_log"].items()}
    return j


def main(argv):
    mx = 40
    args = []
    for a in argv:
        if a.startswith("--max="):
            mx = int(a[6:])
        else:
            args.append(a)
    A, B = Path(args[0]), Path(args[1])
    files = sorted(p.relative_to(A) for p in A.rglob("*.json"))
    other = sorted(p.relative_to(B) for p in B.rglob("*.json"))
    bad, total = [], 0
    if files != other:
        print("file sets differ:", sorted(set(files) ^ set(other))[:10])
        bad.append("file set")
    for rel in files:
        if rel not in other:
            continue
        a = strip_tag_meta(json.loads((A / rel).read_text(encoding="utf-8")))
        b = strip_tag_meta(json.loads((B / rel).read_text(encoding="utf-8")))
        diffs: list = []
        walk(a, b, "", diffs)
        total += 1
        if diffs:
            bad.append(str(rel))
            print(f"DIFF {rel}: {len(diffs)} differences")
            for d in diffs[:mx]:
                print("   ", d[0], "|", str(d[1])[:90], "|", str(d[2])[:90])
    print(f"compared {total} files; files with differences: {len([x for x in bad if x != 'file set'])}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
