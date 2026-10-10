"""Integrity and targeted independent economic/replay checks for the paper."""
from pathlib import Path
import gzip,json,hashlib,math,sys
from types import SimpleNamespace
import pandas as pd
R=Path(__file__).parent;ROOT=R.parent;O=R/'results';sys.path.insert(0,str(ROOT/'research/legacy_engine'))
from treasury_company.market_io import run_configuration
from check_financing import audit
summary=pd.read_csv(O/'scenario_runs.csv').set_index('id');supp=pd.read_csv(O/'supplemental_runs.csv').set_index('id');allrows=pd.concat([summary,supp]);hashes=0;checks=0;maxerr=0;replays=0;replay_ids=[];patterns=set()
# Verify every retained record's hash and independent transaction identities.
for path in sorted((O/'scenario_archives').glob('*.jsonl.gz'))+[O/'supplemental_records.jsonl.gz']:
 with gzip.open(path,'rt') as stream:
  for line in stream:
   text=line.rstrip('\n');r=json.loads(text);rr=r['result'];row=allrows.loc[r['id']]
   assert hashlib.sha256(text.encode()).hexdigest()==row.record_sha256
   obj=SimpleNamespace(**rr);aa=audit(obj);checks+=aa['independent_economic_checks'];maxerr=max(maxerr,aa['maximum_absolute_error']);hashes+=1
   cfg=rr['configuration']
   if path.name!='supplemental_records.jsonl.gz':assert cfg['policy']['common_access_min_multiple']==0.
   ip=rr['initial_snapshot'];assert abs(ip['conditional_common_price_usd']-86.93000030517578)<1e-8
   for ss in [ip]+rr['snapshots']:
    pt=cfg['initial_point'] if ss is ip else next(p for p in cfg['path'] if p['date']==ss['date'])
    st=ss['state'];claims=sum((c['face_native']+c['accrued_native'])*pt['fx_usd_per_unit'][c['currency']] for c in st['claims'])+st['unallocated_payable_usd']
    assets=st['btc']*pt['btc_price_usd']+st['cash_usd']+st['treasuries_usd']+st['restricted_cash_usd']+pt['net_operating_value_usd']
    assert math.isclose(ss['backing_usd'],assets-claims,abs_tol=1e-4)
    if ss['quote_defined']:assert math.isclose(ss['conditional_common_price_usd'],ss['market_multiple']*ss['reference_common_value_usd']/st['common_shares'],rel_tol=1e-12)
   if not rr['complete']:assert r['metrics']['equity_return'] is None and pd.isna(row['return'])
   # Full varied replay: one window covers all 54 main factor combinations.
   selected=(str(row.window)=='2022-05-01' and path.name!='supplemental_records.jsonl.gz')
   # Each supplemental control/volatility/horizon gets one exact replay.
   if path.name=='supplemental_records.jsonl.gz':
    k=(row.control,float(row.volatility),float(row.reference_horizon_years))
    if k not in patterns:selected=True;patterns.add(k)
   if selected:
    recomputed=run_configuration(rr).to_dict();assert recomputed==rr,(r['id'],'nonidentical replay');replays+=1;replay_ids.append(r['id'])
 print(path.name,'verified',hashes,flush=True)
assert hashes==2844
result=dict(retained_records=hashes,all_record_hashes_verified=True,independent_economic_checks=checks,maximum_independent_absolute_error=maxerr,exact_full_replays=replays,replay_ids=replay_ids,all_opening_quotes_verified=True,all_snapshot_backing_identities_verified=True,all_failed_paths_have_no_terminal_return=True,all_main_runs_remove_multiplier_access_gate=True,main_runs=2646,supplemental_runs=198)
(O/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='replay_ids'},indent=2))
