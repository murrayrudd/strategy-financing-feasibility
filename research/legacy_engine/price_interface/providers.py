"""Small adapters; external models export the same documented price schema."""
from datetime import timedelta
from .prices import PricePath, iso, number


def from_engine_path(configuration, scenario_id='embedded_prices'):
    """Exact benchmark path. Daily valuation needs a separately supplied daily series."""
    c = configuration.get('configuration', configuration)
    return PricePath(dict(schema_version='1.0', scenario_id=scenario_id,
        kind='stylized', source='Prices copied exactly from the supplied corporate configuration',
        units='USD_per_BTC', price_timing='scenario_input', availability_lag_days=0,
        interpolation='exact', max_gap_days=None,
        assumptions=['Benchmark reproduction; these are supplied scenario prices, not observations.'],
        points=[{'date': p['date'], 'price_usd': p['btc_price_usd']}
                for p in [c['initial_point']]+c['path']]))


def smooth_match(prices, start, end, scenario_id):
    """Log-linear comparison with exactly the same endpoint prices."""
    days = (iso(end)-iso(start)).days
    if days <= 0:
        raise ValueError('Positive horizon required')
    a, b = prices.at(start), prices.at(end)
    return PricePath(dict(schema_version='1.0', scenario_id=scenario_id, kind='stylized',
        source='Matched smooth comparison', units='USD_per_BTC', price_timing='scenario_input',
        availability_lag_days=0, interpolation='log_linear', max_gap_days=days,
        assumptions=['Synthetic log-linear comparison; endpoints held equal to the source path.'],
        provenance={'matched_price_sha256': prices.sha256},
        points=[{'date': start, 'price_usd': a}, {'date': end, 'price_usd': b}]))


def power_law_path(start, end, opening_price, initial_age_days, exponent, scenario_id):
    """Normalized temporal scaling. Parameters are supplied, never estimated here."""
    start_date, end_date = iso(start), iso(end)
    if end_date <= start_date:
        raise ValueError('Positive horizon required')
    number(opening_price, 'Opening price', positive=True)
    number(initial_age_days, 'Initial age', positive=True)
    number(exponent, 'Exponent')
    points = [dict(date=str(start_date+timedelta(days=i)),
                   price_usd=opening_price*((initial_age_days+i)/initial_age_days)**exponent)
              for i in range((end_date-start_date).days+1)]
    return PricePath(dict(schema_version='1.0', scenario_id=scenario_id, kind='projection',
        source='User-specified normalized power law', units='USD_per_BTC',
        price_timing='scenario_input', availability_lag_days=0, interpolation='exact',
        max_gap_days=None, assumptions=['Temporal scaling only; no demand or market-impact mechanism.',
            'Parameters are supplied scenario assumptions, not empirical estimates.'],
        provenance={'initial_age_days': initial_age_days, 'exponent': exponent,
                    'formula': 'P(t)=P(0)*((age_days+t)/age_days)**exponent'}, points=points))
