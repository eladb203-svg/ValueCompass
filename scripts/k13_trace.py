import sys, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import vc
r = vc.make_runner(5)
t = sys.argv[1]
co = r.companies.get_by_symbol(t, "US")
try:
    print(r.exec_extract({"company_id": co["id"], "priority": 2, "payload": {}}))
except Exception:
    traceback.print_exc()
