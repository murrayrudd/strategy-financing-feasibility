"""Endpoint and timing sensitivity for the historical valuation diagnosis."""
import pandas as pd,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;D=ROOT/'research/data';O=ROOT/'validation/results'
a=pd.read_csv(D/'quarterly_accounts.csv').set_index('date');p=pd.read_csv(D/'daily_panel.csv').set_index('date');rows=[]
for name,start,end in [('quarter_aligned','2022-03-31','2023-06-30'),('selected_episode','2022-04-29','2023-08-01')]:
 x,y=p.loc[start],p.loc[end]
 if name=='quarter_aligned':q0,q1,n0,n1=a.loc[start,'btc'],a.loc[end,'btc'],a.loc[start,'shares_split_adjusted'],a.loc[end,'shares_split_adjusted']
 else:q0,q1,n0,n1=129218,152800,112975480,140853940
 b0,b1=x.btc_price,y.btc_price;g0=x.mstr*n0/(q0*b0);g1=y.mstr*n1/(q1*b1)
 row=dict(convention=name,start=start,end=end,stock_return=y.mstr/x.mstr-1,bitcoin_return=b1/b0-1,holdings_growth=q1/q0-1,shares_growth=n1/n0-1,bitcoin_per_share_change=(q1/n1)/(q0/n0)-1,gross_multiple_start=g0,gross_multiple_end=g1,gross_multiple_factor=g1/g0,fixed_gross_multiple_return=(b1/b0)*(q1/q0)/(n1/n0)-1)
 assert math.isclose(1+row['stock_return'],(1+row['bitcoin_return'])*(1+row['bitcoin_per_share_change'])*row['gross_multiple_factor'])
 rows.append(row)
(O/'endpoint_timing_comparison.json').write_text(json.dumps(rows,indent=2)+'\n')
# Same dated Bitcoin quotes and selected historical company quantities as row 2.
x,y=p.loc['2022-04-29'],p.loc['2023-08-01'];S0=129218*x.btc_price;S1=152800*y.btc_price;K0=2405e6-98942000;K1=2210.6e6-68053000
proof=dict(asset_ratio=S1/S0,share_ratio=14085394/11297548,normalized_strike_start=K0/S0,normalized_strike_end=K1/S1,return_upper_bound=rows[1]['fixed_gross_multiple_return'],price_timing='Prior UTC Bitcoin close on each stock observation date',cash_and_claims='Selected disclosed states; explanatory ex post inputs, zero additional software value')
assert proof['normalized_strike_end']>=proof['normalized_strike_start']
sys.path.insert(0,str(ROOT/'research/legacy_engine'))
from treasury_company.valuation import continuation_equity
values=[]
for vol in [10**(-2+3*i/30) for i in range(31)]:
 for years in [10**(-2+4*i/30) for i in range(31)]:
  c0=continuation_equity(S0,98942000,2405e6,vol,years);c1=continuation_equity(S1,68053000,2210.6e6,vol,years)
  if c0>0:
   ret=c1/c0*11297548/14085394-1;assert ret<=proof['return_upper_bound']+1e-12;values.append(ret)
proof.update(numerical_checks=len(values),maximum_checked_return=max(values))
(O/'matched_option_bound.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
