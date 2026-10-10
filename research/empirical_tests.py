"""Prefix-only conditional valuation backtests. Future corporate/BTC paths are scenario inputs.
No model coefficient sees an observation after its forecast origin.
"""
from pathlib import Path
import json,sys
import numpy as np,pandas as pd
from scipy.special import ndtr
R=Path(__file__).parent;D=R/'data';O=R/'results';O.mkdir(exist_ok=True)
w=pd.read_csv(D/'weekly_panel.csv',index_col='date',parse_dates=True)
from premium_process import continuation_reference as cont
def arfit(z):
 mu=np.mean(z);x=mu-z[:-1];dy=np.diff(z)
 k=np.clip(x@dy/max(x@x,1e-12),0,1);phi=1-k
 eps=dy-k*x
 return mu,phi,np.std(eps,ddof=2)
xret=np.log(w[['btc_price','qqq','hyg','vix']]).diff().values
models=['hold','mean_reversion','btc_response','btc_qqq','macro_response','reversion_macro']
records=[];worked=[]
for route in ['asof','retrospective']:
 s=w[route+'_btc'].values*w.btc_price.values;n=w[route+'_shares_split_adjusted'].values
 claims=w[route+'_debt_carrying'].values+w[route+'_preferred_liquidation'].values
 c=w[route+'_cash'].values+w[route+'_restricted_cash'].values
 for basis,base in [('gross',s/n),('continuation',cont(s,c,claims)/n)]:
  z=np.log(w.mstr.values/base)
  for i in range(64,len(w)):
   train=z[max(0,i-103):i+1];mu,phi,sigma=arfit(train);idx=np.arange(max(1,i-103),i+1);dy=z[idx]-z[idx-1];xx=xret[idx]
   bbtc=np.linalg.lstsq(xx[:,:1],dy,rcond=None)[0]
   bmacro=np.linalg.lstsq(xx,dy,rcond=None)[0]
   btwo=np.linalg.lstsq(xx[:,:2],dy,rcond=None)[0]
   # First shrink toward the observed historical center, then estimate residual macro response.
   mr=(1-phi)*(mu-z[idx-1]);barx=np.linalg.lstsq(xx,dy-mr,rcond=None)[0]
   params={'hold':(0,1,np.std(dy,ddof=1),np.zeros(4)),
           'mean_reversion':(mu*(1-phi),phi,sigma,np.zeros(4)),
           'btc_response':(0,1,np.std(dy-xx[:,:1]@bbtc,ddof=1),np.r_[bbtc,0,0,0]),
           'btc_qqq':(0,1,np.std(dy-xx[:,:2]@btwo,ddof=2),np.r_[btwo,0,0]),
           'macro_response':(0,1,np.std(dy-xx@bmacro,ddof=4),bmacro),
           'reversion_macro':(mu*(1-phi),phi,np.std(dy-mr-xx@barx,ddof=5),barx)}
   for h in [4,13,26,52,65]:
    if i+h>=len(w):continue
    # Monthly origins reduce pseudo-replication; remaining overlap is reported.
    if i%4 and h!=65:continue
    for model,(a,p,sd,beta) in params.items():
     pred=z[i];var=0
     for j in range(i+1,i+h+1):pred=a+p*pred+float(xret[j]@beta);var=p*p*var+sd*sd
     se=np.sqrt(var);predp=base[i+h]*np.exp(pred);error=pred-z[i+h]
     records.append(dict(route=route,basis=basis,model=model,origin=str(w.index[i].date()),target=str(w.index[i+h].date()),horizon_weeks=h,predicted=predp,observed=w.mstr.iloc[i+h],log_error=error,abs_log_error=abs(error),covered90=abs(error)<=1.644854*se,lower90=base[i+h]*np.exp(pred-1.644854*se),upper90=base[i+h]*np.exp(pred+1.644854*se),phi=p,mu=mu,sigma=sd))
rec=pd.DataFrame(records);rec.to_csv(O/'conditional_backtests.csv',index=False)
# Define reporting subsets by target date; training remains a rolling information prefix.
reports=[]
for period,mask in [('all',rec.target>='2022'),('2022_2023',rec.target<'2024'),('2024_2025',rec.origin>='2024'),('2024',rec.origin.str.startswith('2024')),('2025',rec.origin.str.startswith('2025'))]:
 for k,g in rec[mask & rec.horizon_weeks.isin([4,13,26,52])].groupby(['route','basis','model','horizon_weeks']):
  reports.append(dict(period=period,route=k[0],basis=k[1],model=k[2],horizon_weeks=int(k[3]),n=len(g),mae_log=float(g.abs_log_error.mean()),rmse_log=float(np.sqrt(np.mean(g.log_error**2))),coverage90=float(g.covered90.mean()),median_abs_pct=float(np.median(abs(g.predicted/g.observed-1))*100)))
pd.DataFrame(reports).to_csv(O/'backtest_metrics.csv',index=False)
sel=pd.DataFrame(reports);print(sel[(sel.period=='2024_2025') & (sel.route=='asof')].to_string(index=False))
print('\nWORKED 65weeks FROM APRIL29 2022');print(rec[(rec.origin=='2022-04-29')&(rec.horizon_weeks==65)&(rec.route=='asof')][['basis','model','predicted','observed','lower90','upper90','phi','mu']].to_string(index=False))
