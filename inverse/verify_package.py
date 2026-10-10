"""Verify every search summary and deterministically replay a stratified subset."""
import gzip,json
from copy import deepcopy
from concurrent.futures import ProcessPoolExecutor
from study import INPUT,OUT,TOLERANCE,TARGETS,digest,write_json,evaluate,audit
from replay import replay
from verify import algorithm_checks

def numerical_audit_fixture():
 job=next(j for j in json.loads((INPUT/'jobs.json').read_text()) if j['job_id']=='c71d05c82b238a0f34c0')
 with gzip.open(INPUT/(job['template']+'.json.gz'),'rt') as f:base=json.load(f)
 with gzip.open(OUT/'jobs'/('c71d05c82b238a0f34c0.probes.json.gz'),'rt') as f:probes=json.load(f)
 sample=max(probes,key=lambda r:r['maximum_arithmetic_error'])
 _,result,_=evaluate(base,job,sample['coordinate'])
 corrupted=deepcopy(result)
 trade=next(e for e in corrupted.ledger if e['action']=='purchase_bitcoin')
 trade['after']['cash_usd']+=1.0
 try:audit(corrupted)
 except AssertionError:return {'large_balance_roundoff_case_passes':True,'one_dollar_purchase_error_rejected':True}
 raise AssertionError('Independent purchase audit accepted a one-dollar error')

def main():
 jobs=json.loads((INPUT/'jobs.json').read_text());total=checks=0;maxerr=0.;templates=set();replays=[];covered=set()
 for j in jobs:
  p=OUT/'jobs'/j['job_id'];s=json.loads(p.with_suffix('.json').read_text())
  with gzip.open(p.with_suffix('.probes.json.gz'),'rt') as f:probes=json.load(f)
  points={r['coordinate']:r for r in probes};total+=len(points)
  for r in probes:
   assert r['funded']==bool(r['payments'] and r['reserve_compliant'])
   assert r['common_return'] is None or r['payments']
   for t in ('nominal_value','annual_5pct','bitcoin_per_share'):assert not r[t] or r['funded']
   if j['axis']=='sale_authority':assert r['general_use_sale_gross_usd']<=r['coordinate']+.001
   checks+=r['independent_checks'];maxerr=max(maxerr,r['maximum_arithmetic_error'])
  for t in s['search_summary']:
   passing=[x for x,r in points.items() if r[t['target']]]
   assert t['lowest_feasible_tested']==(min(passing) if passing else None)
   for edge in t['transitions']:
    assert points[edge['left']][t['target']]!=points[edge['right']][t['target']]
    assert edge['right']-edge['left']<=TOLERANCE[j['axis']]+1e-6
  if j['template'] not in templates:
   with gzip.open(INPUT/(j['template']+'.json.gz'),'rt') as f:raw=json.load(f)
   assert digest(raw)==j['template'];templates.add(j['template'])
  group=(j['axis'],j['permission'],j['policy'],j['regime'],j.get('future_strc_rate'),j.get('strc_scale'))
  if group not in covered or int(j['job_id'][:8],16)%20==0:
   replays.append(j['job_id']);covered.add(group)
 with ProcessPoolExecutor(max_workers=4) as pool:verified=list(pool.map(replay,replays))
 result=dict(jobs=len(jobs),evaluations=total,source_templates=len(templates),independent_economic_checks=checks,
  maximum_arithmetic_residual=maxerr,exact_recipe_replays=len(verified),strata_replayed=len(covered),
  all_targets_consistent=True,all_observed_transitions_bracketed=True,all_general_sale_budgets_respected=True,
  all_source_hashes_verified=True,search_algorithm_fixtures=algorithm_checks(),numerical_audit_fixture=numerical_audit_fixture(),
  builder_verification=json.loads((OUT/'builder_verification.json').read_text()))
 write_json(OUT/'verification.json',result);write_json(OUT/'recipe_replays.json',verified)
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
