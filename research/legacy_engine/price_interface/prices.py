"""Strict dated prices, explicit availability, bounded interpolation, provenance."""
from bisect import bisect_left
from copy import deepcopy
from datetime import date, timedelta
import csv
import hashlib
import json
import math
from pathlib import Path


def iso(value):
    if not isinstance(value, str):
        raise ValueError('Dates must be ISO YYYY-MM-DD strings')
    result = date.fromisoformat(value)
    if str(result) != value:
        raise ValueError('Dates must use YYYY-MM-DD')
    return result


def number(value, label, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + ' must be a finite number')
    if positive and value <= 0:
        raise ValueError(label + ' must be positive')
    return value


def digest(raw):
    return hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


class PricePath:
    """Dates are observations; availability lag maps them to usable scenario dates.

    Historical daily closes require at least one calendar-day lag. There is no
    intraday execution model. Interpolation is an explicit scenario assumption.
    """
    def __init__(self, raw):
        required = {'schema_version', 'scenario_id', 'kind', 'source', 'units',
                    'price_timing', 'availability_lag_days', 'interpolation',
                    'max_gap_days', 'assumptions', 'points'}
        optional = {'provenance'}
        if set(raw) - required - optional or required - set(raw):
            raise ValueError('Price fields missing or unknown: ' + str(set(raw) ^ required))
        if raw['schema_version'] != '1.0' or raw['units'] != 'USD_per_BTC':
            raise ValueError('Require schema 1.0 and USD_per_BTC')
        for k in ('scenario_id', 'source'):
            if not isinstance(raw[k], str) or not raw[k].strip():
                raise ValueError(k + ' must be a nonempty string')
        if raw['kind'] not in ('historical', 'projection', 'model_output', 'stylized', 'historical_stress'):
            raise ValueError('Unknown price kind')
        if raw['price_timing'] not in ('daily_close', 'scenario_input'):
            raise ValueError('Unknown price timing')
        lag = raw['availability_lag_days']
        if type(lag) is not int or lag < 0:
            raise ValueError('Availability lag must be a nonnegative integer')
        if raw['kind'] == 'historical' and (raw['price_timing'] != 'daily_close' or lag < 1):
            raise ValueError('Historical daily closes require at least one day of availability lag')
        mode = raw['interpolation']
        if mode not in ('exact', 'previous', 'log_linear'):
            raise ValueError('Unknown interpolation mode')
        if raw['kind'] in ('historical', 'historical_stress') and mode == 'log_linear':
            raise ValueError('Historical paths cannot interpolate using a future observation')
        gap = raw['max_gap_days']
        if mode == 'exact':
            if gap is not None:
                raise ValueError('Exact prices use max_gap_days=null')
        elif type(gap) is not int or gap <= 0:
            raise ValueError('Interpolation requires a positive integer max_gap_days')
        if not isinstance(raw['assumptions'], list) or not all(isinstance(x, str) for x in raw['assumptions']):
            raise ValueError('Assumptions must be a list of strings')
        if not isinstance(raw['points'], list) or len(raw['points']) < 2:
            raise ValueError('Supply at least two price observations')
        dates, prices = [], []
        for p in raw['points']:
            if set(p) != {'date', 'price_usd'}:
                raise ValueError('Each price point requires only date and price_usd')
            d = iso(p['date']) + timedelta(days=lag)
            if dates and d <= dates[-1]:
                raise ValueError('Price observations must be unique and strictly increasing')
            dates.append(d)
            prices.append(number(p['price_usd'], 'Bitcoin price', positive=True))
        self._raw = deepcopy(raw)
        self.dates, self.prices = tuple(dates), tuple(prices)
        self.sha256 = digest(raw)

    def to_dict(self):
        return deepcopy(self._raw)

    def at(self, when):
        d = iso(when)
        if d < self.dates[0] or d > self.dates[-1]:
            raise ValueError('Price coverage does not include ' + when + '; extrapolation is disabled')
        i = bisect_left(self.dates, d)
        if self.dates[i] == d:
            return self.prices[i]
        mode = self._raw['interpolation']
        if mode == 'exact':
            raise ValueError('Missing exact price on ' + when)
        elapsed = (d - self.dates[i-1]).days
        gap = self._raw['max_gap_days']
        if mode == 'previous':
            if elapsed > gap:
                raise ValueError('Stale previous price on ' + when)
            return self.prices[i-1]
        span = (self.dates[i] - self.dates[i-1]).days
        if span > gap:
            raise ValueError('Interpolation gap exceeds the declared maximum')
        return self.prices[i-1] * (self.prices[i]/self.prices[i-1]) ** (elapsed/span)

    def historical_window(self, source_start, source_end, scenario_start, opening_price, scenario_id):
        """Map an available historical daily return sequence onto new scenario dates."""
        if self._raw['kind'] != 'historical':
            raise ValueError('Historical windows require an observed historical source')
        start, end, target = iso(source_start), iso(source_end), iso(scenario_start)
        if end <= start:
            raise ValueError('Historical window must have positive length')
        number(opening_price, 'Opening price', positive=True)
        base = self.at(source_start)
        pts = []
        for i in range((end-start).days+1):
            p = self.at(str(start+timedelta(days=i)))
            pts.append({'date': str(target+timedelta(days=i)), 'price_usd': opening_price*p/base})
        return PricePath(dict(schema_version='1.0', scenario_id=scenario_id,
            kind='historical_stress', source=self._raw['source'], units='USD_per_BTC',
            price_timing='scenario_input', availability_lag_days=0, interpolation='exact',
            max_gap_days=None, assumptions=self._raw['assumptions'] + [
                'Observed return sequence rebased and shifted; this is a stress experiment, not a company backtest.'],
            provenance={'source_price_sha256': self.sha256, 'source_start_available_date': source_start,
                        'source_end_available_date': source_end, 'source_path': self.to_dict()}, points=pts))


def load_prices(path, metadata_path=None):
    p = Path(path)
    if p.suffix.lower() == '.json':
        if metadata_path is not None:
            raise ValueError('JSON prices already contain metadata')
        return PricePath(json.loads(p.read_text(encoding='utf-8')))
    if p.suffix.lower() != '.csv' or metadata_path is None:
        raise ValueError('Supply a price JSON, or a CSV with its metadata JSON')
    raw = json.loads(Path(metadata_path).read_text(encoding='utf-8'))
    if 'points' in raw:
        raise ValueError('CSV metadata must not contain a second price series')
    with p.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ['date', 'price_usd']:
            raise ValueError('CSV columns must be date,price_usd')
        points = []
        for row in reader:
            if set(row) != {'date', 'price_usd'} or None in row.values():
                raise ValueError('Malformed CSV row')
            points.append({'date': row['date'], 'price_usd': float(row['price_usd'])})
    raw['points'] = points
    return PricePath(raw)
