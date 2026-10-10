"""Declared stress rules, never estimates selected against an endpoint."""
import math
import statistics
from datetime import timedelta
from .prices import iso


def conditions(prices, start, end, valuation, regime):
    history, returns, out, audit = [], [], {}, {}
    peak=0.
    for i in range((iso(end)-iso(start)).days+1):
        when=str(iso(start)+timedelta(days=i))
        price=prices.at(when)
        if history: returns.append(math.log(price/history[-1]))
        history.append(price);peak=max(peak,price)
        momentum=math.log(price/history[max(0,i-90)])
        drawdown=price/peak-1
        vol=statistics.stdev(returns[-60:])*math.sqrt(365.25) if len(returns)>=20 else .65
        stateful=valuation in ('state_face','continuation_state','continuation_franchise')
        multiple=(max(.75,min(2.5,1.25*math.exp(.8*momentum+.7*drawdown-.25*max(0.,vol-.65))))
                  if stateful else 1.25)
        access=not(regime=='drawdown_closure' and drawdown<=-.4)
        capacity=(min(1.,.65/max(.65,vol)) if regime=='capacity' else 1.) if access else 0.
        mode='continuation' if valuation.startswith('continuation') else 'face'
        out[when]=dict(multiple=multiple,valuation_mode=mode,capacity_multiplier=capacity,
                       franchise_expected_gross_usd=400e6*capacity if valuation=='continuation_franchise' else 0.)
        audit[when]=dict(momentum_log_90_days=momentum,drawdown=drawdown,
                         realized_volatility_60_days=vol,available_observations=len(history),access=access)
    return out,audit
