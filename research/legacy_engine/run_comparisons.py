"""Controlled corporate comparisons; no Bitcoin mechanism or probabilities."""
from copy import deepcopy
from datetime import date, timedelta
import csv
import json
import math
from pathlib import Path

from treasury_company.io import run_configuration

ROOT = Path(__file__).resolve().parent
START, END = date(2026,6,30), date(2027,9,30)
# NY Fed calendar; Saturday holidays do not close the preceding Friday.
# Calendar rule checked against STRC certificate 3(f)(ii), not exchange holidays.
HOLIDAYS = {date.fromisoformat(s) for s in (
    '2026-01-01','2026-01-19','2026-02-16','2026-05-25','2026-06-19','2026-07-04',
    '2026-09-07','2026-10-12','2026-11-11','2026-11-26','2026-12-25',
    '2027-01-01','2027-01-18','2027-02-15','2027-05-31','2027-06-19','2027-07-05',
    '2027-09-06','2027-10-11','2027-11-11','2027-11-25','2027-12-25')}

PATHS = {
    'flat': ('Flat', [('2026-06-30',1),('2027-09-30',1)]),
    'up25': ('Rise 25%', [('2026-06-30',1),('2027-09-30',1.25)]),
    'up50': ('Rise 50%', [('2026-06-30',1),('2027-09-30',1.5)]),
    'down25': ('Fall 25%', [('2026-06-30',1),('2027-09-30',.75)]),
    'early_recovery': ('Early 40% drawdown, recovery', [('2026-06-30',1),('2026-12-15',.6),('2027-09-30',1)]),
    'late_recovery': ('Late 40% drawdown, recovery', [('2026-06-30',1),('2027-06-15',.6),('2027-09-30',1)]),
    'deep_decline': ('Fall 90%: boundary stress', [('2026-06-30',1),('2027-09-30',.1)])
}


def next_business_day(dt):
    while dt.weekday() >= 5 or dt in HOLIDAYS:
        dt += timedelta(days=1)
    return dt


def factor_at(when, knots):
    dt = date.fromisoformat(when)
    knots = [(date.fromisoformat(d),v) for d,v in knots]
    for (a,x),(b,y) in zip(knots,knots[1:]):
        if a <= dt <= b:
            weight = (dt-a).days/(b-a).days
            return math.exp(math.log(x)+(math.log(y)-math.log(x))*weight)
    raise ValueError('Point outside supplied path family')


def configuration(path_id='flat', financing='closed', general_authorization=True,
                  multiple=1, buyback=False, adjust_strc=True):
    cfg = json.loads((ROOT/'examples/strategy_dated_demo.json').read_text())
    cfg['engine_version'] = '0.3.0'
    cfg['configuration_id'] = f'{path_id}__{financing}__general_{general_authorization}__m_{multiple}__buyback_{buyback}'
    cfg['criteria'].pop('min_terminal_btc_per_share_ratio')
    old_points = {p['date']:deepcopy(p) for p in cfg['path']}
    shifts = []
    if adjust_strc:
        for pay in cfg['payments']:
            if pay['claim_id']=='STRC':
                old = pay['payment_date']
                new = str(next_business_day(date.fromisoformat(old)))
                pay['payment_date'] = new
                pay['note'] += '; settlement adjusted by STRC 3(f)(ii); accrual end unchanged'
                if new != old:
                    shifts.append(dict(id=pay['id'],nominal_date=old,payment_date=new))
                    if new <= str(END) and new not in old_points:
                        old_points[new] = dict(deepcopy(cfg['initial_point']),date=new,operating_cashflow_usd=0)
    cfg['payments'].sort(key=lambda p:(p['payment_date'],p['id']))
    cfg['path'] = [old_points[d] for d in sorted(old_points)]
    knots = PATHS[path_id][1]
    for p in [cfg['initial_point']]+cfg['path']:
        p['btc_price_usd'] = 58714*factor_at(p['date'],knots)
        p['multiple'] = multiple
        p.update(btc_general_use_gross_limit_usd=2_000_000_000 if general_authorization else 0,
                 btc_reserve_build_gross_limit_usd=1_250_000_000,
                 btc_distribution_sales_authorized=True)
        if financing=='limited_common':
            p.update(common_issue_cap_gross_usd=250_000_000, common_authorization_gross_limit_usd=1_500_000_000)
        elif financing=='ample_common':
            p.update(common_issue_cap_gross_usd=1_100_000_000, common_authorization_gross_limit_usd=3_000_000_000)
        elif financing!='closed':
            raise ValueError(financing)
        if buyback and p['date']=='2026-12-31':
            p.update(common_repurchase_cap_usd=500_000_000,
                     common_repurchase_gross_limit_usd=1_000_000_000,
                     common_repurchase_share_cap=100_000_000,
                     btc_repurchase_sales_authorized=True)
    cfg['policy'].update(common_issue_fee_rate=.01, common_issue_discount=0,
                         repurchase_common_from_btc=buyback,common_repurchase_fee_rate=.001,
                         common_repurchase_spread=.001)
    old_notes=cfg['metadata'].pop('assumptions')
    cfg['metadata']['v02_assumptions_for_provenance_only']=old_notes
    cfg['metadata']['assumptions']=[
        'Opening observations, economic accrual interpolation, unsecured claims, operating cash use, reserve floor, FX, cash-tax friction and net operating value remain as in v0.2 except explicit changes below.',
        'BTC path uses log-linear interpolation between listed dated knots. Terminal percentages cover 15 months, not one year. Prices are conditional inputs, not estimated probabilities or predictions.',
        'All scenarios use the same dated cash schedule and unchanged future preferred share counts, rates and preference amounts. No price-triggered conversion is inferred.',
        'STRC payment dates follow the next NY Fed business day, without extra accrued dividends; nominal accrual ends remain intact. Other modeled coupon and quarterly preferred dates in this horizon are ordinary weekdays. Their full calendars remain subject to instrument verification.',
        'Primary joint target: all scheduled payments, reserve floor at every supplied point, defined equity mapping throughout, and nonnegative terminal common-equity return. Bitcoin per basic common share is a separate diagnostic and optional target.',
        'BTC sale purpose is constrained separately from market capacity. The closed-financing price comparisons assume an additional $2bn cumulative gross general-use authorization covering principal/operating needs. This is not an observed authorization.',
        'Current modeled program: distribution funding/replenishment, up to $1.25bn gross reserve building, and separately authorized common repurchases. General-use sales cannot borrow these permissions. Initial reserve designation remains unavailable for general uses.',
        'Common financing capacity is a scenario input, not remaining registration capacity or a commitment from investors. Limited access is $250m per supplied event and $1.5bn cumulative; ample access is $1.1bn per event and $3bn cumulative. Gross proceeds incur 1% fees. No advance issuance beyond current modeled funding need.',
        'Buyback comparison fixes the equity multiple at 0.75 in both matched runs. One optional $500m purchase on December 31, 2026 uses BTC sale receipts, incurs 0.1% repurchase fees and a 0.1% price spread, and must increase backing per share after friction. No reserve cash funds the buyback.',
        'The two historical disclosure bridges remain flags. The $248.82 unallocated opening payable stays in claims without an invented settlement. The secured-loan schedule remains a labeled approximation, checked separately over timing/rate alternatives.'
    ]
    cfg['metadata'].update(purpose='Controlled supplied-path price, financing and capital-allocation comparisons',
                           path_id=path_id,path_label=PATHS[path_id][0],path_knots=knots,
                           financing=financing,general_sale_authorization_assumed=general_authorization,
                           calendar_shifts=shifts,constant_multiple=multiple,buyback_requested=buyback,
                           source_review='TERM_REVIEW.md')
    return cfg


def summarize(r):
    d=r.to_dict(); a=d['assessment']; initial=d['initial_snapshot']; end=d['snapshots'][-1]
    sale_entries=[e for e in d['ledger'] if e['action'].startswith('sell_bitcoin')]
    issued=[e for e in d['ledger'] if e['action']=='issue_common_for_funding']
    return dict(id=d['configuration_id'], path=d['configuration']['metadata']['path_id'],
                financing=d['configuration']['metadata']['financing'],
                terminal_btc_price_input=d['configuration']['path'][-1]['btc_price_usd'],
                completed=d['complete'], last_processed_date=end['date'],
                btc_sold_through_last_point=sum(-e['balances']['btc'] for e in sale_entries),
                sale_gross_usd=sum(e['details']['gross_usd'] for e in sale_entries),
                new_common_gross_usd=sum(e['details']['gross_usd'] for e in issued),
                net_common_share_change=end['state']['common_shares']-initial['state']['common_shares'],
                btc_per_share_change=(a['terminal_btc_per_share_ratio']-1) if a['terminal_btc_per_share_ratio'] is not None else None,
                equity_return=a['conditional_terminal_equity_return'],
                reserve_supported=a['reserve_compliant_throughout'] and d['complete'],
                primary_joint_supported=a['jointly_supported'],
                optional_btc_preservation_supported=(a['terminal_btc_per_share_ratio'] is not None and a['terminal_btc_per_share_ratio']>=1-1e-12),
                min_backing_usd=min(x['backing_usd'] for x in [initial]+d['snapshots']),
                failure=d['failure'])


def save_run(cfg, group):
    r=run_configuration(cfg)
    if run_configuration(r.to_dict()).to_dict()!=r.to_dict():
        raise AssertionError('Replay differs')
    directory=ROOT/'comparisons'/group
    directory.mkdir(parents=True,exist_ok=True)
    (directory/f'{r.configuration_id}.json').write_text(json.dumps(r.to_dict(),indent=2,allow_nan=False)+'\n')
    return r


def main():
    rows=[]
    for path in PATHS:
        for financing in ('closed','limited_common'):
            rows.append(summarize(save_run(configuration(path,financing),'price_financing')))
    for financing in ('closed','ample_common'):
        rows.append(summarize(save_run(configuration(financing=financing,general_authorization=False),'authorization')))
    for buyback in (False,True):
        rows.append(summarize(save_run(configuration(multiple=.75,buyback=buyback),'buyback')))
    # Financing terms and price path fixed; isolate valuation multiple separately.
    for m in (.75,1.25):
        rows.append(summarize(save_run(configuration('up25','limited_common',multiple=m),'valuation')))
    (ROOT/'comparisons/summary.json').write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')
    with (ROOT/'comparisons/summary.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    # Contract-informed perturbations; missing amortization prevents tight bounds.
    loan_rows=[]
    for fixed_face in (8_944_000,11_100_000):
      for dt in ('2026-07-31','2026-12-31'):
        for sofr in (.02,.06):
            cfg=configuration()
            cfg['configuration_id']=f'loan_split_{fixed_face}_{dt}_{sofr}'
            cfg['payments']=[p for p in cfg['payments'] if p['claim_id']!='other_secured']
            cfg['opening']['claims']=[c for c in cfg['opening']['claims'] if c['id']!='other_secured']
            for ident,face,rate,maturity in [('secured_fixed',fixed_face,.052,'2027-06-30'),
                                           ('secured_floating',40_044_000-fixed_face,sofr+.0424,dt)]:
                cfg['opening']['claims'].append(dict(id=ident,kind='debt',currency='USD',face_native=face))
                prior='2026-06-30'
                for t in [p['date'] for p in cfg['path'] if p['operating_cashflow_usd']<0 and p['date']<=maturity]:
                    cfg['payments'].append(dict(id=ident+'_interest_'+t,claim_id=ident,kind='interest',
                                               payment_date=t,amount_native=face*rate/12,
                                               accrual_start=prior,accrual_end=t))
                    prior=t
                cfg['payments'].append(dict(id=ident+'_principal',claim_id=ident,kind='principal',payment_date=maturity,amount_native=face))
            cfg['metadata']['loan_sensitivity']=dict(fixed_loan_opening_principal=fixed_face,
                floating_loan_opening_principal=40_044_000-fixed_face,floating_loan_repayment_date=dt,
                fixed_loan_repayment_date='2027-06-30',fixed_coupon=.052,assumed_one_year_sofr=sofr,
                status='Contract-informed allocation/rate/timing perturbations with interest-only placeholders; actual amortization unknown, not rigorous bounds')
            loan_rows.append(summarize(save_run(cfg,'loan_sensitivity')))
    (ROOT/'comparisons/loan_summary.json').write_text(json.dumps(loan_rows,indent=2)+'\n')
    # An inverse threshold within ONE specified family, no universal price target.
    low,high=1.0,1.25
    for _ in range(35):
        ratio=(low+high)/2
        cfg=configuration()
        cfg['configuration_id']='threshold_trial'
        for p in cfg['path']:
            tau=(date.fromisoformat(p['date'])-START).days/(END-START).days
            p['btc_price_usd']=58714*ratio**tau
        r=run_configuration(cfg)
        if r.assessment['jointly_supported']: high=ratio
        else: low=ratio
    endpoints=[]
    for label,ratio in [('below',low),('above',high)]:
        cfg=configuration()
        cfg['configuration_id']='smooth_growth_equity_threshold_'+label
        cfg['metadata']['path_knots']=[['2026-06-30',1],['2027-09-30',ratio]]
        cfg['metadata']['threshold_scope']='Constant log-growth, closed financing, assumed general-use sale approval, fixed valuation multiple 1; numerical boundary only'
        for p in cfg['path']:
            tau=(date.fromisoformat(p['date'])-START).days/(END-START).days
            p['btc_price_usd']=58714*ratio**tau
        endpoints.append(summarize(save_run(cfg,'threshold')))
    (ROOT/'comparisons/threshold.json').write_text(json.dumps(dict(terminal_ratio_bracket=[low,high],
        terminal_price_bracket=[58714*low,58714*high],endpoints=endpoints,
        interpretation='Numerical crossing inside the supplied smooth-growth family; precision is not empirical certainty'),indent=2)+'\n')
    print(json.dumps([dict(path=r['path'],financing=r['financing'],complete=r['completed'],
                           btc_sold=round(r['btc_sold_through_last_point']),equity_return=r['equity_return']) for r in rows],indent=2))


if __name__=='__main__':
    main()
