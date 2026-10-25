import sys, json
sys.path.insert(0, '.')
from src.db import get_supabase_client
from src.etl.db_io import FactSetDb
from src.ai.db_stores import DbAssessmentStore, DbAiItemStore
from src.pipeline import scoring as S
c = get_supabase_client()
t = sys.argv[1]
prof = c.table('companies').select('profile').eq('symbol', t).execute().data[0]['profile']
out = S.score_company(t, prof, FactSetDb(c, k5b_matched=None), DbAssessmentStore(c), DbAiItemStore(c), results_dir=__import__('pathlib').Path('scripts/output_k6c/try'))
print(out.status, out.engine, out.detail[:300], 'ai_pending', out.ai_pending)
if out.result:
    bq = out.result['buffett_quality']; gq = out.result['graham_quality']
    print('buffett', bq['score'], bq['range_min'], bq['range_max'], bq['status'], '| graham', gq['score'])
    ref = json.load(open(f'scripts/output_k5c/golden/{out.engine}/{t}.json', encoding='utf-8')) if __import__('os').path.exists(f'scripts/output_k5c/golden/{out.engine}/{t}.json') else None
    if ref:
        print('K5c golden: buffett', ref['buffett_quality']['score'], ref['buffett_quality']['range_min'], ref['buffett_quality']['range_max'], '| graham', ref['graham_quality']['score'])
