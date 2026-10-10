"""Separate economic valuation from the contractual cash ledger.

All premiums, external marks, option horizons, and expectations are conditional
inputs. No function here changes assets, claims, cash, or outstanding shares.
"""
import math


def continuation_equity(bitcoin_value, other_assets, claims, volatility, years):
    """Zero-carry lognormal residual expectation at one common horizon.

    E[max(S_T - K, 0)], with E[S_T]=S_0 and K=claims-other_assets.
    This is an aggregate sensitivity benchmark, not an instrument-specific
    convertible/preferred model. Negative face backing is permitted.
    """
    if bitcoin_value < 0 or volatility < 0 or years <= 0:
        raise ValueError('Invalid continuation inputs')
    strike = claims - other_assets
    if strike <= 0:
        return bitcoin_value - strike
    if bitcoin_value == 0 or volatility == 0:
        return max(0., bitcoin_value-strike)
    v = volatility*math.sqrt(years)
    d1 = (math.log(bitcoin_value/strike)+.5*v*v)/v
    d2 = d1-v
    normal = lambda x: .5*math.erfc(-x/math.sqrt(2))
    return max(0., bitcoin_value*normal(d1)-strike*normal(d2))


def value_common(state, point, contractual_mark):
    b = contractual_mark['backing_usd']
    total_claims = contractual_mark['claims_usd']
    risky = state.btc*point.btc_price_usd
    assets = b+total_claims
    mode = point.valuation_mode
    if mode == 'face':
        base = max(0., b)
    elif mode == 'continuation':
        base = continuation_equity(risky, assets-risky, total_claims,
                                   point.valuation_volatility, point.valuation_horizon_years)
    elif mode == 'claim_marks':
        marks = point.market_claim_values_usd
        if marks is None or set(marks) != {c.id for c in state.claims}:
            raise ValueError('Every retained claim needs one market principal value')
        principal_market = sum(marks.values())
        accrual = sum(c.accrued_native*point.fx_usd_per_unit[c.currency] for c in state.claims)
        base = max(0., assets-principal_market-accrual-state.unallocated_payable_usd)
    elif mode == 'external':
        if point.external_common_price_usd is None or point.external_common_price_usd <= 0:
            raise ValueError('External valuation requires a positive observed price')
        base = point.external_common_price_usd*state.common_shares
    else:
        raise ValueError('Unknown valuation mode')
    demand_value = base if mode == 'external' else point.multiple*base
    # One prospective issue, priced without its own expectation value. Incoming
    # net funds add dollar-for-dollar to reference equity; they are not cash now.
    budget = min(point.franchise_expected_gross_usd,
                 point.franchise_capacity_fraction*demand_value)
    gain = 0.
    if mode != 'external' and base > 0 and demand_value > 0 and budget > 0:
        dilution = budget/demand_value
        gain = max(0., (base+budget*(1-point.franchise_issue_fee))/(1+dilution)-base)
    franchise = min(point.franchise_max_fraction*base,
                    point.franchise_success_probability*gain/point.franchise_discount_factor)
    value = demand_value+franchise
    price = value/state.common_shares if value > 0 else None
    return dict(valuation_mode=mode, reference_common_value_usd=base,
                market_common_value_usd=value, common_market_price_usd=price,
                conditional_common_price_usd=price, quote_defined=price is not None,
                market_multiple=point.multiple,
                financing_expectation_value_usd=franchise,
                expected_financing_budget_usd=budget,
                continuation_increment_usd=max(0., base-max(0., b)) if mode=='continuation' else 0.,
                gross_bitcoin_multiple=value/risky if risky > 0 else None,
                net_face_multiple=value/b if b > 0 else None,
                implied_senior_value_before_market_wedges_usd=assets-base if mode=='continuation' else None)
