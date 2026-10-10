"""Rebuild a reported inverse-search witness from its frozen source and recipe."""
import argparse,gzip,json
from pathlib import Path
from study import INPUT,OUT,configuration,evaluate,daily_marks,endpoint_obligations,digest

def replay(job_id,coordinate=None,out=None):
 job=next(j for j in json.loads((INPUT/'jobs.json').read_text()) if j['job_id']==job_id)
 stem=OUT/'jobs'/job_id
 summary=json.loads(stem.with_suffix('.json').read_text())
 with gzip.open(stem.with_suffix('.probes.json.gz'),'rt') as f:probes=json.load(f)
 if coordinate is None:
  passing=[s['lowest_feasible_tested'] for s in summary['search_summary'] if s['target']=='nominal_value' and s['lowest_feasible_tested'] is not None]
  if not passing:passing=[s['lowest_feasible_tested'] for s in summary['search_summary'] if s['target']=='funded' and s['lowest_feasible_tested'] is not None]
  coordinate=passing[0] if passing else probes[0]['coordinate']
 expected=next(r for r in probes if r['coordinate']==coordinate)
 with gzip.open(INPUT/(job['template']+'.json.gz'),'rt') as f:base=json.load(f)
 assert digest(base)==job['template']
 row,result,prices=evaluate(base,job,coordinate)
 assert row['configuration_sha256']==expected['configuration_sha256']
 assert row['result_sha256']==expected['result_sha256']
 if out:
  dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
  data=dict(row=row,result=result.to_dict(),daily_marks=daily_marks(result,prices),endpoint_obligations=endpoint_obligations(result))
  with gzip.open(dest,'wt') as f:json.dump(data,f,separators=(',',':'),allow_nan=False)
 return dict(job_id=job_id,coordinate=coordinate,result_sha256=row['result_sha256'],exact_replay=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('job_id');p.add_argument('--coordinate',type=float);p.add_argument('--out');a=p.parse_args();print(json.dumps(replay(a.job_id,a.coordinate,a.out),indent=2))
