from pathlib import Path
import json,numpy as np,pandas as pd
from scipy.special import ndtr
from scipy.optimize import brentq
R=Path(__file__).parent;D=R/'data';O=R/'results'
w=pd.read_csv(D/'weekly_panel.csv',parse_dates=['date']).set_index('date');daily=pd.read_csv(D/'daily_panel.csv',parse_dates=['date']).set_index('date')
rec=pd.read_csv(O/'conditional_backtests.csv')
def C(s,c,k,v=.65,t=3):
 K=k-c
 if K<=0:return s-K
 v=v*np.sqrt(t);a=(np.log(s/K)+v*v/2)/v
 return s*ndtr(a)-K*ndtr(a-v)
def fit(z):
 mu=float(np.mean(z));xx=mu-z[:-1];k=float(np.clip(xx@np.diff(z)/max(xx@xx,1e-12),0,1));return mu,1-k
# Exact legacy episode quantities with synchronized, already-available BTC quotations.
p0=float(daily.loc['2022-04-29','mstr'])*10;p1=float(daily.loc['2023-08-01','mstr'])*10
b0=float(daily.loc['2022-04-29','btc_price']);b1=float(daily.loc['2023-08-01','btc_price'])
n0,n1,q0,q1=11297548,14085394,129218,152800;c0,c1=98942000,68053000;d0,d1=2405e6,2210.6e6
j=int(w.index.get_loc('2022-04-29'));idx=np.arange(1,j+1);xx=np.log(w[['btc_price','qqq','hyg','vix']]).diff().values[idx]
target=np.log(daily.loc['2023-08-01',['btc_price','qqq','hyg','vix']].values.astype(float)/daily.loc['2022-04-29',['btc_price','qqq','hyg','vix']].values.astype(float))
h=(pd.Timestamp('2023-08-01')-pd.Timestamp('2022-04-29')).days/7
out=[];attribution=[]
for software in [0,750e6,1250e6,2000e6]:
 for basis in ['gross','continuation']:
  if software and basis=='gross':continue
  s=w.asof_btc.values*w.btc_price.values;n=w.asof_shares_split_adjusted.values
  cash=w.asof_cash.values+w.asof_restricted_cash.values+software;claims=w.asof_debt_carrying.values+w.asof_preferred_liquidation.values
  base=np.array([C(a,b,c) for a,b,c in zip(s,cash,claims)])/n if basis=='continuation' else s/n
  z=np.log(w.mstr.values/base);z=z[:j+1]
  mu,phi=fit(z);beta=np.linalg.lstsq(xx,np.diff(z),rcond=None)[0];btwo=np.linalg.lstsq(xx[:,:2],np.diff(z),rcond=None)[0]
  base0=C(q0*b0,c0+software,d0)/n0 if basis=='continuation' else q0*b0/n0
  base1=C(q1*b1,c1+software,d1)/n1 if basis=='continuation' else q1*b1/n1
  start=np.log(p0/base0)
  for mode in ['hold','mean_reversion','btc_qqq','macro_response']:
   zz=start if mode=='hold' else mu+phi**h*(start-mu) if mode=='mean_reversion' else start+float(target[:2]@btwo) if mode=='btc_qqq' else start+float(target@beta)
   pred=base1*np.exp(zz)
   out.append(dict(basis=basis,software_value=software,model=mode,predicted_price_presplit=pred,predicted_return=pred/p0-1,actual_return=p1/p0-1,phi=phi,long_run_multiple=float(np.exp(mu))))
  if software==0:
   attribution.append(dict(basis=basis,base_log_change=float(np.log(base1/base0)),coefficients=dict(zip(['BTC','QQQ','HYG','VIX'],map(float,beta))),contribution_log_points=dict(zip(['BTC','QQQ','HYG','VIX'],map(float,beta*target)))))
pd.DataFrame(out).to_csv(O/'matched_episode_models.csv',index=False)
# Reproduce prior identity and prove fixed normalized option valuation cannot reverse it.
legacy=json.load(open(R/'legacy_engine/historical_benchmark/reconstruction.json'))['endpoint']
cm=pd.read_csv(R/'legacy_engine/historical_data/btc_priceusd_2014_2025.csv').set_index('date').price_usd
S0=q0*cm['2022-05-01'];S1=q1*cm['2023-08-01'];K0=d0-c0;K1=d1-c1
proof=dict(asset_ratio=S1/S0,shares_ratio=n1/n0,strike_to_assets_start=K0/S0,strike_to_assets_end=K1/S1,fixed_option_return_upper_bound=(S1/S0)/(n1/n0)-1,observed_return=p1/p0-1,endpoint_equity_excess_over_bitcoin_and_cash=p1*n1-S1-c1)
# Model uncertainty mixture of hold and reversion, equal weights chosen for a sensitivity.
mixtures=[]
for (route,basis,horizon,origin),g in rec.groupby(['route','basis','horizon_weeks','origin']):
 g=g.set_index('model');a=g.loc['hold'];b=g.loc['mean_reversion'];m1=np.log(a.predicted);m2=np.log(b.predicted);s1=np.log(a.upper90/a.predicted)/1.644854;s2=np.log(b.upper90/b.predicted)/1.644854
 def quant(q):return brentq(lambda y:.5*ndtr((y-m1)/s1)+.5*ndtr((y-m2)/s2)-q,min(m1,m2)-10*max(s1,s2),max(m1,m2)+10*max(s1,s2))
 median=quant(.5);lo=quant(.05);hi=quant(.95);obs=np.log(a.observed)
 mixtures.append(dict(route=route,basis=basis,horizon_weeks=horizon,origin=origin,target=a.target,predicted=np.exp(median),observed=a.observed,log_error=median-obs,abs_log_error=abs(median-obs),covered90=lo<=obs<=hi,lower90=np.exp(lo),upper90=np.exp(hi)))
mix=pd.DataFrame(mixtures);mix.to_csv(O/'mixture_backtests.csv',index=False)
metrics=[]
for (route,basis,h),g in mix[(mix.origin>='2024')&mix.horizon_weeks.isin([4,13,26,52])].groupby(['route','basis','horizon_weeks']):metrics.append(dict(route=route,basis=basis,horizon_weeks=int(h),n=len(g),mae_log=float(g.abs_log_error.mean()),coverage90=float(g.covered90.mean()),median_abs_pct=float(np.median(abs(g.predicted/g.observed-1))*100)))
pd.DataFrame(metrics).to_csv(O/'mixture_metrics.csv',index=False)
res={'legacy_endpoint':legacy,'algebraic_bound':proof,'matched_dates':{'origin':'2022-04-29','target':'2023-08-01','btc_origin_previous_utc_close':b0,'btc_target_previous_utc_close':b1,'matched_accounts_are_ex_post_inputs':True},'episode_macro_attribution':attribution,'backtests':{'coefficient_information':'all coefficients estimated on observations available by origin; rolling maximum 104 weeks','future_inputs':'realized Bitcoin and later accounting disclosure states; macro variants also condition on future QQQ, HYG and VIX','quarterly_disclosure_only':True,'stock_split_basis':'2024 ten-for-one adjusted throughout, with presplit display for original episode'},'model_count':int(len(rec))}
(O/'diagnostic_summary.json').write_text(json.dumps(res,indent=2));print(pd.DataFrame(out).to_string(index=False));print('\nATTRIBUTION',json.dumps(attribution,indent=2));print('\nMIXTURE',pd.DataFrame(metrics).query("route=='asof' and basis=='continuation'").to_string(index=False));print('\nBOUND',proof)
