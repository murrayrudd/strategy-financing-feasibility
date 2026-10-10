"""Construct specified T+1 placement calendars, with no future market inputs."""
from bisect import bisect_right
from copy import deepcopy
from datetime import date,timedelta
from treasury_company.settlement_growth import next_business_day
from price_interface.prices import PricePath

def compile_settlement(raw, prefund=False):
 c=deepcopy(raw);c['engine_version']='0.6.0'
 start=c['opening']['asof'];end=c['path'][-1]['date'];old=[c['initial_point']]+deepcopy(c['path'])
 dates=[p['date'] for p in old];prices=PricePath(c['metadata']['common_price_interface']['price_path'])
 # Conservative financing calendar: existing bank holidays plus market-only or
 # observed closures. This supplied capacity assumption is distinct from the
 # certificate's Federal Reserve calendar for dividend delivery.
 holidays=sorted(set(c['strc_terms']['business_holidays'])|{'2026-07-03','2027-03-26','2027-06-18'})
 def business(d):return d.weekday()<5 and str(d) not in holidays
 def prev(d):
  d-=timedelta(days=1)
  while not business(d):d-=timedelta(days=1)
  return d
 def settle(d):return next_business_day(d+timedelta(days=1),holidays)
 points={p['date']:deepcopy(p) for p in c['path']}
 def get(when):
  k=str(when)
  if k not in points:
   p=deepcopy(old[bisect_right(dates,k)-1]);p['date']=k
   p.update(operating_cashflow_usd=0,common_program_target_gross_usd=0,strc_issue_target_gross_usd=0,
            common_issue_cap_gross_usd=0,strc_issue_cap_gross_usd=0,btc_purchase_cap=0)
   # Apply the rate for this known calendar period, not the previous event rate.
   active=next(t for t in c['strc_terms']['templates'] if t['record_date']<k<=t['accrual_end'])
   p['strc_annual_rate']=active['annual_rate']
   points[k]=p
  p=points[k];p['btc_price_usd']=prices.at(k);p.update(c['metadata']['market_conditions'][k])
  p['equity_trading_open']=business(when) and str(settle(when))<=end
  return p
 for original in old[1:]:
  when=date.fromisoformat(original['date']);p=get(when)
  # Scheduled programs are placed one business day before their delivery event.
  # All preferred delivery events were already validated as regular record dates.
  if original.get('common_program_target_gross_usd',0) or original.get('strc_issue_target_gross_usd',0):
   delivery=when if business(when) else prev(when)
   trade=prev(delivery)
   if str(trade)<=start:raise ValueError('Trade precedes opening')
   q=get(trade)
   q['common_program_target_gross_usd']+=original.get('common_program_target_gross_usd',0)
   q['strc_issue_target_gross_usd']+=original.get('strc_issue_target_gross_usd',0)
   q['common_issue_cap_gross_usd']=max(q['common_issue_cap_gross_usd'],original['common_issue_cap_gross_usd'])
   q['strc_issue_cap_gross_usd']=max(q['strc_issue_cap_gross_usd'],original['strc_issue_cap_gross_usd'])
   if q['strc_issue_target_gross_usd']:q['scheduled_strc_settlement_date']=str(delivery)
   p['common_program_target_gross_usd']=p['strc_issue_target_gross_usd']=0
   get(delivery)['btc_purchase_cap']=original['btc_purchase_cap']
  if prefund:
   delivery=when if business(when) else prev(when);trade=prev(delivery);q=get(trade)
   q['financing_for_date']=str(when)
   q['common_issue_cap_gross_usd']=max(q['common_issue_cap_gross_usd'],c['initial_point']['common_issue_cap_gross_usd'])
   p['common_issue_cap_gross_usd']=0
   get(delivery)
 # Every permitted placement date has an explicit receipt event. No issuance
 # capacity is introduced on these additional receipt-only dates.
 for p in list(points.values()):
  d=date.fromisoformat(p['date'])
  if p['equity_trading_open'] and (p['common_issue_cap_gross_usd'] or p['strc_issue_cap_gross_usd']):get(settle(d))
 c['path']=[points[k] for k in sorted(points)]
 c['policy'].update(equity_settlement_lag_business_days=1,equity_settlement_holidays=holidays)
 c['metadata']['settlement_control']={'variant':'prefunded' if prefund else 'scheduled_programs_only',
  'lag_business_days':1,'holidays':holidays,
  'prefunding':'One-business-day advance decision for known event cash needs at then-current quote/capacity' if prefund else 'Only scheduled discretionary programs advance; cash-shortfall rescue orders retain event-date timing',
  'unsettled_proceeds':'No spendable cash or issued basic shares until delivery; price locked at placement',
  'preferred_first_dividend':'Delivery restricted to original regular record dates; new shares receive following full period',
  'scope':'Supplied conservative financing calendar; no execution-failure probabilities or intraday settlement guarantee'}
 c['metadata']['common_price_interface']['settlement_treatment']='Explicit next-business-day placement queue and receipt events'
 c['configuration_id']='tplus1_'+('prefunded_' if prefund else 'scheduled_')+raw.get('configuration_id','control')
 return c
