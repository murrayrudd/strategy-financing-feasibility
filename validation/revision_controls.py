"""Mechanism-specific revision tests; retain each full configuration and ledger."""
from pathlib import Path
from copy import deepcopy
import csv,gzip,hashlib,json,sys,time,math
import pandas as pd
R=Path(__file__).parent;O=R/'results';sys.path.insert(0,str(R.parent/'research/legacy_engine'))
from treasury_company.market_io import run_configuration
from price_interface.prices import PricePath
from price_interface.market_adapter import daily_marks,reporting_metrics,endpoint_obligations
from check_financing import audit
from settlement_calendar import compile_settlement

def run(c,ident,base,variant,stream,rows):
 c=deepcopy(c);c['configuration_id']=ident;c['engine_version']='0.6.0'
 result=run_configuration(c);aa=audit(result)
 marks=daily_marks(result,PricePath(c['metadata']['common_price_interface']['price_path']))
 metrics=reporting_metrics(result,marks,.05)
 rec={'id':ident,'base_id':base['id'],'variant':variant,'result':result.to_dict(),'daily_marks':marks,'metrics':metrics,'endpoint_obligations':endpoint_obligations(result)}
 encoded=json.dumps(rec,separators=(',',':'),allow_nan=False);stream.write(encoded+'\n')
 last=result.snapshots[-1];f=result.failure or {};bd=base['result'];bfinal=bd['snapshots'][-1]
 row=dict(id=ident,base_id=base['id'],variant=variant,record_sha256=hashlib.sha256(encoded.encode()).hexdigest(),complete=result.complete,
  funded=result.complete and result.assessment['reserve_compliant_throughout'],reserve_compliant=result.assessment['reserve_compliant_throughout'],failure_date=f.get('date'),cash_gap_usd=f.get('cash_gap_usd',0),asset_use_gap_usd=max(f.get('reserve_authorization_gap_usd',0),f.get('btc_general_use_funding_gap_usd',0)),
  baseline_funded=bd['complete'] and bd['assessment']['reserve_compliant_throughout'],baseline_complete=bd['complete'],
  equity_return=metrics['equity_return'],btc_per_share=last['btc_per_common_share'] if result.complete else None,
  common_gross=sum(e['details']['gross_usd'] for e in result.ledger if e['action']=='issue_common_atm'),
  independent_checks=aa['independent_economic_checks'],max_economic_error=aa['maximum_absolute_error'],pending_placements=len(result.pending_placements))
 for key in ['window','shape','premium','policy','regime']:
  row[key]=BASE.loc[base['id'],key]
 rows.append(row);return result

BASE=pd.read_csv(O/'scenario_runs.csv').set_index('id')
def main():
 rows=[];failures=[];fixed=[];clock=time.monotonic();lagtests=0
 with gzip.open(O/'revision_records.jsonl.gz','wt',compresslevel=3) as stream:
  for file in sorted((O/'scenario_archives').glob('*.jsonl.gz')):
   with gzip.open(file,'rt') as src:
    for line in src:
     base=json.loads(line);rr=base['result'];c=rr['configuration'];ident=base['id'];meta=BASE.loc[ident]
     if rr['failure']:
      f=rr['failure'];d=f['diagnostics'];last=rr['snapshots'][-1]
      failures.append(dict(id=ident,window=meta.window,shape=meta['shape'],premium=meta.premium,policy=meta.policy,regime=meta.regime,
       first_binding_date=f['date'],cash_gap_usd=f['cash_gap_usd'],reserve_authorization_gap_usd=f['reserve_authorization_gap_usd'],general_use_gap_usd=f['btc_general_use_funding_gap_usd'],
       **d,btc_available=last['state']['btc']-last['state']['pledged_btc'],
       general_cash_due_usd=d['cash_due_usd']-d['eligible_distributions_usd'],
       usable_for_general_cash_use_usd=max(0,d['cash_due_usd']-d['eligible_distributions_usd']-f['btc_general_use_funding_gap_usd']) if f['btc_general_use_funding_gap_usd']>0 else None,
       usable_general_basis='General funding test before distribution-restricted sale proceeds; derived only for a positive general-use gap',
       failure_class='cash_and_asset_use' if d['cash_shortage'] and d['asset_use_restriction'] else 'cash' if d['cash_shortage'] else 'asset_use_only',
       restriction_origin='Board asset-use policy; contractual payments and experiment capacity held fixed'))
      for variant in ['general_sale_2bn','reserve_general_use','both_permissions','reserve_use_no_floor']:
       z=deepcopy(c)
       for p in [z['initial_point']]+z['path']:
        if variant in ['general_sale_2bn','both_permissions']:p['btc_general_use_gross_limit_usd']=2e9
        if variant in ['reserve_general_use','both_permissions','reserve_use_no_floor']:p['allow_general_use_of_reserve']=True
        if variant=='reserve_use_no_floor':p['reserve_floor_usd']=0
       if variant=='reserve_use_no_floor':z['policy']['strc_reserve_months']=0
       z['metadata']['permission_control']=variant
       run(z,variant+'_'+ident,base,variant,stream,rows)
     if meta.window in ['2022-05-01','2023-01-01']:
      for prefund in [False,True]:
       variant='tplus1_prefunded' if prefund else 'tplus1_scheduled'
       z=compile_settlement(c,prefund);a=run(z,variant+'_'+ident,base,variant,stream,rows)
       for e in a.ledger:
        if e['action'] in ['issue_common_atm','issue_strc']:
         assert e['date']==e['details']['settlement_date']>e['details']['trade_date'];lagtests+=1
       assert a.complete is False or not a.pending_placements
     if meta.window=='2022-05-01' and meta.policy=='adaptive' and rr['complete']:
      quotes={d['date']:d['common_quote_usd'] for d in rr['financing_decisions']}
      for objective in ['both','bitcoin']:
       for scale in [.5,1.,2.]:
        z=deepcopy(c);z['policy']['common_growth_objective']=objective
        for p in z['path']:p.update(execution_common_price_usd=quotes[p['date']],policy_reference_scale=scale)
        variant=f'fixed_quote_{objective}_{scale:g}'
        a=run(z,variant+'_'+ident,base,variant,stream,rows)
        states_identical=a.complete==rr['complete'] and [p['state'] for p in a.snapshots]==[p['state'] for p in rr['snapshots']]
        # Floating-point execution market-cap multiplication can differ by <1 cent.
        max_relative=0.
        if len(a.snapshots)==len(rr['snapshots']):
         for x,y in zip(a.snapshots,rr['snapshots']):
          for key in ['cash_usd','treasuries_usd','btc','common_shares','strc_shares','reserve_designation_usd']:
           max_relative=max(max_relative,abs(x['state'][key]-y['state'][key])/max(1,abs(y['state'][key])))
        else:max_relative=None
        if objective=='bitcoin':assert a.complete and max_relative<1e-10,(ident,max_relative)
        fixed.append(dict(id=ident,objective=objective,reference_scale=scale,complete=a.complete,
          same_financial_path=bool(max_relative is not None and max_relative<1e-10),max_relative_state_difference=max_relative,
          value_screen_binding=sum(d['common_value_premium']<d['common_bitcoin_premium'] for d in a.financing_decisions if d['common_value_premium'] is not None and d['common_bitcoin_premium'] is not None)))
   print(file.stem,len(rows),round(time.monotonic()-clock,1),flush=True)
 pd.DataFrame(rows).to_csv(O/'revision_runs.csv',index=False);pd.DataFrame(failures).to_csv(O/'failure_diagnostics.csv',index=False);pd.DataFrame(fixed).to_csv(O/'fixed_quote_screen_audit.csv',index=False)
 df=pd.DataFrame(rows)
 summary={'runs':len(rows),'main_failures':len(failures),'main_cash_shortages':sum(x['cash_gap_usd']>1e-5 for x in failures),'main_sale_only':sum(x['reserve_authorization_gap_usd']<=1e-5 for x in failures),'main_reserve_and_sale':sum(x['reserve_authorization_gap_usd']>1e-5 for x in failures),
  'lagged_issuances_checked':lagtests,'independent_checks':int(df.independent_checks.sum()),'max_independent_error':float(df.max_economic_error.max()),
  'groups':df.groupby('variant').agg(n=('id','size'),complete=('complete','sum'),funded=('funded','sum'),reserve_compliant=('reserve_compliant','sum'),baseline_funded=('baseline_funded','sum'),cash_shortages=('cash_gap_usd',lambda x:int((x>1e-5).sum()))).reset_index().to_dict('records')}
 (O/'revision_summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
