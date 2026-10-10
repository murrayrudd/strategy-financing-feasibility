"""Complete-path inverse searches for treasury financing and shareholder targets.

Frozen opening and instruments; targets are evaluated after rerunning the ledger.
A bounded grid locates all observed transitions; refinement does not assume a
monotone global response or claim that an unresolved sub-grid island cannot exist.
"""
from pathlib import Path
from copy import deepcopy
from datetime import date, timedelta
import argparse, csv, gzip, hashlib, itertools, json, math, os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'validation'),str(ROOT/'research/legacy_engine')]
from treasury_company.market_io import run_configuration
from price_interface.prices import PricePath, digest
from price_interface.market_conditions import conditions
from price_interface.market_adapter import daily_marks, endpoint_obligations
from settlement_calendar import compile_settlement
from check_financing import audit

HERE=Path(__file__).resolve().parent
INPUT=HERE/'inputs';OUT=HERE/'results'
START='2026-06-30';END='2027-09-30';DAYS=(date.fromisoformat(END)-date.fromisoformat(START)).days
YEARS=DAYS/365.25
TARGETS=('payments','funded','nominal_value','annual_5pct','bitcoin_per_share')
SELECTED=('2021-11-01','2022-05-01','2023-01-01')
GRIDS={'valuation':[2**(i/4) for i in range(-12,13)],
       'bitcoin':[.1,.125,.16,.2,.25,.32,.4,.5,.63,.8,1.,1.25,1.6,2.,2.5,3.2,4.],
       'capacity':[0,.0625,.125,.1875,.25,.375,.5,.625,.75,.875,1.,1.25,1.5,1.75,2.],
       'sale_authority':[0,25e6,50e6,100e6,200e6,400e6,800e6,1.2e9,1.6e9,2e9]}
TOLERANCE={'valuation':.005,'bitcoin':.005,'capacity':.005,'sale_authority':1e6}

def write_json(p,data):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.partial');tmp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n');tmp.replace(p)
def save_config(c):
 key=digest(c);p=INPUT/(key+'.json.gz')
 if not p.exists():
  with gzip.open(p,'wt',compresslevel=6) as f:json.dump(c,f,separators=(',',':'),allow_nan=False)
 return key

def prepare():
 INPUT.mkdir(exist_ok=True);jobs=[];basis=[]
 for archive in sorted((ROOT/'validation/results/scenario_archives').glob('*.jsonl.gz')):
  with gzip.open(archive,'rt') as f:
   for line in f:
    rec=json.loads(line);ident=rec['id'];c=rec['result']['configuration']
    window=ident[:10];rest=ident[11:]
    shape='smooth_matched' if rest.startswith('smooth_matched') else 'historical'
    remain=rest[len(shape)+1:];premium=remain.split('_')[0];remain=remain[len(premium)+1:]
    policy='principal_buffer' if remain.startswith('principal_buffer') else remain.split('_')[0]
    regime=remain[len(policy)+1:]
    meta=dict(window=window,shape=shape,premium=premium,policy=policy,regime=regime,base_id=ident)
    key=None
    def add(kind,axis,permission,timing='prefunded',**extra):
     nonlocal key
     if key is None:key=save_config(c)
     j=dict(kind=kind,axis=axis,permission=permission,timing=timing,template=key,**meta,**extra)
     j['job_id']=digest(j)[:20];jobs.append(j)
    # General-sale authority required for every original stopped configuration.
    if not rec['result']['complete']:
     add('inverse','sale_authority','restricted',timing='immediate')
    # Valuation frontier on all historical windows and both shapes, reference
    # policy; adaptive comparisons on the three declared case windows.
    if premium=='persistence' and (policy=='reference' or (window in SELECTED and policy=='adaptive')):
     for permission in ('restricted','reserve_flexible'):
      add('inverse','valuation',permission)
    # Bitcoin endpoint and financing capacity inverse analyses on three windows.
    if window in SELECTED and policy in ('reference','adaptive'):
     for permission in ('restricted','reserve_flexible'):
      add('inverse','bitcoin',permission)
      add('inverse','capacity',permission)
     # Isolate new STRC availability and future distribution rate. Common
     # targets/capacity stay fixed; this is not an equal-total-budget comparison.
     for scale in (0.,.5,1.):
      for rate in (.10,.12,.14,.16):
       add('strc','none','reserve_flexible',strc_scale=scale,future_strc_rate=rate)
    if key is not None:basis.append(dict(template=key,**meta,baseline_complete=rec['result']['complete']))
 write_json(INPUT/'jobs.json',jobs);write_json(INPUT/'templates.json',basis)
 write_json(HERE/'design.json',dict(version='1.0.0',date='2026-10-08',opening=START,horizon_end=END,
  targets={'payments':'Complete the declared payment schedule under specified permissions',
   'funded':'Payments complete and reserve floor met at all corporate events',
   'nominal_value':'Funded and final common quote at least opening quote',
   'annual_5pct':'Funded and common quote return at least (1.05)^(457/365.25)-1',
   'bitcoin_per_share':'Funded and Bitcoin per basic share at least opening level'},
  grids=GRIDS,refinement_absolute_tolerances=TOLERANCE,
  inverse_procedure='Scan every grid point, refine every observed target-state transition, rerun the full corporate path at every evaluation; report all observed feasible bands and adjacent passing/failing witnesses.',
  search_interpretation='Lowest feasible tested coordinate within the declared one-dimensional domain. Interior boundaries are brackets, not proof of global minima; sub-grid islands may remain unresolved.',
  baseline='Frozen June 2026 opening and original 49 windows. Historical scenario counts are unweighted.',
  operational_timing='T+1 with advance planning for inverse valuation, Bitcoin, capacity and STRC comparisons; original immediate timing retained for attribution of the 335 baseline policy stops.',
  permissions={'restricted':'Original asset-use permissions','reserve_flexible':'General use of designated reserves allowed; original reserve floor retained'},
  valuation_axis='Terminal multiple / opening multiple, log-linear daily path; opening quote fixed; full ledger rerun.',
  bitcoin_axis='Terminal Bitcoin / opening Bitcoin; preserve historical log deviations from its endpoint-matched smooth path and tilt the trend. Recompute drawdown/volatility-dependent access.',
  capacity_axis='Multiply nominal capacities and capitalization-based capacity limits for both channels; discretionary targets and cumulative authorizations fixed.',
  sale_axis='Cumulative gross general-use Bitcoin sale authority in USD, not actual sales and not per-event authority.',
  strc_axis='0%, 50%, or 100% of new STRC discretionary targets, capacity and authorization. Existing STRC remains. Common channel unchanged. Future rate changes apply to full periods beginning August 31, 2026; declared opening distributions remain fixed.',
  primary_windows='49 monthly windows from September 2020 to September 2024 for reference valuation frontier; both shapes, three access regimes, two permission policies.',
  focused_windows=list(SELECTED),job_count=len(jobs)))
 print('Prepared',len(jobs),'jobs from',len(basis),'frozen templates',flush=True)


def configuration(base,job,x):
 c=deepcopy(base);c['configuration_id']=job['job_id']+'_'+format(x,'.12g');c['engine_version']='0.6.0'
 axis=job['axis'];points=[c['initial_point']]+c['path'];old_prices=PricePath(c['metadata']['common_price_interface']['price_path']);prices=old_prices
 if axis=='bitcoin':
  raw=old_prices.to_dict();old_end=old_prices.at(END)/old_prices.at(START)
  raw.update(kind='stylized',scenario_id='inverse_bitcoin_'+format(x,'.12g'),price_timing='scenario_input',availability_lag_days=0,interpolation='exact',max_gap_days=None)
  raw['points']=[dict(date=str(date.fromisoformat(START)+timedelta(days=i)),price_usd=old_prices.at(str(date.fromisoformat(START)+timedelta(days=i)))*(x/old_end)**(i/DAYS)) for i in range(DAYS+1)]
  raw['assumptions']=raw['assumptions']+['Historical log-path deviations retained; endpoint trend varied for inverse analysis.']
  prices=PricePath(raw);cond,check=conditions(prices,START,END,'continuation_state',job['regime'])
  for day,signal in c['metadata']['market_conditions'].items():signal['capacity_multiplier']=cond[day]['capacity_multiplier']
  c['metadata']['financing_condition_audit']=check
  for p in points:p.update(btc_price_usd=prices.at(p['date']),capacity_multiplier=cond[p['date']]['capacity_multiplier'])
  c['metadata']['common_price_interface'].update(price_path=prices.to_dict(),price_sha256=prices.sha256)
 if axis=='valuation':
  anchor=c['initial_point']['multiple']
  for day,signal in c['metadata']['market_conditions'].items():
   signal['multiple']=anchor*x**((date.fromisoformat(day)-date.fromisoformat(START)).days/DAYS)
  for p in points:p['multiple']=c['metadata']['market_conditions'][p['date']]['multiple']
  c['metadata']['valuation_scenario'].update(premium='inverse',terminal_factor=x)
 if axis=='capacity':
  for p in points:
   for k in ('common_issue_cap_gross_usd','strc_issue_cap_gross_usd'):p[k]*=x
  for k in ('common_market_cap_fraction','strc_market_cap_fraction'):
   if c['policy'].get(k) is not None:c['policy'][k]*=x
 if axis=='sale_authority':
  for p in points:p['btc_general_use_gross_limit_usd']=x
 if job['permission']=='reserve_flexible':
  for p in points:p['allow_general_use_of_reserve']=True
 if job['kind']=='strc':
  scale=job['strc_scale'];rate=job['future_strc_rate'];effective='2026-08-31'
  for p in points:
   for k in ('strc_issue_target_gross_usd','strc_issue_cap_gross_usd','strc_authorization_gross_limit_usd'):p[k]*=scale
   if p['date']>effective:p['strc_annual_rate']=rate
  for t in c['strc_terms']['templates']:
   if t['record_date']>=effective:t['annual_rate']=rate
  for p in c['payments']:
   if p['claim_id']=='STRC' and p.get('accrual_start','')>=effective:
    assert not p.get('opening_credit_native',0),'Cannot alter declared opening credit'
    p['amount_native']*=rate/.12
 c['metadata']['inverse_study']=dict(job_id=job['job_id'],axis=axis,coordinate=x,permission=job['permission'],timing=job['timing'])
 if job['timing']=='prefunded':c=compile_settlement(c,True)
 return c,prices


def evaluate(base,job,x):
 c,prices=configuration(base,job,x);result=run_configuration(c);check=audit(result)
 assert result.reconciliation['all_prefixes_reconciled']
 assert abs(result.initial_snapshot['conditional_common_price_usd']-86.93000030517578)<1e-7
 if result.complete:assert not result.pending_placements
 first=result.initial_snapshot;last=result.snapshots[-1];f=result.failure or {}
 funded=result.complete and result.assessment['reserve_compliant_throughout'];ret=result.assessment['conditional_terminal_equity_return']
 bps=last['btc_per_common_share']/first['btc_per_common_share']-1 if result.complete else None
 ledger=result.ledger
 def total(action,key):return sum(e['details'].get(key,0) for e in ledger if e['action']==action)
 cash=bool(f.get('cash_gap_usd',0)>1e-5);permission=bool(max(f.get('reserve_authorization_gap_usd',0),f.get('btc_general_use_funding_gap_usd',0))>1e-5)
 failure_class=('cash_and_permission' if cash and permission else 'cash' if cash else 'permission' if permission else 'reserve_floor' if not funded else 'none')
 row={k:job[k] for k in ('job_id','base_id','window','shape','premium','policy','regime','axis','permission','timing','kind')}
 row.update(coordinate=x,payments=result.complete,funded=funded,
  reserve_compliant=result.assessment['reserve_compliant_throughout'],nominal_value=bool(funded and ret is not None and ret>=-1e-12),
  annual_5pct=bool(funded and ret is not None and ret>=(1.05)**YEARS-1-1e-12),bitcoin_per_share=bool(funded and bps is not None and bps>=-1e-12),
  common_return=ret,bitcoin_per_share_change=bps,scheduled_bitcoin_return=prices.at(END)/prices.at(START)-1,
  terminal_multiple_factor=c['path'][-1]['multiple']/c['initial_point']['multiple'],
  failure_class=failure_class,first_stop_date=f.get('date'),cash_gap_usd=f.get('cash_gap_usd',0),
  general_use_gap_usd=f.get('btc_general_use_funding_gap_usd',0),reserve_use_gap_usd=f.get('reserve_authorization_gap_usd',0),
  common_gross_usd=total('issue_common_atm','gross_usd'),strc_gross_usd=total('issue_strc','gross_usd'),
  gross_bitcoin_sales_usd=total('sell_bitcoin_for_funding','gross_usd'),
  general_use_sale_gross_usd=total('sell_bitcoin_for_funding','general_use_net_usd')/(1-c['policy']['btc_sale_cost_rate']-c['policy']['effective_sale_tax_cash_fraction']),
  bitcoin_sold=-sum(e['balances'].get('btc',0) for e in ledger if e['action']=='sell_bitcoin_for_funding'),
  bitcoin_purchased=sum(e['balances'].get('btc',0) for e in ledger if e['action']=='purchase_bitcoin'),
  final_bitcoin=last['state']['btc'] if result.complete else None,
  common_share_growth=last['state']['common_shares']/first['state']['common_shares']-1 if result.complete else None,
  final_liquid_usd=last['liquid_assets_usd'] if result.complete else None,
  final_unreserved_liquid_usd=last['liquid_assets_usd']-last['state']['reserve_designation_usd'] if result.complete else None,
  final_claims_usd=last['claims_usd'] if result.complete else None,
  annualized_strc_distribution_usd=last['annualized_strc_distributions_usd'] if result.complete else None,
  annualized_new_strc_distribution_usd=(last['state']['strc_shares']-first['state']['strc_shares'])*100*last['strc_annual_rate'] if result.complete else None,
  in_horizon_new_strc_cash_paid_usd=sum(p['amount_native'] for p in result.generated_payments if p['id'] in {q for e in ledger if e['action']=='settle_dated_commitments' for q in e['details']['payment_ids']}),
  minimum_reserve_margin_usd=min(p['state']['reserve_designation_usd']-p['reserve_floor_usd'] for p in [first]+result.snapshots),
  event_common_drawdown=min([0.]+[p['conditional_common_price_usd']/max(q['conditional_common_price_usd'] for q in [first]+result.snapshots[:i])-1 for i,p in enumerate(result.snapshots,1)]),
  independent_checks=check['independent_economic_checks'],maximum_arithmetic_error=check['maximum_absolute_error'],
  configuration_sha256=digest(c),result_sha256=digest(result.to_dict()))
 if job['kind']=='strc':row.update(strc_scale=job['strc_scale'],future_strc_rate=job['future_strc_rate'])
 return row,result,prices


def search_grid(probe,grid,targets,tolerance):
 """Scan before refinement; permit multiple feasible bands and reversals."""
 for x in grid:probe(x)
 for target in targets:
  # Adjacent evaluations include refinements already made for other targets.
  ordered=sorted(probe.cache)
  for left,right in zip(ordered,ordered[1:]):
   if probe.cache[left][0][target]==probe.cache[right][0][target]:continue
   while right-left>tolerance:
    mid=(left+right)/2;probe(mid)
    if probe.cache[mid][0][target]==probe.cache[left][0][target]:left=mid
    else:right=mid
 return probe.cache


def run_job(job):
 dest=OUT/'jobs'/job['job_id'];done=dest.with_suffix('.json')
 if done.exists():return dict(job_id=job['job_id'],resumed=True)
 with gzip.open(INPUT/(job['template']+'.json.gz'),'rt') as f:base=json.load(f)
 cache={}
 def probe(x):
  if x not in cache:cache[x]=evaluate(base,job,x)
  return cache[x][0]
 probe.cache=cache
 targets=TARGETS if job['axis']!='sale_authority' else ('payments','funded')
 if job['kind']=='strc':probe(0.);selected={0.};summary=[]
 else:
  search_grid(probe,GRIDS[job['axis']],targets,TOLERANCE[job['axis']]);ordered=sorted(cache);selected={ordered[0],ordered[-1]};summary=[]
  for target in targets:
   transitions=[];bands=[];begin=None
   for i,x in enumerate(ordered):
    yes=cache[x][0][target]
    if yes and begin is None:begin=x
    if begin is not None and (not yes or i==len(ordered)-1):
     end=x if yes else ordered[i-1];bands.append([begin,end]);begin=None
   for left,right in zip(ordered,ordered[1:]):
    if cache[left][0][target]!=cache[right][0][target]:
     transitions.append(dict(left=left,right=right,left_pass=cache[left][0][target],right_pass=cache[right][0][target]));selected.update((left,right))
   passing=[x for x in ordered if cache[x][0][target]]
   low=min(passing) if passing else None
   if low is not None:selected.add(low)
   row={k:v for k,v in job.items() if k!='template'}
   row.update(target=target,lowest_feasible_tested=low,lower_domain=ordered[0],upper_domain=ordered[-1],
    boundary_status='no_feasible_tested' if low is None else 'feasible_at_lower_domain' if low==ordered[0] else 'transition_bracketed',
    feasible_bands=bands,transitions=transitions,observed_reversal=any(t['left_pass'] and not t['right_pass'] for t in transitions),
    evaluations=len(cache),coordinate_tolerance=TOLERANCE[job['axis']])
   if low is not None:row['witness']=cache[low][0]
   summary.append(row)
 dest.parent.mkdir(exist_ok=True)
 probe_file=dest.with_suffix('.probes.json.gz');witness_file=dest.with_suffix('.witnesses.jsonl.gz')
 probe_tmp=probe_file.with_name(probe_file.name+f'.{os.getpid()}.partial')
 witness_tmp=witness_file.with_name(witness_file.name+f'.{os.getpid()}.partial')
 with gzip.open(probe_tmp,'wt') as f:json.dump([cache[x][0] for x in sorted(cache)],f,separators=(',',':'),allow_nan=False)
 with gzip.open(witness_tmp,'wt',compresslevel=3) as f:
  for x in sorted(selected):
   row,r,prices=cache[x]
   marks=daily_marks(r,prices);high=marks[0]['conditional_common_price_usd'];dd=0.
   for m in marks:high=max(high,m['conditional_common_price_usd']);dd=min(dd,m['conditional_common_price_usd']/high-1)
   row['daily_common_drawdown']=dd
   f.write(json.dumps(dict(row=row,result=r.to_dict(),daily_marks=marks,endpoint_obligations=endpoint_obligations(r)),separators=(',',':'),allow_nan=False)+'\n')
 probe_tmp.replace(probe_file);witness_tmp.replace(witness_file)
 write_json(done,dict(job=job,search_summary=summary,evaluations=len(cache),witnesses=len(selected),all_checks_passed=True))
 return dict(job_id=job['job_id'],evaluations=len(cache),witnesses=len(selected),kind=job['kind'],axis=job['axis'])


def main():
 p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--workers',type=int,default=4);p.add_argument('--limit',type=int);p.add_argument('--axis');p.add_argument('--kind');a=p.parse_args()
 if a.prepare:prepare();return
 jobs=json.loads((INPUT/'jobs.json').read_text());jobs=[j for j in jobs if (not a.axis or j['axis']==a.axis) and (not a.kind or j['kind']==a.kind)]
 if a.limit:jobs=jobs[:a.limit]
 (OUT/'jobs').mkdir(parents=True,exist_ok=True);t=time.monotonic();n=0;evals=0
 failed=[]
 with ProcessPoolExecutor(max_workers=a.workers) as pool:
  futures={pool.submit(run_job,j):j['job_id'] for j in jobs}
  for f in as_completed(futures):
   
   try:result=f.result()
   except Exception as exc:
    failed.append(dict(job_id=futures[f],error=repr(exc)));print('FAILED',failed[-1],flush=True);continue
   n+=1;evals+=result.get('evaluations',0)
   if n%20==0 or n==len(jobs):print(json.dumps(dict(jobs_complete=n,total_jobs=len(jobs),new_evaluations=evals,seconds=round(time.monotonic()-t,1))),flush=True)
 if failed:
  write_json(OUT/'failed_jobs.json',failed)
  raise RuntimeError(f'{len(failed)} jobs failed; inspect results/failed_jobs.json')
if __name__=='__main__':main()
