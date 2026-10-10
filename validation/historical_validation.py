"""Historical corporate replay at the resolution of public disclosure.

Flow inputs come from contemporaneous XBRL and dated 8-K disclosures. End-point
balances are independent comparison targets. No balancing plug is posted.
"""
from pathlib import Path
from dataclasses import asdict
import json, sys, math, copy
import pandas as pd

R=Path(__file__).parent;ROOT=R.parent
sys.path.insert(0,str(ROOT/'research/legacy_engine'))
from treasury_company.dated import Opening,Claim,Journal
F=ROOT/'research/data/filings';O=R/'results';O.mkdir(exist_ok=True)
DATES=['2022-03-31','2022-06-30','2022-09-30','2022-12-31','2023-03-31','2023-06-30']
facts={d:json.loads((F/(d+'_facts.json')).read_text()) for d in DATES}
citations=[]

def amount(date,name,start=None,instant=False,dimensions=None,default=None):
    found=[]
    for f in facts[date]:
        c=f['context']
        if f['name']!=name:continue
        if instant:
            if c.get('instant')!=date:continue
        elif c.get('startdate')!=(start or date[:4]+'-01-01') or c.get('enddate')!=date:continue
        if dimensions is None and c['dims']:continue
        if dimensions is not None and dict(c['dims'])!=dimensions:continue
        found.append(f)
    vals=sorted(set(f['value'] for f in found))
    if not vals and default is not None:return default
    assert len(vals)==1,(date,name,start,dimensions,vals)
    citations.append({'filing_quarter':date,'tag':name,'context':found[0]['context'],'value':vals[0]})
    return vals[0]

def ytd(date,name,**kw):return amount(date,name,default=0,**kw)
def flow(i,name,**kw):
    d=DATES[i];prev=DATES[i-1]
    return ytd(d,name,**kw)-(ytd(prev,name,**kw) if prev[:4]==d[:4] else 0)

tags={
'cfo':('us-gaap:NetCashProvidedByUsedInOperatingActivities',1),
'btc_purchase_cash':('us-gaap:PaymentsToAcquireIntangibleAssets',-1),
'btc_sale_cash':('us-gaap:ProceedsFromSaleOfIntangibleAssets',1),
'capex':('us-gaap:PaymentsToAcquirePropertyPlantAndEquipment',-1),
'debt_proceeds':('mstr:ProceedsFromOtherLongTermSecuredDebt',1),
'term_loan_net_proceeds':('mstr:ProceedsFromIssuanceOfSecuredTermLoanNetOfLenderFees',1),
'other_debt_issue_cost':('mstr:PaymentsOfDebtIssuanceCostsForOtherLongTermSecuredDebt',-1),
'term_debt_issue_cost':('mstr:PaymentsOfDebtIssuanceCostsForSecuredTermLoanExcludingLenderFees',-1),
'secured_debt_cash_repayment':('us-gaap:RepaymentsOfSecuredDebt',-1),
'other_debt_cash_repayment':('us-gaap:RepaymentsOfOtherLongTermDebt',-1),
'atm_gross':('us-gaap:ProceedsFromIssuanceOfCommonStock',1),
'atm_cash_cost':('us-gaap:PaymentsOfStockIssuanceCosts',-1),
'option_cash':('us-gaap:ProceedsFromStockOptionsExercised',1),
'employee_withholding_cash':('us-gaap:PaymentsRelatedToTaxWithholdingForShareBasedCompensation',-1),
'fx':('us-gaap:EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations',1)}
employee_tags=['us-gaap:StockIssuedDuringPeriodSharesStockOptionsExercised','us-gaap:StockIssuedDuringPeriodSharesEmployeeStockPurchasePlans','mstr:StockIssuedDuringPeriodRestrictedStockUnitVestingNetOfWithholdingTaxes']
equity_dims={'us-gaap:StatementEquityComponentsAxis':'us-gaap:CommonStockMember','us-gaap:StatementClassOfStockAxis':'us-gaap:CommonClassAMember'}
espp_dims={'us-gaap:PlanNameAxis':'mstr:EmployeeStockPurchaseProgramMember'}
quarterly=pd.read_csv(ROOT/'research/data/quarterly_accounts.csv').set_index('date')
opening=Opening(asof=DATES[0],btc=float(quarterly.loc[DATES[0],'btc']),
    cash_usd=float(quarterly.loc[DATES[0],'cash']+quarterly.loc[DATES[0],'restricted_cash']),
    treasuries_usd=0,restricted_cash_usd=0,reserve_designation_usd=0,
    common_shares=float(quarterly.loc[DATES[0],'shares_split_adjusted']/10),
    claims=[Claim('notes','debt','USD',2200e6),Claim('silvergate','debt','USD',205e6),Claim('other','debt','USD',0)])
j=Journal(opening);rows=[];flows=[]
atm_units={'2022-06-30':0,'2022-09-30':0,'2022-12-31':218575,'2023-03-31':1348855,'2023-06-30':1079170}
employee_accumulated=sum(amount(DATES[0],n,dimensions=equity_dims,default=0) for n in employee_tags)

def loan_cash_ytd(d):
    name='us-gaap:ProceedsFromIssuanceOfSecuredDebt' if d=='2022-03-31' else 'mstr:ProceedsFromIssuanceOfSecuredTermLoanNetOfLenderFees'
    return ytd(d,name)
def other_cost_ytd(d):
    if d in ['2022-06-30','2022-09-30']:
        return ytd(d,'us-gaap:PaymentsOfDebtIssuanceCosts',dimensions={'us-gaap:LongtermDebtTypeAxis':'mstr:OtherLongTermSecuredDebtMember'})
    return ytd(d,'mstr:PaymentsOfDebtIssuanceCostsForOtherLongTermSecuredDebt')

for i,d in enumerate(DATES[1:],1):
    cf={k:sgn*flow(i,t) for k,(t,sgn) in tags.items()}
    prev=DATES[i-1]
    cf['term_loan_net_proceeds']=loan_cash_ytd(d)-(loan_cash_ytd(prev) if prev[:4]==d[:4] else 0)
    cf['other_debt_issue_cost']=-other_cost_ytd(d)+(other_cost_ytd(prev) if prev[:4]==d[:4] else 0)
    cf['espp_cash']=flow(i,'us-gaap:ProceedsFromStockPlans',dimensions=espp_dims)
    bought=flow(i,'mstr:NumberOfBitcoinsPurchased');sold=flow(i,'mstr:NumberOfBitcoinsSold')
    if prev[:4]!=d[:4]:employee_accumulated=0
    start=d[:4]+{'03':'-01-01','06':'-04-01','09':'-07-01','12':'-01-01'}[d[5:7]]
    employee=sum(amount(d,n,start=start,dimensions=equity_dims,default=0) for n in employee_tags)
    if d[5:7]=='12':employee-=employee_accumulated
    employee_accumulated+=employee
    # Principal and repayment cash are different fields. The March settlement
    # retires all $205m face even though principal cash paid is $159.9m.
    face={'other':cf['debt_proceeds']+cf['other_debt_cash_repayment']}
    if d=='2023-03-31':face['silvergate']=-205e6
    j.post(d,'reported_quarterly_transactions',
        {'cash_usd':sum(cf.values()),'btc':bought-sold,'common_shares':atm_units[d]+employee},
        faces=face,details={'cash_flows_usd':cf,'purchased_btc':bought,'sold_btc':sold,
          'atm_shares_exact':atm_units[d],'employee_shares_rounded':employee,
          'execution_timing':'Quarter aggregate; entry date is reporting boundary, not an execution date',
          'cash_pool':'Cash, cash equivalents, and restricted cash combined for this historical reconciliation only'})
    target=quarterly.loc[d]
    # Independent total principal from the maturity table, whose rounded
    # components can differ by $1,000 from the flow-based roll-forward.
    mats={f['name']:f['value'] for f in facts[d] if f['context'].get('instant')==d and not f['context']['dims'] and f['name'].startswith('us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipal')}
    principal=sum(mats.values())
    actual_cash=float(target.cash+target.restricted_cash)
    preddebt=sum(c.face_native for c in j.state.claims)
    row={'date':d,'observed_btc':float(target.btc),'replayed_btc':j.state.btc,
        'observed_total_cash':actual_cash,'replayed_total_cash':j.state.cash_usd,
        'observed_shares_rounded':float(target.shares_split_adjusted/10),'replayed_shares':j.state.common_shares,
        'observed_debt_maturity_sum':principal,'replayed_debt_face':preddebt,
        'btc_error':j.state.btc-target.btc,'cash_error':j.state.cash_usd-actual_cash,
        'share_error':j.state.common_shares-target.shares_split_adjusted/10,
        'debt_error':preddebt-principal,'debt_rounding_tolerance':500*(len(mats)+1)}
    assert row['btc_error']==0 and row['cash_error']==0,(row,cf)
    assert abs(row['share_error'])<=2000
    assert abs(row['debt_error'])<=row['debt_rounding_tolerance']
    rows.append(row);flows.append(dict(date=d,**cf,purchased_btc=bought,sold_btc=sold,atm_shares=atm_units[d],employee_shares_rounded=employee))

# Public disclosures distinguish exact settlement dates from trade intervals.
events=[
{'id':'q2_2022_purchase','kind':'purchase','start':'2022-05-03','end':'2022-06-28','announced':'2022-06-29','btc':480,'cash_usd':-10e6,'rounded':True},
{'id':'q3_2022_purchase','kind':'purchase','start':'2022-08-02','end':'2022-09-19','announced':'2022-09-20','btc':301,'cash_usd':-6e6,'rounded':True},
{'id':'q4_2022_atm','kind':'common_issue','start':'2022-10-01','end':'2022-12-27','announced':'2022-12-28','shares':218575,'net_cash_usd':46.4e6,'rounded_cash':True},
{'id':'late_2022_purchase','kind':'purchase','start':'2022-11-01','end':'2022-12-21','announced':'2022-12-28','btc':2395,'cash_usd':-42.8e6,'rounded':True},
{'id':'tax_sale','kind':'sale','start':'2022-12-22','end':'2022-12-22','announced':'2022-12-28','btc':-704,'cash_usd':11.8e6,'rounded':True},
{'id':'december_purchase','kind':'purchase','start':'2022-12-24','end':'2022-12-24','announced':'2022-12-28','btc':810,'cash_usd':-13.6e6,'rounded':True},
{'id':'q1_2023_atm','kind':'common_issue','start':'2023-01-01','end':'2023-03-24','announced':'2023-03-27','shares':1348855,'net_cash_usd':339.4e6,'rounded_cash':True},
{'id':'early_2023_purchase','kind':'purchase','start':'2023-02-16','end':'2023-03-23','announced':'2023-03-27','btc':6455,'cash_usd':-150e6,'rounded':True},
{'id':'silvergate_settlement','kind':'discounted_debt_settlement','start':'2023-03-24','end':'2023-03-24','announced':'2023-03-27','face_retired':205e6,'principal_cash':159.9e6,'interest_cash':1.1e6,'released_collateral_btc':34619,'restricted_cash_released':5e6,'rounded_cash':True},
{'id':'march_april_purchase','kind':'purchase','start':'2023-03-24','end':'2023-04-04','announced':'2023-04-05','btc':1045,'cash_usd':-29.3e6,'rounded':True},
{'id':'q2_2023_atm','kind':'common_issue','start':'2023-05-01','end':'2023-06-27','announced':'2023-06-28','shares':1079170,'net_cash_usd':333.7e6,'rounded_cash':True},
{'id':'q2_2023_purchase','kind':'purchase','start':'2023-04-29','end':'2023-06-27','announced':'2023-06-28','btc':12333,'cash_usd':-347e6,'rounded':True},
]
manifest={r['filing_date']:r for r in json.loads((R/'sources/event_source_manifest.json').read_text())}
for e in events:
    e['source_url']=manifest[e['announced']]['url']
    e['timing_precision']='exact_date' if e['start']==e['end'] else 'reported_interval'

# State transitions at dated events exercise the same Journal used by the
# scenario engine. Event-local balances are test fixtures, not invented daily
# company accounts. Independently observed changes are the comparison targets.
local=[]
def local_replay(event,opening,balances,faces=None,accruals=None):
    jj=Journal(opening);jj.post(event['end'],event['kind'],balances,faces,accruals,details={'source_event':event['id']})
    local.append({'event':event['id'],'opening':asdict(opening),'ledger':jj.entries,'reconciliation':jj.reconcile()})
    return jj
sale=next(e for e in events if e['id']=='tax_sale')
os=Opening(sale['start'],132395,0,0,0,0,1,[Claim('debt','debt','USD',0)])
js=local_replay(sale,os,{'btc':sale['btc'],'cash_usd':sale['cash_usd']})
buy=next(e for e in events if e['id']=='december_purchase')
ob=Opening(buy['start'],js.state.btc,13.6e6,0,0,0,1,[Claim('debt','debt','USD',0)])
jb=local_replay(buy,ob,{'btc':buy['btc'],'cash_usd':buy['cash_usd']})
assert jb.state.btc==132501 # Approximate announcements differ from quarter stock by 1 BTC.
silver=next(e for e in events if e['id']=='silvergate_settlement')
os=Opening(silver['start'],138955,156e6,0,5e6,0,1,[Claim('silvergate','debt','USD',205e6,1.1e6)],pledged_btc=34619)
js=local_replay(silver,os,{'cash_usd':-156e6,'restricted_cash_usd':-5e6,'pledged_btc':-34619},faces={'silvergate':-205e6},accruals={'silvergate':-1.1e6})
assert js.state.btc==os.btc and js.state.cash_usd==0 and js.state.restricted_cash_usd==0
assert js.state.claims[0].face_native==0 and js.state.claims[0].accrued_native==0

# Equity changes are mechanical even when an observed quote is not implied by
# the continuation reference; exact observed ATM units determine execution.
for e in [x for x in events if x['kind']=='common_issue']:
    idx=DATES.index({'q4_2022_atm':'2022-12-31','q1_2023_atm':'2023-03-31','q2_2023_atm':'2023-06-30'}[e['id']])-1
    before=quarterly.loc[DATES[idx]]
    ee=Opening(e['start'],float(before.btc),0,0,0,0,float(before.shares_split_adjusted/10),[Claim('debt','debt','USD',0)])
    jj=local_replay(e,ee,{'cash_usd':e['net_cash_usd'],'common_shares':e['shares']})
    assert jj.state.common_shares-ee.common_shares==e['shares']

# Deliberate historical-input omissions expose what aggregate holdings conceal.
end=j.state;error_cases=[]
for name,dc,dq,dn,dd in [
 ('omit_employee_issuance',0,0,-sum(f['employee_shares_rounded'] for f in flows),0),
 ('retire_only_principal_cash_paid',0,0,0,205e6-159.9e6),
 ('add_released_collateral_to_holdings',0,34619,0,0),
 ('count_debt_extinguishment_gain_as_cash',44.686e6,0,0,0),
 ('charge_payoff_interest_twice',-1.1e6,0,0,0)]:
    error_cases.append(dict(case=name,cash_error_usd=dc,btc_error=dq,share_error=dn,debt_error_usd=dd))

summary={'quarterly_intervals':5,'cash_and_holdings_exact_at_reported_precision':True,
 'maximum_share_error':max(abs(x['share_error']) for x in rows),
 'maximum_debt_error_usd':max(abs(x['debt_error']) for x in rows),
 'employee_shares_rounded':sum(f['employee_shares_rounded'] for f in flows),
 'atm_shares_exact':sum(f['atm_shares'] for f in flows),
 'atm_gross_usd':sum(f['atm_gross'] for f in flows),
 'cash_reconciliation':j.reconcile(),'event_records':len(events),'event_local_replays':len(local),
 'rounding_differences_btc':{'q2_2022_announcement_minus_quarter_purchase':480-flows[0]['purchased_btc'],'q4_2022_announced_buys_minus_quarter_purchase':2395+810-flows[2]['purchased_btc']},
 'scope':'Quarterly joint states and event-local transitions; no daily cash reconstruction or historical-policy prediction',
 'restricted_cash_split_independently_replayed':False,'quarterly_balancing_plugs':False}
pd.DataFrame(rows).to_csv(O/'historical_replay.csv',index=False)
pd.DataFrame(flows).to_csv(O/'historical_flow_inputs.csv',index=False)
pd.DataFrame(error_cases).to_csv(O/'historical_omission_tests.csv',index=False)
for name,obj in [('historical_validation_summary',summary),('historical_events',events),('historical_ledger',{'opening':asdict(opening),'ledger':j.entries}),('event_local_replays',local),('xbrl_input_evidence',citations)]:
    (O/(name+'.json')).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
print(pd.DataFrame(rows).to_string(index=False));print(json.dumps(summary,indent=2))
