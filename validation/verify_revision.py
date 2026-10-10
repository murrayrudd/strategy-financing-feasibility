"""Check revised record integrity, independent economics, settlement and causality."""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import gzip,hashlib,json,sys,math
import pandas as pd
R=Path(__file__).parent;O=R/'results';sys.path.insert(0,str(R.parent/'research/legacy_engine'))
from treasury_company.market_io import run_configuration
from check_financing import audit
from settlement_calendar import compile_settlement

# A cash-only commitment cannot spend a contemporaneous unsettled placement.
with gzip.open(O/'scenario_archives/2022-05-01.jsonl.gz','rt') as f:base=json.loads(next(f))
c=deepcopy(base['result']['configuration']);c['engine_version']='0.6.0';c['configuration_id']='cash_settlement_fixture';c['path']=c['path'][:1]
c['opening'].update(cash_usd=0,treasuries_usd=0,restricted_cash_usd=0,reserve_designation_usd=0)
c['policy'].update(purchase_bitcoin=False,sell_btc_for_funding=False,refill_reserve_floor=False,common_issue_mode='liquidity')
for p in [c['initial_point']]+c['path']:p.update(reserve_floor_usd=0,allow_general_use_of_reserve=True,common_program_target_gross_usd=0,strc_issue_target_gross_usd=0)
a=run_configuration(c);assert a.complete
c['policy']['equity_settlement_lag_business_days']=1;b=run_configuration(c)
assert not b.complete and b.failure['cash_gap_usd']>50e6 and len(b.pending_placements)==1
assert b.failure['diagnostics']['cash_available_usd']==0
assert not any(e['action']=='issue_common_atm' for e in b.ledger)
assert math.isclose(b.pending_placements[0]['net_usd'],b.failure['cash_gap_usd'],abs_tol=1e-5)

# Perturb only future prices and access. Earlier prefunding decisions cannot change.
z=compile_settlement(base['result']['configuration'],True);a=run_configuration(z)
cut=next(d['date'] for d in a.financing_decisions if d['common_executed_gross_usd'] or d['strc_executed_gross_usd'])
y=deepcopy(z)
for p in y['path']:
 if p['date']>cut:p['btc_price_usd']*=.7;p['capacity_multiplier']=0
b=run_configuration(y)
assert [d for d in a.financing_decisions if d['date']<=cut]==[d for d in b.financing_decisions if d['date']<=cut]

hashes=checks=replays=0;maxerr=0;patterns=set();ids=[]
for filename,summary in [('revision_records.jsonl.gz','revision_runs.csv'),('preferred_allocation_records.jsonl.gz','preferred_allocation_runs.csv')]:
 rows=pd.read_csv(O/summary).set_index('id')
 with gzip.open(O/filename,'rt') as src:
  for line in src:
   r=json.loads(line);rr=r['result'];row=rows.loc[r['id']]
   assert hashlib.sha256(line.rstrip('\n').encode()).hexdigest()==row.record_sha256;hashes+=1
   aa=audit(SimpleNamespace(**rr));checks+=aa['independent_economic_checks'];maxerr=max(maxerr,aa['maximum_absolute_error'])
   if not rr['complete']:assert r['metrics']['equity_return'] is None
   if rr['configuration']['policy'].get('equity_settlement_lag_business_days',0):
    if rr['complete']:assert not rr['pending_placements']
    for e in rr['ledger']:
     if e['action'] in ['issue_common_atm','issue_strc']:assert e['date']==e['details']['settlement_date']>e['details']['trade_date']
   key=(r['variant'],bool(rr['complete']))
   if key not in patterns:
    assert run_configuration(rr).to_dict()==rr,(r['id'],'replay differs');patterns.add(key);ids.append(r['id']);replays+=1
 print(filename,hashes,flush=True)
result={'retained_revision_records':hashes,'record_hashes_verified':hashes,'independent_economic_checks':checks,'maximum_absolute_error':maxerr,
 'exact_replays':replays,'replayed_ids':ids,'unsettled_proceeds_cash_fixture_passed':True,'future_price_and_access_prefix_invariance_passed':True,'prefix_cutoff':cut}
(O/'revision_verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
