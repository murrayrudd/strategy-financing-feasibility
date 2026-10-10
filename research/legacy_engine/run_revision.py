"""Targeted comparative experiments; unchanged 0.4 corporate accounting engine.

All numeric experiments are conditional and retain entire inputs and results.
Python standard library only; plotting and document generation are separate.
"""
from copy import deepcopy
from datetime import date
from pathlib import Path
import csv
import hashlib
import itertools
import json
import lzma
import math

from run_feasibility import configuration as base_configuration, row_for
from treasury_company.io import run_configuration
from check_financing import audit

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'revision'


def configuration(use_cap=1.0, cash_rule='fixed', rescue_atm=True,
                  closure_start=None, closure_end=None, strc_discount=False,
                  operating_use_m=5.0, put_fraction=1.0, sale_tax=.02, **base):
    c = base_configuration(**base)
    params = dict(c['metadata']['parameters'], use_cap=use_cap, cash_rule=cash_rule,
                  rescue_atm=rescue_atm, closure_start=closure_start,
                  closure_end=closure_end, strc_discount=strc_discount,
                  operating_use_m=operating_use_m, put_fraction=put_fraction,
                  sale_tax=sale_tax)
    if not (0 <= use_cap <= 1 and put_fraction in (0, 1) and operating_use_m >= 0):
        raise ValueError('Invalid policy or sensitivity parameter')
    if cash_rule not in ('fixed', 'principal'):
        raise ValueError('Unknown cash rule')
    if bool(closure_start) != bool(closure_end):
        raise ValueError('Closure needs both endpoints')
    for p in c['payments']:
        if p['kind'] == 'principal' and p['payment_date'] == '2027-09-15':
            p['amount_native'] *= put_fraction
    c['payments'] = [p for p in c['payments'] if p['amount_native'] > 0]
    principals = [p for p in c['payments'] if p['kind'] == 'principal'
                  and p['payment_date'] <= c['path'][-1]['date']]
    for p in [c['initial_point']] + c['path']:
        if p['operating_cashflow_usd'] < 0:
            p['operating_cashflow_usd'] = -operating_use_m*1e6
        # Capacity is an opportunity. A fixed use ceiling can leave it unused.
        p['common_issue_cap_gross_usd'] = min(p['common_issue_cap_gross_usd'], 1.1e9*use_cap)
        p['strc_issue_cap_gross_usd'] = min(p['strc_issue_cap_gross_usd'], .4e9*use_cap)
        in_window = closure_start and closure_start <= p['date'] <= closure_end
        if in_window:
            p['common_issue_cap_gross_usd'] = 0
            p['strc_issue_cap_gross_usd'] = 0
        if strc_discount and '2026-10-01' <= p['date'] <= '2027-03-31':
            p['strc_execution_price_usd'] = 97
        if cash_rule == 'principal':
            # Evaluated after current payments, using their known dates, not a
            # future price or a future financing realization.
            claims = {x['id']:x for x in c['opening']['claims']}
            p['unreserved_cash_buffer_usd'] = 50e6 + sum(
                x['amount_native']*p['fx_usd_per_unit'][claims[x['claim_id']]['currency']]
                for x in principals if x['payment_date'] > p['date'])
    c['policy'].update(common_fund_cash_shortfalls=rescue_atm,
                       effective_sale_tax_cash_fraction=sale_tax)
    c['metadata']['parameters'] = params
    c['metadata']['v05_assumptions_for_provenance_only'] = c['metadata'].pop('assumptions')
    c['metadata']['assumptions'] = [
        'REVISION_DESIGN.md and these complete numerical parameters govern the 0.6.0 analysis; earlier notes are provenance.',
        'The 0.4.0 corporate engine and opening calibration are unchanged. Company-information cutoff remains August 3, 2026.',
        'The use ceiling is a voluntary restriction on executable capacity; unused market access is not cash.',
        'The principal-linked buffer protects remaining modeled principal plus $50m after current settlements; it uses the known payment schedule, not future realized prices.',
        'The scheduled-only comparison disables additional cash-shortfall common requests, but does not implement T+1 settlement.',
        'Joint stresses, valuation multiples, capacities, and policy rules are supplied scenarios, without probabilities or optimality claims.',
        'Bitcoin-relative return, an illustrative annual hurdle, and event-date drawdown are separate diagnostics; the primary target remains nominal terminal value preservation.',
        'Historical reconciliation flags, contract approximations, and the uncompleted Monster–CRRA comparison remain explicit.'
    ]
    c['metadata'].update(analysis_version='0.6.0', revision_design='REVISION_DESIGN.md')
    c['configuration_id'] = 'revision_'+hashlib.sha256(
        json.dumps(params, sort_keys=True).encode()).hexdigest()[:20]
    return c


def independent_checks(r):
    checks = audit(r)
    c = r.configuration
    previous = r.initial_snapshot['state']
    for e in r.ledger:
        previous = e['after']
    end = r.snapshots[-1]
    start = r.initial_snapshot
    # Rebuild all principal valuation components, independently of engine mark.
    for s in [start]+r.snapshots:
        p = c['initial_point'] if s is start else next(x for x in c['path'] if x['date']==s['date'])
        st = s['state']
        liabilities = sum((x['face_native']+x['accrued_native'])*p['fx_usd_per_unit'][x['currency']]
                          for x in st['claims'])+st['unallocated_payable_usd']
        backing = st['btc']*p['btc_price_usd']+st['cash_usd']+st['treasuries_usd']+st['restricted_cash_usd']+p['net_operating_value_usd']-liabilities
        assert math.isclose(s['backing_usd'], backing, abs_tol=1e-4)
        checks['independent_economic_checks'] += 1
    if r.complete and r.assessment['criteria']['equity_mapping_defined_throughout']:
        identity = (c['path'][-1]['multiple']/c['initial_point']['multiple']
                    *end['backing_usd']/start['backing_usd']
                    *start['state']['common_shares']/end['state']['common_shares']-1)
        assert math.isclose(identity, r.assessment['conditional_terminal_equity_return'], abs_tol=1e-12)
        checks['independent_economic_checks'] += 1
    expected = (r.complete and all(s['reserve_compliant'] and s['quote_defined'] for s in [start]+r.snapshots)
                and r.assessment['conditional_terminal_equity_return'] is not None
                and r.assessment['conditional_terminal_equity_return'] >= -1e-12)
    assert expected == r.assessment['jointly_supported']
    assert r.complete or r.assessment['conditional_terminal_equity_return'] is None
    assert r.reconciliation['all_prefixes_reconciled']
    return checks


def extra_metrics(r):
    row = row_for(r)
    begin = r.initial_snapshot
    end = r.snapshots[-1]
    prices = [s['conditional_common_price_usd'] for s in [begin]+r.snapshots]
    drawdown = None
    if all(x is not None for x in prices):
        high = prices[0]
        drawdown = 0.0
        for x in prices:
            high = max(high, x)
            drawdown = min(drawdown, x/high-1)
    btc_return = r.configuration['path'][-1]['btc_price_usd']/r.configuration['initial_point']['btc_price_usd']-1
    row.update(terminal_bitcoin_return=btc_return,
               excess_over_bitcoin=(row['equity_return']-btc_return) if row['equity_return'] is not None else None,
               event_max_drawdown=drawdown,
               net_terminal_backing_usd=end['backing_usd'] if r.complete else None,
               btc_valuation_elasticity=(end['state']['btc']*r.configuration['path'][-1]['btc_price_usd']/end['backing_usd']) if r.complete and end['backing_usd']>0 else None,
               final_common_shares=end['state']['common_shares'] if r.complete else None,
               cashflow_paid_usd=sum(s['cash_due_usd'] for s in r.snapshots if s['settled']))
    row['target_bitcoin_supported'] = bool(row['funding_supported'] and row['equity_mapping_supported'] and row['excess_over_bitcoin'] is not None and row['excess_over_bitcoin'] >= -1e-12)
    row['target_fivepct_annual_supported'] = bool(row['funding_supported'] and row['equity_mapping_supported'] and row['equity_return'] is not None and row['equity_return'] >= 1.05**(457/365.25)-1-1e-12)
    return row


class Study:
    def __init__(self, archive):
        self.archive = archive
        self.rows = {}
        self.groups = {}
        self.check_count = 0

    def run(self, **kwargs):
        c = configuration(**kwargs)
        ident = c['configuration_id']
        if ident not in self.rows:
            r = run_configuration(c)
            record = r.to_dict()
            enc = json.dumps(record, separators=(',', ':'), allow_nan=False)
            assert run_configuration(json.loads(enc)).to_dict() == record
            self.check_count += independent_checks(r)['independent_economic_checks']
            row = extra_metrics(r)
            row.update(archive_line=len(self.rows)+1,
                       record_sha256=hashlib.sha256(enc.encode()).hexdigest(), replay_identical=True)
            self.rows[ident] = row
            self.archive.write(enc+'\n')
            if len(self.rows) % 100 == 0:
                print(f'Retained and checked {len(self.rows)} configurations', flush=True)
        return self.rows[ident]

    def group(self, name, **kwargs):
        row = self.run(**kwargs)
        self.groups.setdefault(name, []).append(row['id'])
        return row


def main():
    DEST.mkdir(exist_ok=True)
    with lzma.open(DEST/'paths.jsonl.xz', 'wt', encoding='utf-8', preset=6) as a:
        s = Study(a)
        ref = s.group('reference')
        assert abs(ref['equity_return']-(-.0491)) < .0001
        for family,ret in [('smooth',0),('smooth',.25),('smooth',-.25),('early',0),('late',0)]:
            for channel in ('common','both','strc'):
                s.group('equal_capital', family=family, terminal_return=ret, channel=channel,
                        equal_capital=True, rescue_atm=False)
        for ret in (0,.0275,.25,-.25):
            for access in (i/20 for i in range(21)):
                for cap in (.2,.3,.4,.5,.6,.8,1):
                    s.group('policy_capacity', terminal_return=ret, access=access, use_cap=cap)
        for family in ('smooth','early','late'):
            for multiple in (.75,1,1.1,1.25,1.5,1.75):
                s.group('valuation_path', family=family, terminal_multiple=multiple)
        for cash_rule, rescue, access in itertools.product(('fixed','principal'), (True,False),(.2,.5,1)):
            for family in ('smooth','early','late'):
                s.group('cash_policy', cash_rule=cash_rule, rescue_atm=rescue, access=access, family=family)
        for mask in range(16):
            s.group('joint_stress', family='early', terminal_multiple=1 if mask&1 else 1.25,
                    closure_start='2026-10-01' if mask&2 else None,
                    closure_end='2027-03-31' if mask&2 else None,
                    rate=.14 if mask&4 else .12, strc_discount=bool(mask&8))
        for lo,hi in [('2026-07-01','2026-12-31'),('2026-10-01','2027-03-31'),
                      ('2027-01-01','2027-06-30'),('2027-04-01','2027-09-30')]:
            for cash_rule,sales in itertools.product(('fixed','principal'),(0.,2e9)):
                s.group('closure_timing', closure_start=lo,closure_end=hi,
                        cash_rule=cash_rule,general_sale_usd=sales)
        for x in (0.,5.,10.):
            s.group('operating_sensitivity',operating_use_m=x)
        for x in (0.,1.):
            s.group('put_sensitivity',put_fraction=x)
        for x in (0.,.02,.05):
            s.group('tax_sensitivity',access=0,general_sale_usd=2e9,sale_tax=x)
        # One-way level comparisons are reported at declared perturbation sizes.
        for ret in (-.25,-.10,0,.10,.25):
            s.group('bitcoin_sensitivity',terminal_return=ret)
        for rate in (.10,.12,.14):
            s.group('rate_sensitivity',rate=rate)
        for fee in (.0025,.01,.02):
            s.group('fee_sensitivity',issue_fee=fee)
        for buffer in (0, .15e9,.3e9,.6e9,1.1e9):
            for rescue in (True,False):
                s.group('reactive_financing',buffer_usd=buffer,rescue_atm=rescue)
        # Target comparison on a common smooth-return grid, with every switch
        # retained. No presumption that the support set has a unique threshold.
        thresholds = []
        for target in ('primary_joint_supported','target_bitcoin_supported','target_fivepct_annual_supported'):
            samples = [(i/100, s.run(terminal_return=i/100)) for i in range(-50,61,5)]
            switches = []
            for (lo,left),(hi,right) in zip(samples,samples[1:]):
                if left[target] == right[target]: continue
                while hi-lo > .0001:
                    mid=(lo+hi)/2; r=s.run(terminal_return=mid)
                    if r[target] == left[target]:lo,left=mid,r
                    else:hi,right=mid,r
                switches.append(dict(lower=lo,upper=hi,lower_id=left['id'],upper_id=right['id'],
                                     lower_supported=left[target],upper_supported=right[target]))
            thresholds.append(dict(target=target,sample_ids=[r['id'] for _,r in samples],switches=switches))
        (DEST/'thresholds.json').write_text(json.dumps(thresholds,indent=2)+'\n')
        # Exploratory follow-up specified after observing the recovery controls:
        # contrast terminal success with the interim equity drawdown.
        for family in ('smooth', 'early', 'late'):
            s.group('recovery_positive', family=family, terminal_return=.25)
        rows = list(s.rows.values())
        (DEST/'index.json').write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')
        (DEST/'groups.json').write_text(json.dumps(s.groups,indent=2)+'\n')
        with (DEST/'summary.csv').open('w', newline='') as f:
            fields=['id','completed','equity_return','excess_over_bitcoin','event_max_drawdown',
                    'common_gross_usd','strc_gross_usd','final_btc','btc_sold','basic_share_dilution',
                    'btc_per_share_change','annualized_strc_distributions_usd','primary_joint_supported']
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
        # Frozen-ledger re-mark is an accounting counterfactual, not a new run.
        remark=[]
        for ident in s.groups['valuation_path']:
            row=s.rows[ident];p=row['parameters']
            refrow=s.run(family=p['family'])
            m=p['terminal_multiple']
            frozen=(1+refrow['equity_return'])*m/1.25-1 if refrow['equity_return'] is not None else None
            remark.append(dict(family=p['family'],terminal_multiple=m,full_path_id=ident,
                               frozen_path_id=refrow['id'],full_path_return=row['equity_return'],
                               frozen_ledger_return=frozen,
                               intervening_path_difference=(row['equity_return']-frozen) if row['equity_return'] is not None and frozen is not None else None))
        (DEST/'valuation_decomposition.json').write_text(json.dumps(remark,indent=2)+'\n')
        report=dict(configurations=len(s.rows),independent_checks=s.check_count,
                    all_exact_replays=True,engine_version='0.4.0',analysis_version='0.6.0',
                    prior_regression_tests=117,new_regression_tests=7,
                    total_regression_tests=124,probabilities_assigned=False)
        (DEST/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__=='__main__': main()
