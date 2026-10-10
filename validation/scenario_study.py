"""Crossed conditional stress comparisons for the full paper.

No scenario probabilities or fitted future premium trajectories are assigned.
Each historical path has an exact endpoint-matched smooth counterpart.
"""
from pathlib import Path
from datetime import timedelta
from copy import deepcopy
import argparse,csv,gzip,hashlib,itertools,json,math,sys,time
import pandas as pd

R=Path(__file__).parent;ROOT=R.parent
sys.path.insert(0,str(ROOT/'research/legacy_engine'))
sys.path.insert(0,str(ROOT/'research'))
from historical_study import corporate_template,windows,extract_prices,START,END
from price_interface.providers import smooth_match
from price_interface.market_conditions import conditions
from price_interface.market_adapter import compile_scenario,daily_marks,reporting_metrics,endpoint_obligations
from treasury_company.market_io import run_configuration
from treasury_company.market_growth import Opening,Point,mark
from treasury_company.dated import Claim
from premium_process import apply_to_corporate_template

O=R/'results';O.mkdir(exist_ok=True);A=O/'scenario_archives';A.mkdir(exist_ok=True)
OPENING_PRICE=86.93000030517578
PREMIUM_FACTORS={'compression':.5,'persistence':1.,'expansion':2.}
POLICIES=['reference','adaptive','principal_buffer']
REGIMES=['open','capacity','drawdown_closure']
DESIGN={'purpose':'Conditional corporate mechanisms; no price forecast or probability interpretation',
 'window_openings':'2020-09-01 through 2024-09-01; monthly starts; 49 overlapping paths',
 'corporate_opening':str(START),'corporate_end':str(END),'opening_observed_common_price':OPENING_PRICE,
 'premium_terminal_factors':PREMIUM_FACTORS,'premium_interpolation':'constant calendar-day log change from observed opening anchor',
 'policies':POLICIES,'regimes':REGIMES,'price_shapes':['historical','smooth_matched'],
 'crossed_configurations':49*2*3*3*3,'continuation_volatility':.65,'continuation_horizon_years':3.,
 'training_used_for_main_premium_paths':False,'extra_franchise_increment':0,
 'capacity_regime':'Each channel <=2% of contemporaneous common capitalization and nominal capacity reduced by high trailing Bitcoin volatility',
 'closure_regime':'Both issuance capacities zero at Bitcoin drawdown >=40% from scenario peak; reopen below threshold',
 'reference':'Inherited positive-net-face-backing common issuance screen and fixed discretionary requests',
 'adaptive':'Common discretionary requests use the Bitcoin-per-share screen; exhaustive audit shows the reference-value screen is redundant in the main design',
 'principal_buffer':'Reference issuance rule with unreserved cash retention equal to remaining scheduled principal plus $50m',
 'common_access_min_multiple':0,'access_gate_correction':'A threshold on the valuation-normalization multiplier is not a portable market-access rule; capacity and economic issuance screens remain explicit',
 'claim':'Sensitivity across this finite design, not a global robustness certificate'}

def build(prices,policy,premium,regime,vol=.65,horizon=3.):
    c,rule=corporate_template('principal_buffer' if policy=='principal_buffer' else 'reference',prices,'open')
    c['engine_version']='0.6.0'
    c['policy']['common_access_min_multiple']=0.
    if policy=='adaptive':c['policy'].update(common_growth_objective='bitcoin',common_scale_discretionary=True,common_full_scale_net_premium=1.25)
    if regime=='capacity':c['policy'].update(common_market_cap_fraction=.02,strc_market_cap_fraction=.02)
    ip=deepcopy(c['initial_point']);ip.update(valuation_mode='continuation',valuation_volatility=vol,valuation_horizon_years=horizon,multiple=1.,franchise_expected_gross_usd=0.)
    st=deepcopy(c['opening']);st['claims']=[Claim(**x) for x in st['claims']]
    anchor=OPENING_PRICE/mark(Opening(**st),Point(**ip))['conditional_common_price_usd']
    for p in [c['initial_point']]+c['path']:p.update(valuation_volatility=vol,valuation_horizon_years=horizon)
    days=(END-START).days
    premium_path={str(START+timedelta(days=i)):anchor*PREMIUM_FACTORS[premium]**(i/days) for i in range(days+1)}
    c=apply_to_corporate_template(c,premium_path,OPENING_PRICE)
    cond,audit=conditions(prices,str(START),str(END),'continuation_state',regime)
    for day,signal in c['metadata']['market_conditions'].items():signal['capacity_multiplier']=cond[day]['capacity_multiplier']
    for p in [c['initial_point']]+c['path']:p['capacity_multiplier']=cond[p['date']]['capacity_multiplier']
    c['metadata']['valuation_scenario']={'premium':premium,'terminal_factor':PREMIUM_FACTORS[premium],'opening_anchor':anchor,'future_values_are_assumptions':True}
    c['metadata']['financing_condition_audit']=audit
    c['metadata']['main_study_design']=DESIGN
    c['metadata']['inherited_assumptions_for_provenance_only']=c['metadata'].pop('assumptions',[])
    c['metadata']['assumptions']=['scenario_design.json and the complete retained numeric configuration govern this study.',
      'Observed opening price anchors the valuation multiple. Future premiums are explicit scenarios, not estimates.',
      'Market access is controlled by capacity. No access threshold is imposed on the valuation-normalization multiple.',
      'Economic common issuance screens and preferred execution gates remain separate from investor capacity.',
      'The cash buffer restricts discretionary purchases; it does not imply continuous prefunding of future principal.',
      'Same-event proceeds availability, basic share denominator, fixed contractual assumptions and unresolved opening bridges remain explicit.',
      'No general-use Bitcoin sales are authorized in the main comparison. Permission sensitivities are separate.',
      'Neither historical-window counts nor scenario frequencies are probabilities.']
    return compile_scenario(c,prices,buffer_rule=rule)

def evaluate(cfg,prices,ident):
    cfg=deepcopy(cfg);cfg['configuration_id']=ident
    result=run_configuration(cfg)
    marks=daily_marks(result,prices);metrics=reporting_metrics(result,marks,.05)
    assert abs(result.initial_snapshot['conditional_common_price_usd']-OPENING_PRICE)<1e-8
    assert result.reconciliation['all_prefixes_reconciled']
    for e in result.ledger:
        if e['action']=='issue_common_atm':
            assert math.isclose(e['balances']['common_shares']*e['details']['price_usd'],e['details']['gross_usd'],abs_tol=.01)
        if e['action']=='purchase_bitcoin':
            assert math.isclose(e['balances']['btc']*e['details']['btc_price_usd']+e['details']['execution_cost_usd'],-e['balances']['cash_usd'],abs_tol=.01)
    first,last=result.initial_snapshot,result.snapshots[-1];funded=metrics['completed'] and result.assessment['reserve_compliant_throughout']
    row={'id':ident,'funded':funded,'complete':result.complete,'failure_date':result.failure.get('date') if result.failure else None,
      'return':metrics['equity_return'] if funded else None,'drawdown':metrics['daily_max_drawdown'] if funded else None,
      'processed_period_drawdown':metrics['daily_max_drawdown'],'bitcoin_return':metrics['scheduled_bitcoin_return_input'],
      'final_btc':last['state']['btc'] if funded else None,'final_shares':last['state']['common_shares'] if funded else None,
      'btc_per_share_change':last['btc_per_common_share']/first['btc_per_common_share']-1 if funded else None,
      'final_liquid_assets':last['liquid_assets_usd'] if funded else None,
      'final_senior_claims':last['claims_usd'] if funded else None,
      'new_preferred_annual_distribution':last['annualized_strc_distributions_usd']-first['annualized_strc_distributions_usd'] if funded else None,
      'common_gross':sum(e['details']['gross_usd'] for e in result.ledger if e['action']=='issue_common_atm'),
      'preferred_gross':sum(e['details']['gross_usd'] for e in result.ledger if e['action']=='issue_strc'),
      'purchased_btc':sum(e['balances']['btc'] for e in result.ledger if e['action']=='purchase_bitcoin'),
      'sold_btc':-sum(e['balances']['btc'] for e in result.ledger if e['action'].startswith('sell_bitcoin')),
      'max_ledger_error':result.reconciliation['max_absolute_reconstruction_error'],
      'nominal_value_supported':bool(funded and metrics['equity_return']>=-1e-12),
      'btc_per_share_supported':bool(funded and last['btc_per_common_share']>=first['btc_per_common_share']*(1-1e-12)),
      'min_cash_buffer_gap':min(x['liquid_assets_usd']-x['state']['reserve_designation_usd']-x['unreserved_cash_buffer_usd'] for x in result.snapshots),
      'buffer_is_purchase_retention_rule':True}
    record={'id':ident,'result':result.to_dict(),'daily_marks':marks,'metrics':metrics,'endpoint_obligations':endpoint_obligations(result)}
    return row,record

def main():
    p=argparse.ArgumentParser();p.add_argument('--start',type=int,default=0);p.add_argument('--stop',type=int,default=49);p.add_argument('--force',action='store_true');args=p.parse_args()
    (O/'scenario_design.json').write_text(json.dumps(DESIGN,indent=2)+'\n')
    selected=[(i,w) for i,w in windows(extract_prices()) if '2020-09-01'<=i['window_id']<='2024-09-01'];assert len(selected)==49
    clock=time.monotonic()
    for wi,(info,hist) in enumerate(selected):
        if not args.start<=wi<args.stop:continue
        dest=A/(info['window_id']+'.jsonl.gz');summary=A/(info['window_id']+'.csv')
        if dest.exists() and summary.exists() and not args.force:continue
        tmp=dest.with_suffix('.partial');rows=[]
        shapes={'historical':hist,'smooth_matched':smooth_match(hist,str(START),str(END),'smooth_'+info['window_id'])}
        with gzip.open(tmp,'wt',compresslevel=3) as stream:
            for shape,premium,policy,regime in itertools.product(shapes,PREMIUM_FACTORS,POLICIES,REGIMES):
                prices=shapes[shape];cfg=build(prices,policy,premium,regime)
                ident='_'.join([info['window_id'],shape,premium,policy,regime])
                row,record=evaluate(cfg,prices,ident);row.update(window=info['window_id'],shape=shape,premium=premium,policy=policy,regime=regime)
                encoded=json.dumps(record,separators=(',',':'),allow_nan=False);row['record_sha256']=hashlib.sha256(encoded.encode()).hexdigest()
                stream.write(encoded+'\n');rows.append(row)
        tmp.replace(dest);pd.DataFrame(rows).to_csv(summary,index=False)
        print(json.dumps({'window':info['window_id'],'runs':len(rows),'seconds':round(time.monotonic()-clock,1),'funded':sum(r['funded'] for r in rows)}),flush=True)
    summaries=sorted(A.glob('*.csv'))
    if summaries:
        pd.concat([pd.read_csv(x) for x in summaries],ignore_index=True).to_csv(O/'scenario_runs.csv',index=False)

if __name__=='__main__':main()
