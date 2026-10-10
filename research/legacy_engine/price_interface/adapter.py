"""Price adapter and observation-only daily marks. The corporate engine is unchanged."""
from bisect import bisect_right
from copy import deepcopy
from datetime import timedelta
import math

from treasury_company.io import run_configuration
from treasury_company.growth import Opening, Point, mark
from treasury_company.dated import Claim, Payment, earned
from .prices import PricePath, digest, iso, number


def _configuration(raw):
    if 'configuration' in raw:
        c = deepcopy(raw['configuration'])
        c['configuration_id'] = raw['configuration_id']
    else:
        c = deepcopy(raw)
    if c.get('engine_version') != '0.4.0':
        raise ValueError('This adapter requires the preserved 0.4.0 growth engine')
    return c


def _buffer_rule(spec, cfg):
    spec = deepcopy(spec or {'mode': 'embedded'})
    mode = spec.get('mode')
    if mode == 'embedded':
        if set(spec) != {'mode'}:
            raise ValueError('Embedded buffer takes no parameters')
    elif mode == 'fixed':
        if set(spec) != {'mode', 'amount_usd'}:
            raise ValueError('Fixed buffer requires amount_usd')
        if number(spec['amount_usd'], 'Cash buffer') < 0:
            raise ValueError('Cash buffer cannot be negative')
    elif mode == 'principal':
        required = {'mode', 'margin_usd', 'principal_schedule_valid_through'}
        options = {'planning_end', 'lookahead_days'} & set(spec)
        if len(options) != 1 or set(spec) != required | options:
            raise ValueError('Principal buffer needs margin, schedule coverage, and planning_end OR lookahead_days')
        if number(spec['margin_usd'], 'Buffer margin') < 0:
            raise ValueError('Buffer margin cannot be negative')
        coverage = iso(spec['principal_schedule_valid_through'])
        if 'planning_end' in spec:
            horizon = iso(spec['planning_end'])
            if horizon <= iso(cfg['opening']['asof']) or horizon > coverage:
                raise ValueError('Planning end must follow opening and lie within declared principal coverage')
        else:
            if type(spec['lookahead_days']) is not int or spec['lookahead_days'] <= 0:
                raise ValueError('Lookahead must be a positive number of days')
        # Coverage is a caller assertion, recorded with results, not inferred from
        # the last payment or from a claim's mere presence on the balance sheet.
    else:
        raise ValueError('Unknown cash-buffer mode')
    return spec


def _set_buffer(point, spec, cfg):
    if spec['mode'] == 'embedded':
        return
    if spec['mode'] == 'fixed':
        point['unreserved_cash_buffer_usd'] = spec['amount_usd']
        return
    current = iso(point['date'])
    end = (iso(spec['planning_end']) if 'planning_end' in spec else
           current + timedelta(days=spec['lookahead_days']))
    if end > iso(spec['principal_schedule_valid_through']):
        raise ValueError('Principal planning window exceeds declared schedule coverage')
    claims = {x['id']: x for x in cfg['opening']['claims']}
    point['unreserved_cash_buffer_usd'] = spec['margin_usd'] + sum(
        p['amount_native'] * point['fx_usd_per_unit'][claims[p['claim_id']]['currency']]
        for p in cfg['payments'] if p['kind'] == 'principal' and p.get('declared', True)
        and p.get('settlement', 'cash') == 'cash'
        and current < iso(p['payment_date']) <= end)


def compile_scenario(template, prices, *, reporting_end=None, buffer_rule=None,
                     opening_price_mode='match', daily_valuation=True):
    """Replace only Bitcoin prices and an explicitly selected buffer rule.

    Endpoints must already exist in the supplied corporate event calendar. A
    longer run requires a separately supplied, fully specified corporate template.
    """
    if not isinstance(prices, PricePath):
        raise TypeError('prices must be a PricePath')
    if type(daily_valuation) is not bool:
        raise ValueError('daily_valuation must be boolean')
    cfg = _configuration(template)
    base = deepcopy(cfg)
    if not cfg['path']:
        raise ValueError('Corporate template has no events')
    start = cfg['opening']['asof']
    end = reporting_end or cfg['path'][-1]['date']
    if iso(end) <= iso(start):
        raise ValueError('Reporting end must follow opening')
    if end > cfg['path'][-1]['date']:
        raise ValueError('Corporate schedule ends before the requested horizon; supply an extended template')
    if end not in {p['date'] for p in cfg['path']}:
        raise ValueError('Reporting end must be an explicitly supplied corporate event date')
    rule = _buffer_rule(buffer_rule, cfg)
    cfg['path'] = [p for p in cfg['path'] if p['date'] <= end]
    opening_price = prices.at(start)
    if opening_price_mode not in ('match', 'revalue'):
        raise ValueError('Opening price mode must be match or revalue')
    if opening_price_mode == 'match' and not math.isclose(
            opening_price, cfg['initial_point']['btc_price_usd'], rel_tol=1e-12, abs_tol=1e-8):
        raise ValueError('Opening price differs; explicitly rebase the path or choose revalue')
    for p in [cfg['initial_point']] + cfg['path']:
        p['btc_price_usd'] = prices.at(p['date'])
        _set_buffer(p, rule, base)
    if daily_valuation:
        for i in range((iso(end)-iso(start)).days+1):
            prices.at(str(iso(start)+timedelta(days=i)))
    provenance = dict(interface_version='0.1.0', base_configuration_id=base['configuration_id'],
        base_configuration_sha256=digest(base), price_sha256=prices.sha256,
        price_path=prices.to_dict(), reporting_start=start, reporting_end=end,
        supplied_corporate_schedule_end=base['path'][-1]['date'], cash_buffer_rule=rule,
        opening_price_mode=opening_price_mode, daily_valuation=daily_valuation,
        financial_conditions_between_events='Previous supplied event values; no interpolation',
        inherited_metadata_status='Earlier labels and assumptions are provenance only; compiled numeric inputs govern',
        settlement_treatment='Inherited same-event execution and receipt; no intraday or settlement-lag model',
        horizon_treatment='No automatic extensions, renewed authorizations, or new trading dates')
    cfg.setdefault('metadata', {})['common_price_interface'] = provenance
    cfg['configuration_id'] = 'price_' + digest(cfg)[:24]
    return cfg


def daily_marks(result, prices):
    """Observation-only daily valuation with inherited linear claim accrual.

    Event-date observations use exact engine snapshots. Intervening dates accrue
    outstanding distributions without issuing, trading, paying, or refilling cash.
    """
    cfg = result.configuration
    points = [cfg['initial_point']] + cfg['path']
    point_dates = [p['date'] for p in points]
    snapshots = {cfg['opening']['asof']: result.initial_snapshot}
    snapshots.update({s['date']: s for s in result.snapshots})
    state_dates = sorted(snapshots)
    payments = [Payment(**p) for p in cfg['payments'] + result.generated_payments]
    opening = cfg['opening']['asof']
    last = result.snapshots[-1]['date']
    records = []
    for offset in range((iso(last)-iso(opening)).days+1):
        when = str(iso(opening)+timedelta(days=offset))
        is_event = when in snapshots
        if is_event:
            m = snapshots[when]
        else:
            anchor_date = state_dates[bisect_right(state_dates, when)-1]
            state = deepcopy(snapshots[anchor_date]['state'])
            state['claims'] = [Claim(**c) for c in state['claims']]
            claims = {c.id: c for c in state['claims']}
            for p in payments:
                if p.kind != 'principal':
                    c = claims[p.claim_id]
                    c.accrued_native += (earned(p, when, opening, c)
                                         - earned(p, anchor_date, opening, c))
            state['asof'] = when
            point = deepcopy(points[bisect_right(point_dates, when)-1])
            point.update(date=when, btc_price_usd=prices.at(when))
            m = mark(Opening(**state), Point(**point))
        records.append(dict(date=when, corporate_event=is_event,
            mark_timing='After corporate event, or observation only between events',
            btc_price_usd=prices.at(when), backing_usd=m['backing_usd'],
            conditional_common_price_usd=m['conditional_common_price_usd'],
            quote_defined=m['quote_defined'], claims_usd=m['claims_usd'],
            common_shares=m['state']['common_shares'], btc=m['state']['btc']))
    return records


def _drawdown(quotes):
    if not quotes or any(p is None for p in quotes):
        return None
    high, worst = quotes[0], 0.0
    for p in quotes:
        high = max(high, p)
        worst = min(worst, p/high-1)
    return worst


def reporting_metrics(result, observed, annual_hurdle):
    number(annual_hurdle, 'Annual return hurdle')
    if annual_hurdle <= -1:
        raise ValueError('Annual hurdle must exceed -100%')
    c = result.configuration
    opening, end = c['opening']['asof'], c['path'][-1]['date']
    years = (iso(end)-iso(opening)).days / 365.25
    marks = [result.initial_snapshot] + result.snapshots
    equity_return = result.assessment['conditional_terminal_equity_return']
    btc_return = c['path'][-1]['btc_price_usd']/c['initial_point']['btc_price_usd']-1
    funding = result.complete and result.assessment['reserve_compliant_throughout']
    observed_defined = all(x['quote_defined'] for x in observed) if observed else None
    daily_supported = (funding and observed_defined and equity_return is not None
                       and equity_return >= -1e-12) if observed else None
    return dict(completed=result.complete, reporting_start=opening, reporting_end=end,
        last_processed_date=result.snapshots[-1]['date'], horizon_years=years,
        equity_return=equity_return,
        annualized_equity_return=((1+equity_return)**(1/years)-1) if equity_return is not None else None,
        bitcoin_return=btc_return if result.complete else None,
        scheduled_bitcoin_return_input=btc_return,
        excess_over_bitcoin=equity_return-btc_return if equity_return is not None else None,
        annual_hurdle=annual_hurdle, horizon_hurdle=(1+annual_hurdle)**years-1,
        hurdle_supported=bool(funding and equity_return is not None
                              and equity_return >= (1+annual_hurdle)**years-1-1e-12),
        bitcoin_relative_supported=bool(funding and equity_return is not None and equity_return >= btc_return-1e-12),
        event_joint_supported=result.assessment['jointly_supported'],
        event_max_drawdown=_drawdown([x['conditional_common_price_usd'] for x in marks]),
        daily_max_drawdown=_drawdown([x['conditional_common_price_usd'] for x in observed]) if observed else None,
        daily_mapping_defined_over_processed_period=observed_defined,
        daily_nominal_joint_supported=daily_supported,
        first_daily_undefined_mapping_date=next((x['date'] for x in observed if not x['quote_defined']), None),
        daily_marks_are_observations_not_extra_payment_or_policy_tests=True,
        failure=result.failure, probabilities_assigned=False)


def endpoint_obligations(result):
    """Report retained claims and listed future payments; never imply a complete tail."""
    c = result.configuration
    snap = result.snapshots[-1]
    when = snap['date']
    point = next(p for p in c['path'] if p['date'] == when)
    state = snap['state']
    claims = {x['id']: x for x in state['claims']}
    def usd(x):
        return x['amount_native']*point['fx_usd_per_unit'][claims[x['claim_id']]['currency']]
    tail = [deepcopy(p) for p in c['payments']+result.generated_payments
            if when < p['payment_date'] <= str(iso(when)+timedelta(days=365))
            and p.get('declared', True) and p.get('settlement', 'cash') == 'cash']
    paid = {i for e in result.ledger if e['action'] == 'settle_dated_commitments'
            for i in e['details']['payment_ids']}
    failed_due = [p for p in c['payments']+result.generated_payments
                  if p['payment_date'] <= when and p['id'] not in paid and p.get('declared', True)]
    return dict(asof=when, is_completed_horizon=result.complete,
        debt_principal_usd=sum(x['face_native']*point['fx_usd_per_unit'][x['currency']]
                              for x in state['claims'] if x['kind'] == 'debt'),
        preferred_claims_usd=sum(x['face_native']*point['fx_usd_per_unit'][x['currency']]
                               for x in state['claims'] if x['kind'] != 'debt'),
        accrued_claims_usd=sum(x['accrued_native']*point['fx_usd_per_unit'][x['currency']]
                             for x in state['claims'])+state['unallocated_payable_usd'],
        liquid_assets_usd=state['cash_usd']+state['treasuries_usd'],
        unreserved_liquid_assets_usd=state['cash_usd']+state['treasuries_usd']-state['reserve_designation_usd'],
        annualized_strc_distributions_usd=snap['annualized_strc_distributions_usd'],
        listed_future_cash_payments_next_365_days_usd=sum(usd(p) for p in tail),
        listed_future_payments=tail, unsettled_due_payments=failed_due,
        future_schedule_complete=False,
        tail_warning='Listed payments only. Missing dates do not imply zero obligations; no full next-year coverage is certified.',
        remaining_claims_already_in_backing=True)


def run_price_scenario(template, prices, *, annual_hurdle=.05, **options):
    cfg = compile_scenario(template, prices, **options)
    result = run_configuration(cfg)
    observed = daily_marks(result, prices) if options.get('daily_valuation', True) else []
    return dict(interface_version='0.1.0', price_scenario_id=prices.to_dict()['scenario_id'],
                corporate_result=result.to_dict(), daily_valuations=observed,
                metrics=reporting_metrics(result, observed, annual_hurdle),
                endpoint_obligations=endpoint_obligations(result))


def replay(record):
    """Replay both the unchanged corporate ledger and the observation/report layer."""
    raw = record['corporate_result']
    prices = PricePath(raw['configuration']['metadata']['common_price_interface']['price_path'])
    result = run_configuration(raw)
    daily = daily_marks(result, prices) if raw['configuration']['metadata']['common_price_interface']['daily_valuation'] else []
    rebuilt = dict(interface_version='0.1.0', price_scenario_id=prices.to_dict()['scenario_id'],
        corporate_result=result.to_dict(), daily_valuations=daily,
        metrics=reporting_metrics(result, daily, record['metrics']['annual_hurdle']),
        endpoint_obligations=endpoint_obligations(result))
    if rebuilt != record:
        raise AssertionError('Retained record does not replay exactly')
    return rebuilt
