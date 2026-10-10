"""Historical return-sequence experiment on the unchanged corporate engine.

Offline and deterministic. Run python historical_study.py; use --verify-only
to replay the retained study. Data extraction never silently refreshes the data.
"""
import argparse
import csv
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import lzma
import math
from pathlib import Path
import time

from run_revision import configuration, independent_checks, extra_metrics
from treasury_company.io import run_configuration
from price_interface import PricePath
from price_interface.adapter import (compile_scenario, daily_marks, reporting_metrics,
                                     endpoint_obligations, replay)
from price_interface.providers import smooth_match
from price_interface.prices import digest
from verify_price_interface import check_preservation

ROOT = Path(__file__).resolve().parent
DATA = ROOT/'historical_data'
OUT = ROOT/'historical_results'
START, END = date(2026,6,30), date(2027,9,30)
DAYS = (END-START).days
POLICIES = ('reference', 'capped_40', 'principal_buffer')
REGIMES = ('open', 'drawdown_closure')

def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')

def extract_prices():
    raw = DATA/'coinmetrics_btc_raw.csv'
    with raw.open() as stream:
        rows = list(csv.DictReader(stream))
    values = [(r['time'][:10], r['PriceUSD']) for r in rows if r.get('PriceUSD')]
    assert len(values) == len(set(d for d,p in values))
    selected = [(d,p) for d,p in values if '2014-01-01' <= d <= '2025-12-31']
    assert selected[0][0]=='2014-01-01' and selected[-1][0]=='2025-12-31'
    for i,(d,p) in enumerate(selected):
        assert date.fromisoformat(d)==date(2014,1,1)+timedelta(days=i)
        assert math.isfinite(float(p)) and float(p)>0
    with (DATA/'btc_priceusd_2014_2025.csv').open('w',newline='') as f:
        w=csv.writer(f); w.writerow(['date','price_usd']);w.writerows(selected)
    raw_hash=hashlib.sha256(raw.read_bytes()).hexdigest()
    metadata=dict(schema_version='1.0',scenario_id='coinmetrics_daily_2014_2025',
        kind='historical',source='Coin Metrics Community archive, BTC PriceUSD',
        units='USD_per_BTC',price_timing='daily_close',availability_lag_days=1,
        interpolation='exact',max_gap_days=None,
        assumptions=['Daily UTC closes become available on the following calendar date.',
                     'Frozen revised data; original publication vintages are not available.'],
        provenance=dict(raw_filename='historical_data/coinmetrics_btc_raw.csv',
                        raw_sha256=raw_hash,source_url='https://raw.githubusercontent.com/coinmetrics/data/master/csv/btc.csv',
                        license='CC BY-NC 4.0',retrieval_date='2026-10-04'))
    write_json(DATA/'btc_priceusd_metadata.json',metadata)
    source=PricePath(dict(metadata,points=[dict(date=d,price_usd=float(p)) for d,p in selected]))
    report=dict(raw_rows=len(rows),raw_price_rows=len(values),raw_price_start=values[0][0],
        raw_price_end=values[-1][0],raw_sha256=raw_hash,selected_rows=len(selected),
        selected_start=selected[0][0],selected_end=selected[-1][0],missing_selected_days=0,
        duplicate_selected_dates=0,nonpositive_or_nonfinite_prices=0,source_price_sha256=source.sha256,
        source_is_revised_not_vintage=True,selection='Complete calendar years 2014–2025; monthly first-day observation starts; full 457-day windows only.')
    write_json(DATA/'validation.json',report)
    return source

def windows(source):
    for year in range(2014,2026):
        for month in range(1,13):
            observed_start=date(year,month,1)
            observed_end=observed_start+timedelta(days=DAYS)
            if observed_end > date(2025,12,31):
                continue
            available_start=observed_start+timedelta(days=1)
            available_end=observed_end+timedelta(days=1)
            # Store this window's observations with full metadata. The complete
            # frozen source is retained once in the package, identified by hash.
            a=source.to_dict()
            a['points']=[p for p in a['points'] if str(observed_start)<=p['date']<=str(observed_end)]
            a['scenario_id']='observed_'+str(observed_start)
            a['provenance']['full_source_price_sha256']=source.sha256
            a['provenance']['full_source_file']='historical_data/btc_priceusd_2014_2025.csv'
            window=PricePath(a)
            p=window.historical_window(str(available_start),str(available_end),str(START),58714.0,'historical_'+str(observed_start))
            yield dict(window_id=str(observed_start),source_close_start=str(observed_start),
                       source_close_end=str(observed_end),source_availability_start=str(available_start),
                       source_availability_end=str(available_end)),p

def conditions(prices, regime):
    """Observed-to-date drawdown only; the opening date resets the peak.

    The mapped value is already available because source closes were lagged.
    No additional day lag is needed. Decisions occur only on corporate dates.
    """
    assert regime in REGIMES
    high=0.; out={}
    for i in range(DAYS+1):
        d=str(START+timedelta(days=i));p=prices.at(d);high=max(high,p)
        dd=p/high-1
        out[d]=dict(drawdown=dd,open=(regime=='open' or dd > -.40))
    return out

def corporate_template(policy, prices, regime):
    assert policy in POLICIES
    c=configuration(use_cap=.4 if policy=='capped_40' else 1.)
    cond=conditions(prices,regime)
    for p in [c['initial_point']]+c['path']:
        if not cond[p['date']]['open']:
            p['common_issue_cap_gross_usd']=p['strc_issue_cap_gross_usd']=0.
    c['metadata']['historical_study']=dict(policy=policy,regime=regime,
        access_rule='Both issuance capacities are zero when available Bitcoin price is at least 40% below the running peak since scenario opening; reopen when above threshold.',
        trigger_is_scenario_assumption=True,conditions=cond)
    rule={'mode':'embedded'}
    if policy=='principal_buffer':
        rule=dict(mode='principal',margin_usd=50e6,planning_end=str(END),
                  principal_schedule_valid_through=str(END))
    return c,rule

def run_one(info, prices, shape, policy, regime):
    c,rule=corporate_template(policy,prices,regime)
    c['metadata']['historical_study'].update(info,shape=shape)
    cfg=compile_scenario(c,prices,buffer_rule=rule)
    result=run_configuration(cfg)
    daily=daily_marks(result,prices)
    rec=dict(interface_version='0.1.0',price_scenario_id=prices.to_dict()['scenario_id'],
        corporate_result=result.to_dict(),daily_valuations=daily,
        metrics=reporting_metrics(result,daily,.05),endpoint_obligations=endpoint_obligations(result))
    checks=independent_checks(result)
    row=extra_metrics(result)
    row.update(info,shape=shape,policy=policy,regime=regime,**rec['metrics'])
    row['common_gross_issued_usd']=sum(e['details']['gross_usd'] for e in result.ledger if e['action']=='issue_common_atm')
    row['strc_gross_issued_usd']=sum(e['details']['gross_usd'] for e in result.ledger if e['action']=='issue_strc')
    row['final_btc']=result.snapshots[-1]['state']['btc'] if result.complete else None
    row['annualized_strc_distributions_usd']=rec['endpoint_obligations']['annualized_strc_distributions_usd']
    row['closed_issuance_events']=sum(not c['metadata']['historical_study']['conditions'][p['date']]['open']
        and (p['common_program_target_gross_usd']>0 or p['strc_issue_target_gross_usd']>0) for p in c['path'])
    row['source_bitcoin_max_drawdown']=min(x['drawdown'] for x in conditions(prices,regime).values())
    row['daily_quote_undefined']=any(not d['quote_defined'] for d in daily)
    row['daily_mapping_missed_by_events']=row['daily_quote_undefined'] and row['equity_mapping_supported']
    # The daily extension must not change event cash tests or invent terminal returns.
    assert all(d['btc_price_usd'] == prices.at(d['date']) for d in daily)
    assert result.complete or row['equity_return'] is None
    encoded=json.dumps(rec,separators=(',',':'),allow_nan=False)
    replay(json.loads(encoded))
    row['record_sha256']=hashlib.sha256(encoded.encode()).hexdigest()
    return row,encoded,checks

def run(limit=None):
    OUT.mkdir(exist_ok=True)
    source=extract_prices();preserved=check_preservation();rows=[];checks=0;err=0;start=time.monotonic()
    with lzma.open(OUT/'paths.jsonl.xz','wt',encoding='utf-8',preset=3) as f:
        for wi,(info,hist) in enumerate(windows(source)):
            if limit is not None and wi>=limit:break
            smooth=smooth_match(hist,str(START),str(END),'smooth_'+info['window_id'])
            assert smooth.at(str(START))==hist.at(str(START)) and smooth.at(str(END))==hist.at(str(END))
            for shape,prices in [('historical',hist),('smooth',smooth)]:
                for regime in REGIMES:
                    for policy in POLICIES:
                        row,encoded,audit=run_one(info,prices,shape,policy,regime)
                        row['archive_line']=len(rows)+1;rows.append(row);f.write(encoded+'\n')
                        checks+=audit['independent_economic_checks'];err=max(err,audit['maximum_absolute_error'])
            print('Windows',wi+1,'runs',len(rows),'seconds',round(time.monotonic()-start,1),flush=True)
    write_json(OUT/'summary.json',rows)
    scalar=[k for k in rows[0] if not isinstance(rows[0][k],(dict,list))]
    with (OUT/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=scalar,extrasaction='ignore');w.writeheader();w.writerows(rows)
    write_json(OUT/'verification.json',dict(records=len(rows),exact_serialized_replays=len(rows),
        independent_economic_checks=checks,maximum_absolute_accounting_error_usd=err,
        journal_prefixes_reconciled=True,matched_price_endpoints_verified=True,
        original_engine_and_calibration_files_unchanged=preserved['files_checked'],
        historical_windows=len(rows)//12,policies=list(POLICIES),regimes=list(REGIMES),
        horizon_days=DAYS,all_records_retained=True,probabilities_assigned=False))

def verify_archive():
    rows=json.loads((OUT/'summary.json').read_text());checks=0
    with lzma.open(OUT/'paths.jsonl.xz','rt') as f:
        for i,line in enumerate(f):
            assert hashlib.sha256(line.rstrip('\n').encode()).hexdigest()==rows[i]['record_sha256']
            replay(json.loads(line));checks+=1
    assert checks==len(rows)
    print('Retained record hashes and exact replays verified:',checks)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int);p.add_argument('--verify-only',action='store_true');args=p.parse_args()
    if args.verify_only:verify_archive()
    else:run(args.limit)
