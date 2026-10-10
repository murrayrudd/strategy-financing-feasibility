"""Matched, illustrative ATM/STRC comparisons with complete retained paths."""
from copy import deepcopy
from datetime import date
import csv
import json
from pathlib import Path

from run_comparisons import configuration as previous_configuration, HOLIDAYS, PATHS, factor_at
from treasury_company.io import run_configuration

ROOT=Path(__file__).resolve().parent


def configuration(path_id='flat', channel='both', variant='sustained'):
    c=previous_configuration(path_id, 'closed', multiple=1.25)
    c['configuration_id']=f'{path_id}__{channel}__{variant}'
    c['engine_version']='0.4.0'
    c['opening']['strc_shares']=104_894_705
    if variant=='rate14':
        # Evaluate the reserve change on its effective date, even though capital
        # markets are closed; do not defer this condition to the next cash date.
        added=dict(deepcopy(c['initial_point']),date='2027-01-01',operating_cashflow_usd=0,
                   btc_price_usd=58_714*factor_at('2027-01-01',PATHS[path_id][1]))
        c['path'].append(added);c['path'].sort(key=lambda p:p['date'])
    templates=[]
    for pay in c['payments']:
        if pay['claim_id']!='STRC': continue
        rate=.14 if variant=='rate14' and pay['accrual_end']>='2027-01-01' else .12
        templates.append(dict(id=pay['id'],record_date=pay['accrual_start'],
                              accrual_end=pay['accrual_end'],payment_date=pay['payment_date'],annual_rate=rate))
        if not pay['opening_credit_native']:
            pay['amount_native']=c['opening']['strc_shares']*100*rate/24
            pay['note']='Opening STRC shares; cash dividend at supplied period rate; opening credits excluded'
    templates.sort(key=lambda t:t['record_date'])
    c['strc_terms']=dict(claim_id='STRC',stated_amount_usd=100,opening_annual_rate=.12,
                         templates=templates,business_holidays=sorted(str(d) for d in HOLIDAYS))
    # One illustrative growth opportunity per month, at its last business-day
    # regular record date. Months with neither date usable have no STRC offering.
    opportunities={}
    for t in templates:
        d=date.fromisoformat(t['record_date'])
        if str(d)>c['opening']['asof'] and d.weekday()<5 and d not in HOLIDAYS:
            opportunities[str(d)[:7]]=str(d)
    opportunity_dates=set(opportunities.values())
    for p in [c['initial_point']]+c['path']:
        d=date.fromisoformat(p['date'])
        business=d.weekday()<5 and d not in HOLIDAYS
        common=channel in ('common','both')
        strc=channel in ('strc','both')
        opportunity=p['date'] in opportunity_dates
        p.update(common_program_target_gross_usd=400_000_000 if common and opportunity else 0,
                 common_issue_cap_gross_usd=1_100_000_000 if common and business else 0,
                 common_authorization_gross_limit_usd=6_000_000_000 if common else 0,
                 strc_issue_target_gross_usd=400_000_000 if strc and opportunity else 0,
                 strc_issue_cap_gross_usd=400_000_000 if strc and business else 0,
                 strc_authorization_gross_limit_usd=6_000_000_000 if strc else 0,
                 strc_execution_price_usd=100,strc_liquidation_preference_usd=100,
                 strc_annual_rate=.14 if variant=='rate14' and p['date']>='2027-01-01' else .12,
                 btc_purchase_cap=100_000,unreserved_cash_buffer_usd=0)
        if variant=='interrupted' and p['date']>'2027-03-31':
            p.update(common_issue_cap_gross_usd=0,strc_issue_cap_gross_usd=0)
        if variant=='price_gates_close' and p['date']>='2027-01-15':
            p.update(multiple=.85,strc_execution_price_usd=97)
        if variant in ('cash_buffer','buffer_no_extra_sale_permission'):
            p['unreserved_cash_buffer_usd']=1_100_000_000
        if variant in ('no_extra_sale_permission','buffer_no_extra_sale_permission'):
            p['btc_general_use_gross_limit_usd']=0
        if variant=='zero_market_demand':
            p.update(common_issue_cap_gross_usd=0,strc_issue_cap_gross_usd=0)
        if variant=='equal_capital':
            each_target=200_000_000 if channel=='both' else 400_000_000
            if common:
                p['common_program_target_gross_usd']=each_target if opportunity else 0
                p['common_authorization_gross_limit_usd']=13*each_target
            if strc:
                p['strc_issue_target_gross_usd']=each_target if opportunity else 0
                p['strc_issue_cap_gross_usd']=each_target
                p['strc_authorization_gross_limit_usd']=13*each_target
    c['policy'].update(name=f'ATM/STRC: {channel}; {variant}',
                       common_fund_cash_shortfalls=variant!='equal_capital',
                       common_growth_min_net_premium=1,common_access_min_multiple=1,
                       strc_issue_fee_rate=.01,strc_min_execution_price_usd=99,
                       strc_max_execution_price_usd=101,require_positive_backing_for_strc=True,
                       strc_reserve_months=0 if variant=='fixed_reserve' else 12,
                       purchase_bitcoin=True,purchase_fraction=1,
                       deploy_existing_surplus_cash=False,btc_purchase_cost_rate=.001)
    c['metadata']['v03_assumptions_for_provenance_only']=c['metadata'].pop('assumptions')
    c['metadata']['assumptions']=[
        'June 30 opening and August 3 company-information cutoff unchanged; later actual disclosures are not used for calibration.',
        'Core financing channels are common ATM and STRC; other new preferred issues and new debt are excluded.',
        'All financing targets, investor capacities, execution prices and authorization budgets are illustrative scenario assumptions, not forecasts or observed remaining programs.',
        'Each active channel requests $400m gross on each selected monthly growth date; 13 opportunities in this horizon. Common ATM also covers dated funding need within $1.1bn per business-date capacity. Each channel has a $6bn cumulative gross limit.',
        'STRC issues only on business-day record dates before their cutoff. First distribution is the following full semimonthly period; arbitrary first-period exceptions are not modeled.',
        'Common execution follows the residual-backing quote at multiple 1.25 unless the price-gate variant changes it. Market-access floor 1 and growth net-premium floor 1 are scenario rules, not disclosed company mNAV thresholds.',
        'STRC execution and supplied liquidation preference are $100, annual dividend 12%, and issuance fees 1% for both channels unless the rate or price-gate variant changes an input.',
        'Reserve floor increases by 12 months of additional annualized STRC distributions unless the fixed-reserve sensitivity removes that addition. Legacy base floor and opening designation remain unchanged.',
        'Commitments and reserve needs precede Bitcoin purchases. Purchases use at most current net financing receipts, remaining unreserved cash, and trading capacity, with 0.1% execution cost. Unspent cash carries forward.',
        'The cash-buffer variant protects $1.1bn from discretionary purchases; that buffer is an allocation target, not a contractual payment or mandatory joint criterion.',
        'The equal-capital variant raises $5.2bn gross on the same 13 dates: all common, all STRC, or half each. Additional common funding issuance is disabled in that comparison. This separates financing mix from total financing scale.',
        'The rate14 variant changes all non-predeclared original and new STRC distributions to 14% for periods ending from January 2027; the reserve target reflects the same current rate.',
        'The interrupted variant closes both investor-capacity inputs after March 31, 2027. The price-gate variant retains capacity but lowers the common multiple to 0.85 and STRC execution price to $97 from January 15, 2027.',
        'Additional general-use Bitcoin sale authority remains the explicit $2bn assumption except the no-extra-sale-permission variant. Sale capacity and permitted use remain separate.',
        'The supplied STRC preference is not a computation from daily market prices. Other preferred shares/rates, secured loans, taxes, FX and operating cash-flow assumptions retain their documented limitations.',
        'The common-share denominator remains basic shares. No conversion, stock compensation, or assumed-diluted KPI is inferred. No probability weights, Bitcoin-price feedback, or Monster–CRRA equivalence are introduced.'
    ]
    c['metadata'].update(purpose='Matched financing-channel comparisons',financing=channel,variant=variant,
                         growth_opportunity_dates=sorted(opportunity_dates),source_review='FINANCING_SOURCES.md',
                         constant_multiple=None if variant=='price_gates_close' else 1.25,
                         general_sale_authorization_assumed=variant not in ('no_extra_sale_permission','buffer_no_extra_sale_permission'))
    return c


def summarize(r):
    initial=r.initial_snapshot; end=r.snapshots[-1]; a=r.assessment
    common=[e for e in r.ledger if e['action']=='issue_common_atm']
    strc=[e for e in r.ledger if e['action']=='issue_strc']
    purchases=[e for e in r.ledger if e['action']=='purchase_bitcoin']
    sales=[e for e in r.ledger if e['action'].startswith('sell_bitcoin')]
    generated={p['id']:p for p in r.generated_payments}
    paid_ids={i for e in r.ledger if e['action']=='settle_dated_commitments' for i in e['details']['payment_ids']}
    return dict(id=r.configuration_id,path=r.configuration['metadata']['path_id'],
                channel=r.configuration['metadata']['financing'],variant=r.configuration['metadata']['variant'],
                completed=r.complete,last_processed_date=end['date'],
                common_gross_usd=sum(e['details']['gross_usd'] for e in common),
                strc_gross_usd=sum(e['details']['gross_usd'] for e in strc),
                btc_purchased=sum(e['balances']['btc'] for e in purchases),
                btc_sold=sum(-e['balances']['btc'] for e in sales),
                final_btc=end['state']['btc'],net_btc_change=end['state']['btc']-initial['state']['btc'],
                common_share_change=end['state']['common_shares']-initial['state']['common_shares'],
                strc_share_change=end['state']['strc_shares']-initial['state']['strc_shares'],
                btc_per_share_change=(a['terminal_btc_per_share_ratio']-1) if a['terminal_btc_per_share_ratio'] is not None else None,
                equity_return=a['conditional_terminal_equity_return'],
                final_backing_per_share=end['backing_per_common_share_usd'],
                annualized_strc_distributions_usd=end['annualized_strc_distributions_usd'],
                new_strc_dividends_paid_usd=sum(p['amount_native'] for i,p in generated.items() if i in paid_ids),
                final_reserve_floor_usd=end['reserve_floor_usd'],
                final_liquid_assets_usd=end['liquid_assets_usd'],
                reserve_compliant=a['reserve_compliant_throughout'] and r.complete,
                primary_joint_supported=a['jointly_supported'],
                failure=r.failure,generated_payments=len(r.generated_payments))


def cases():
    for path in ('flat','up25','down25','early_recovery','late_recovery'):
        for channel in ('closed','common','strc','both'):
            yield configuration(path,channel)
    for variant in ('interrupted','price_gates_close','rate14','fixed_reserve','cash_buffer','zero_market_demand'):
        yield configuration('flat','both',variant)
    for channel in ('common','strc','both'):
        yield configuration('flat',channel,'no_extra_sale_permission')
        yield configuration('flat',channel,'equal_capital')
    yield configuration('flat','both','buffer_no_extra_sale_permission')
    yield configuration('deep_decline','both')


def main():
    dest=ROOT/'financing'; (dest/'paths').mkdir(parents=True,exist_ok=True)
    rows=[]
    for c in cases():
        r=run_configuration(c); d=r.to_dict()
        if run_configuration(d).to_dict()!=d: raise AssertionError('Financing replay differs')
        (dest/'paths'/f'{r.configuration_id}.json').write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
        rows.append(summarize(r))
    (dest/'summary.json').write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')
    with (dest/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps(rows,indent=2,allow_nan=False))
    return rows


if __name__=='__main__':main()
