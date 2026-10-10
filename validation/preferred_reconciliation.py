"""Source-linked preferred checks, rounding-allocation bounds, and retained evidence.

These are filing consistency and contract-conformance tests, not a reconstructed
transaction-by-transaction preferred trading history.
"""
from pathlib import Path
from copy import deepcopy
import gzip,hashlib,json,sys
from lxml import html
import pandas as pd
R=Path(__file__).parent;O=R/'results';sys.path.insert(0,str(R.parent/'research/legacy_engine'))
from treasury_company.market_io import run_configuration
from revision_controls import run
SOURCE='https://www.sec.gov/Archives/edgar/data/1050446/000105044626000044/mstr-20260630.htm'

def main():
 root=html.fromstring((R/'sources/2026-06-30_10q.html').read_bytes());tables=[' '.join(t.text_content().split()) for t in root.xpath('//table')]
 evidence=[]
 def source_table(marker,locator):
  i=next(i for i,t in enumerate(tables) if marker in t)
  evidence.append({'source':SOURCE,'local_path':'validation/sources/2026-06-30_10q.html','table_index_zero_based':i,'locator':locator,'text':tables[i]})
  return tables[i]
 equity=source_table('75,346','Statement of changes in mezzanine and stockholders equity, six months ended June 30, 2026')
 dividends=source_table('64,198','Note 10, cash dividends paid by preferred class, six months ended June 30, 2026')
 balance=source_table('Preferred dividends payable155,157','Balance sheet, preferred dividends payable')
 assert all(x in equity for x in ['78,183','153,529','6,919,514','7,521,381','14,440,895','758,224'])
 assert all(x in dividends for x in ['394,295','44,478','56,083','70,121','629,175'])
 checks=[]
 def check(label,computed,reported,tolerance,classification,locator):
  checks.append(dict(label=label,computed=computed,reported=reported,residual=computed-reported,tolerance=tolerance,passes=abs(computed-reported)<=tolerance,classification=classification,source_locator=locator))
 check('Preferred shares, H1 roll-forward (shares)',78183000+75346000,153529000,0,'reported accounting bridge','Equity statement')
 check('Preferred carrying value, H1 roll-forward (USD)',6919514000+7521381000,14440895000,0,'reported accounting bridge','Equity statement')
 paid=[64198000,394295000,44478000,56083000,70121000]
 check('Preferred class cash distributions sum (USD)',sum(paid),629175000,0,'reported accounting bridge','Note 10, six-month cash dividends paid')
 check('Preferred payable from declared less paid (USD)',27121000+758224000-629175000,155157000,0,'unresolved cross-statement bridge','Balance sheet; equity statement; cash flow statement')
 with gzip.open(O/'scenario_archives/2022-05-01.jsonl.gz','rt') as f:base=json.loads(next(f))
 c=base['result']['configuration'];payments=[p for p in c['payments'] if p['claim_id']=='STRC']
 shares=c['opening']['strc_shares'];computed=[shares*.479166667,shares*100*.12/24,shares*100*.12/24]
 for i,p in enumerate(payments[:3]):check(p['id']+' (USD)',p['amount_native'],computed[i],1e-5,'source-anchored declared payment','June 15 Form 8-K and 10-Q Note 12')
 assert [p['payment_date'] for p in payments[:3]]==['2026-07-15','2026-07-31','2026-08-17']
 check('Three declared STRC payments versus aggregate payable (USD)',sum(computed),155157000,500,'inferred allocation within reporting precision','Balance sheet; June 15 Form 8-K; Note 12')
 credit=sum(p['opening_credit_native'] for p in payments)
 claim=next(x for x in c['opening']['claims'] if x['id']=='STRC')
 check('Opening STRC credits recognized once (USD)',credit,claim['accrued_native'],1e-5,'implementation identity','Payments and opening claim')
 check('Payable allocation plus retained rounding remainder (USD)',credit+c['opening']['unallocated_payable_usd'],155157000,1e-5,'implementation identity','Opening state')
 # Cash and preference effects of a specified par issue; fees/rate/reserve length
 # are scenario assumptions, while shares, full-period day-count and payment
 # calendar are checked against the certificate definitions.
 rr=base['result'];issue=next(e for e in rr['ledger'] if e['action']=='issue_strc')
 check('Example par issuance: net proceeds (USD)',issue['balances']['cash_usd'],400e6*(1-.01),1e-5,'conditional mechanics','Scenario 400m gross at par, 1% fee')
 check('Example par issuance: shares',issue['balances']['strc_shares'],4e6,1e-5,'conditional mechanics','Scenario 400m gross / 100')
 check('Example par issuance: preference (USD)',issue['face_changes_native']['STRC'],400e6,1e-5,'conditional mechanics','Certificate stated amount; scenario par preference')
 lot=[p for p in rr['generated_payments'] if p['id'].startswith('strc_lot_1_')]
 assert lot[0]['accrual_start']==issue['date'] and lot[0]['payment_date']>issue['date']
 check('Full semimonthly new-lot distribution (USD)',lot[0]['amount_native'],4e6*100*.12*15/360,1e-5,'contract formula at scenario rate','STRC certificate section 5(a), 30/360 full-period convention')
 first_dec=next(d for d in rr['financing_decisions'] if d['date']==issue['date'])
 source_point=next(p for p in c['path'] if p['date']==issue['date'])
 check('First new-lot reserve increment (USD)',first_dec['effective_reserve_floor_usd']-source_point['reserve_floor_usd'],48e6,1e-5,'board/scenario reserve rule','12-month increment at supplied 12% rate')
 assert all(x['passes'] for x in checks if x['classification']!='unresolved cross-statement bridge')
 rows=[]
 with gzip.open(O/'preferred_allocation_records.partial','wt',compresslevel=3) as stream,gzip.open(O/'scenario_archives/2022-05-01.jsonl.gz','rt') as src:
  for line in src:
   base=json.loads(line)
   for target in ['STRC','STRF']:
    z=deepcopy(base['result']['configuration']);residual=z['opening']['unallocated_payable_usd'];assert 0<residual<500
    z['opening']['unallocated_payable_usd']=0
    claim=next(x for x in z['opening']['claims'] if x['id']==target);claim['accrued_native']=claim.get('accrued_native',0)+residual
    pay=next(p for p in z['payments'] if p['claim_id']==target and not p.get('opening_credit_native',0));pay['opening_credit_native']=residual
    variant='rounding_credit_'+target
    z['metadata']['allocation_sensitivity']='Assign only the 248.819 USD rounding remainder to '+pay['id']+'; preserve total opening claims and every cash payment'
    run(z,variant+'_'+base['id'],base,variant,stream,rows)
 (O/'preferred_allocation_records.partial').replace(O/'preferred_allocation_records.jsonl.gz')
 df=pd.DataFrame(rows);df.to_csv(O/'preferred_allocation_runs.csv',index=False)
 baseline=pd.read_csv(O/'scenario_runs.csv').set_index('id')
 changes=[]
 for r in rows:
  b=baseline.loc[r['base_id']]
  changes.append({'id':r['id'],'funding_changed':bool(r['funded']!=b.funded),'return_difference':r['equity_return']-b['return'] if r['funded'] and b.funded else None})
 changes=pd.DataFrame(changes)
 manifest=[]
 for name in ['2026-06-30_10q.html','2026-06-15_strc_transition.html','2026-06-15_strc_certificate.html','2026-03-23_sales_agreement.html']:
  p=R/'sources'/name;manifest.append({'file':str(p.relative_to(R.parent)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 result={'checks':checks,'source_evidence':evidence,'source_files':manifest,
  'allocation_controls':{'n':len(rows),'maximum_reallocated_usd':residual,'funding_switches':int(changes.funding_changed.sum()),'maximum_absolute_return_difference':float(changes.return_difference.abs().max()),'cash_schedule_changed':False},
  'boundaries':['No independent daily preferred issuance history is reconstructed. Filing bridges are accounting consistency checks.','Full-period STRC cash amounts use 30/360. Interim uncredited accrual is linearly interpolated across actual elapsed days in the valuation ledger.','New STRC delivery is restricted to regular business-day record dates; security-specific irregular first-dividend terms are outside this route.','Future cash declarations, fixed 12% rate, par execution, fees and reserve months remain scenario assumptions.','The 1.013m payable bridge and 42.167m Bitcoin-sale bridge remain unresolved; neither is injected as a cash shock.','The rounding-allocation control does not establish that the entire aggregate payable is independently identified by instrument.']}
 (O/'preferred_reconciliation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'checks':len(checks),'allocation_controls':result['allocation_controls']},indent=2))
if __name__=='__main__':main()
