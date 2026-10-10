"""Targeted structural controls selected after the historical validation.

These are local sensitivity checks, not a second search for a best model.
"""
from pathlib import Path
from copy import deepcopy
import gzip,json,itertools,hashlib
import pandas as pd
from scenario_study import build,evaluate,windows,extract_prices,START,END
R=Path(__file__).parent;O=R/'results'
rows=[]
with gzip.open(O/'supplemental_records.jsonl.gz','wt',compresslevel=3) as out:
 for info,prices in windows(extract_prices()):
  win=info['window_id']
  if win not in ['2022-05-01','2023-01-01']:continue
  cases=[]
  # Four declared corners around the main 65%, 3-year reference.
  for (vol,hor),prem,pol,reg in itertools.product([(.35,1.),(.35,5.),(1.,1.),(1.,5.)],['compression','persistence','expansion'],['reference','adaptive','principal_buffer'],['open','drawdown_closure']):
   cases.append(('valuation_reference',vol,hor,prem,pol,reg,None))
  if win=='2022-05-01':
   for kind,prem,pol,reg in itertools.product(['legacy_multiple_access_gate','scheduled_issuance_only','general_sale_permission'],['compression','persistence','expansion'],['reference','adaptive','principal_buffer'],['open','drawdown_closure']):
    cases.append((kind,.65,3.,prem,pol,reg,None))
  for kind,vol,hor,prem,pol,reg,_ in cases:
   cfg=build(prices,pol,prem,reg,vol,hor)
   if kind=='legacy_multiple_access_gate':cfg['policy']['common_access_min_multiple']=1.
   if kind=='scheduled_issuance_only':cfg['policy']['common_fund_cash_shortfalls']=False
   if kind=='general_sale_permission':
    for point in [cfg['initial_point']]+cfg['path']:point['btc_general_use_gross_limit_usd']=2e9
   cfg['metadata']['supplemental_control']={'kind':kind,'volatility':vol,'reference_horizon_years':hor,'interpretation':'The explicitly changed numeric input supersedes main-study metadata for this local control.'}
   ident='_'.join([kind,win,str(vol),str(hor),prem,pol,reg]);row,record=evaluate(cfg,prices,ident)
   row.update(control=kind,window=win,volatility=vol,reference_horizon_years=hor,premium=prem,policy=pol,regime=reg,shape='historical')
   enc=json.dumps(record,separators=(',',':'),allow_nan=False);row['record_sha256']=hashlib.sha256(enc.encode()).hexdigest();out.write(enc+'\n');rows.append(row)
  print(win,len(rows),flush=True)
pd.DataFrame(rows).to_csv(O/'supplemental_runs.csv',index=False)
print('Supplemental controls complete',len(rows),flush=True)
