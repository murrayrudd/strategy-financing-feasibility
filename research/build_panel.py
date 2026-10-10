from pathlib import Path
import json,re,datetime
import pandas as pd,numpy as np
from lxml import etree
D=Path(__file__).parent/'data'
meta=json.loads((D/'filing_manifest.json').read_text());rows=[]
early={'2020-06-30':0,'2020-09-30':38250,'2020-12-31':70469,'2021-03-31':91326,'2021-06-30':105085,'2021-09-30':114042,'2021-12-31':124391}
for m in sorted(meta,key=lambda r:r['date']):
 d=m['date'];facts=json.loads((D/'filings'/(d+'_facts.json')).read_text());ff=[f for f in facts if f['context'].get('instant')==d]
 def one(names,dim=False,default=None):
  a=[f['value'] for f in ff if f['name'] in names and (dim or not f['context']['dims'])]
  a=sorted(set(a));assert len(a)<=1,(d,names,a)
  return a[0] if a else default
 btc=one(['mstr:NumberOfBitcoinHeld','mstr:NumberOfBitcoinsHeld','us-gaap:CryptoAssetNumberOfUnits'],default=early.get(d))
 if btc is None:
  candidates={f['value'] for f in facts if f['name'] in ['mstr:NumberOfCarryingValueBitcoins','mstr:NumberOfBitcoinsHeld'] and f['context'].get('enddate')==d and not f['context']['dims']}
  assert len(candidates)==1,(d,candidates)
  btc=candidates.pop()
 sc={}
 for f in ff:
  if f['name']=='us-gaap:CommonStockSharesOutstanding':
   dims=f['context']['dims'];members=[v for k,v in dims if k=='us-gaap:StatementClassOfStockAxis']
   if len(dims)==1 and members and members[0] in ['us-gaap:CommonClassAMember','us-gaap:CommonClassBMember']:sc[members[0]]=f['value']
 assert len(sc)==2,d
 split=10 if m['filed']<'2024-08-08' else 1
 n=sum(sc.values())*split
 debt=one(['us-gaap:LongTermDebt'],default=0)
 cash=one(['us-gaap:CashAndCashEquivalentsAtCarryingValue'],default=0)
 rcash=one(['us-gaap:RestrictedCashAndCashEquivalentsAtCarryingValue'],default=0)
 pref={}
 for f in ff:
  if f['name']=='us-gaap:TemporaryEquityLiquidationPreference':pref[tuple(tuple(k) for k in f['context']['dims'])]=f['value']
 pref=sum(pref.values())
 # Keep debt at reported carrying value for empirical normalization only.
 # 2020-12 predates the consolidated LongTermDebt tag; use the $650m face disclosure, labeled.
 debt_note='reported GAAP carrying amount'
 if d=='2020-12-31':debt=650e6;debt_note='face principal proxy for early debt tag'
 rows.append(dict(date=d,filed=m['filed'],available=(pd.Timestamp(m['filed'])+pd.Timedelta(days=1)).strftime('%Y-%m-%d'),btc=btc,shares_split_adjusted=n,cash=cash,restricted_cash=rcash,debt_carrying=debt,preferred_liquidation=pref,debt_note=debt_note,url=m['url']))
q=pd.DataFrame(rows);q.to_csv(D/'quarterly_accounts.csv',index=False)
def yahoo(ticker):
 raw=json.loads((D/f'{ticker}_2020_2025_daily.json').read_text())['chart']['result'][0];prices=raw['indicators'].get('adjclose',[{}])[0].get('adjclose',raw['indicators']['quote'][0]['close'])
 return pd.Series(prices,index=pd.to_datetime(raw['timestamp'],unit='s',utc=True).tz_convert('America/New_York').tz_localize(None).normalize(),name=ticker)
p=pd.concat([yahoo(x) for x in ['mstr','qqq','vix','hyg']],axis=1).dropna()
# Coin Metrics UTC end-of-day prices are only available on the next calendar day.
b=pd.read_csv(Path(__file__).parent/'legacy_engine/historical_data/btc_priceusd_2014_2025.csv',parse_dates=['date']).set_index('date')['price_usd']
p['btc_price']=b.reindex(p.index-pd.Timedelta(days=1)).values
p['btc_eod']=b.reindex(p.index).values
for route,key in [('asof','available'),('retrospective','date')]:
 qr=q.copy();qr['date_key']=pd.to_datetime(qr[key]);qr=qr.set_index('date_key').sort_index()
 v=qr.reindex(p.index,method='ffill')
 for col in ['btc','shares_split_adjusted','cash','restricted_cash','debt_carrying','preferred_liquidation']:
  p[f'{route}_{col}']=v[col].values
p=p.loc['2020-10-28':].dropna();p['gross_base']=p.asof_btc*p.btc_price/p.asof_shares_split_adjusted
p['gross_premium']=p.mstr/p.gross_base
p.to_csv(D/'daily_panel.csv',index_label='date')
w=p.resample('W-FRI').last();w=w[w.index<='2025-12-31'];w.to_csv(D/'weekly_panel.csv',index_label='date')
print(q[['date','btc','shares_split_adjusted','debt_carrying','preferred_liquidation']].to_string(index=False));print('DAILY',len(p),'WEEKLY',len(w))
