"""Market-anchored empirical premium paths for the retained corporate engine.

A premium is a market valuation state, not spendable cash or proof of fundamental
value. Regime weights below are scenario choices, not estimated probabilities.
"""
from dataclasses import dataclass,asdict
import math
from datetime import date,timedelta
import numpy as np


def continuation_reference(bitcoin_value, other_assets, senior_claims, volatility=.65, years=3.):
    """Vectorized equivalent of the retained engine's zero-carry reference.
    Excess non-Bitcoin assets remain assets when the residual strike is negative.
    """
    from scipy.special import ndtr
    s,c,k=np.broadcast_arrays(np.asarray(bitcoin_value,dtype=float),np.asarray(other_assets,dtype=float),np.asarray(senior_claims,dtype=float))
    if np.any(s<0) or volatility<0 or years<=0:raise ValueError('Invalid continuation inputs')
    strike=k-c
    if volatility==0:return np.maximum(s-strike,0.)
    safe=np.maximum(strike,1e-12);v=volatility*np.sqrt(years)
    with np.errstate(divide='ignore'):
        d1=(np.log(s/safe)+v*v/2)/v
    option=s*ndtr(d1)-safe*ndtr(d1-v)
    return np.where(strike<=0,s-strike,np.maximum(option,0.))

@dataclass
class PremiumFit:
    training_end: str
    observations: int
    target_log_multiple: float
    phi_weekly: float
    persistence_innovations: list
    reversion_innovations: list
    reference_volatility: float=.65
    reference_horizon_years: float=3.

def fit_premium(log_multiple,dates,window=104):
    z=np.asarray(log_multiple[-window:],dtype=float)
    if len(z)<52 or not np.isfinite(z).all():raise ValueError('At least 52 finite weekly observations required')
    mu=float(z.mean());x=mu-z[:-1];dy=np.diff(z)
    k=float(np.clip(x@dy/max(x@x,1e-12),0,1))
    # Center innovations to keep sampled noise distinct from assumed drift.
    e=dy-k*x;e=e-e.mean();rw=dy-dy.mean()
    return PremiumFit(str(dates[-1]),len(z),mu,1-k,rw.tolist(),e.tolist())

def sample_premium_path(fit,start,end,opening_multiple,mode,seed,block_weeks=4):
    if mode not in ['persistence','reversion']:raise ValueError('Unknown premium regime')
    if opening_multiple<=0:raise ValueError('Observed market anchor must be positive')
    a,b=date.fromisoformat(start),date.fromisoformat(end)
    if b<=a:raise ValueError('End must follow start')
    if date.fromisoformat(fit.training_end[:10])>a:raise ValueError('Training must precede scenario origin')
    rng=np.random.default_rng(seed);res=np.array(fit.persistence_innovations if mode=='persistence' else fit.reversion_innovations)
    z=math.log(opening_multiple);phi=1. if mode=='persistence' else fit.phi_weekly
    needed=(b-a).days//7+1;eps=[]
    while len(eps)<needed:
        k=int(rng.integers(len(res)));eps.extend(res[(k+np.arange(block_weeks))%len(res)])
    out={};week=0
    for i in range((b-a).days+1):
        if i and i%7==0:
            z=fit.target_log_multiple+phi*(z-fit.target_log_multiple)+eps[week];week+=1
        # No hidden floor/cap is applied to a sampled market premium.
        out[str(a+timedelta(days=i))]=math.exp(z)
    return out

def deterministic_premium_path(fit,start,end,opening_multiple,mode):
    a,b=date.fromisoformat(start),date.fromisoformat(end);z=math.log(opening_multiple);out={}
    for i in range((b-a).days+1):
        v=z if mode=='persistence' else fit.target_log_multiple+fit.phi_weekly**(i/7)*(z-fit.target_log_multiple)
        out[str(a+timedelta(days=i))]=math.exp(v)
    return out

def apply_to_corporate_template(template,path,observed_opening_share_price):
    """Attach a daily premium path after verifying its observed opening anchor.
    Contractual claims and payments are unchanged. Common issuance uses the quote
    inside the original cash ledger; no post-processing repricing substitutes for it.
    """
    from copy import deepcopy
    from treasury_company.market_growth import Opening,Point,mark
    from treasury_company.dated import Claim
    c=deepcopy(template);c['engine_version']='0.6.0' if template.get('engine_version')=='0.6.0' else '0.5.0';s=deepcopy(c['opening']);s['claims']=[Claim(**x) for x in s['claims']]
    ip=deepcopy(c['initial_point']);ip.update(multiple=1.,valuation_mode='continuation',franchise_expected_gross_usd=0.)
    reference=mark(Opening(**s),Point(**ip))['conditional_common_price_usd']
    anchor=observed_opening_share_price/reference
    if not math.isclose(path[c['opening']['asof']],anchor,rel_tol=1e-10):raise ValueError('Premium path does not match observed opening share price')
    signals={d:dict(multiple=m,valuation_mode='continuation',franchise_expected_gross_usd=0.) for d,m in path.items()}
    c.setdefault('metadata',{})['market_conditions']=signals
    c['metadata']['empirical_premium']={'opening_price':observed_opening_share_price,'opening_multiple':anchor,'future_premiums_are_scenarios':True}
    for p in [c['initial_point']]+c['path']:p.update(signals[p['date']])
    return c
