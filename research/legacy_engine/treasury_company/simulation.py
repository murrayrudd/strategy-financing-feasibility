"""Causal, event-driven policy runner with complete configuration retention."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from hashlib import sha256
from math import isfinite
import json
from .core import Ledger, Position, State, Terms, TOL, day, fraction, nonnegative


@dataclass(frozen=True)
class Offer:
    terms: Terms
    capacity: float
    price_per_face: float = 1.0

    def __post_init__(self):
        nonnegative('senior capacity', self.capacity)
        nonnegative('price_per_face', self.price_per_face, positive=True)


@dataclass(frozen=True)
class Event:
    date: str
    btc_price: float
    multiple: float = 1.0
    operating_value: float = 0.0
    operating_cashflow: float = 0.0
    # Decision-date forecast of future net operating cash USES, excluding instruments.
    forecast_operating_needs: float = 0.0
    equity_capacity: float = 0.0
    equity_authorization: float = 1e100
    repurchase_capacity: float = 0.0
    btc_sale_capacity: float = 1e100  # BTC, shared across mandatory/discretionary sales
    btc_buy_capacity: float = 1e100
    senior_budget: float = 0.0
    offers: tuple[Offer, ...] = ()
    conversions: dict[str, float] = field(default_factory=dict)
    pay_preferred: bool = False
    other_common_shares: float = 0.0  # compensation only; no unmodeled extinguished claims

    def __post_init__(self):
        day(self.date)
        for name in ('btc_price', 'multiple'):
            nonnegative(name, getattr(self, name), positive=True)
        for name in ('operating_value', 'equity_capacity', 'equity_authorization',
                     'repurchase_capacity', 'btc_sale_capacity', 'btc_buy_capacity',
                     'senior_budget', 'other_common_shares'):
            nonnegative(name, getattr(self, name))
        for name in ('operating_cashflow', 'forecast_operating_needs'):
            if not isfinite(getattr(self, name)):
                raise ValueError(f'{name} must be finite')
        kinds = [o.terms.kind for o in self.offers]
        if len(kinds) != len(set(kinds)):
            raise ValueError('At most one new offer per instrument class per event')
        if len({o.terms.id for o in self.offers}) != len(self.offers):
            raise ValueError('Duplicate offered instrument id')


@dataclass(frozen=True)
class Policy:
    name: str = 'cash_reserve_and_accumulation'
    reserve_days: int = 180
    cash_buffer: float = 0.0
    buy_fraction: float = 1.0
    equity_fraction: float = 0.0  # request as fraction of positive preissue backing
    repurchase_fraction: float = 0.0  # consideration / decision-date market cap
    sale_fraction_for_repurchase: float = 0.0
    debt_weight: float = 1.0  # fixed split of senior budget; no reallocation
    min_asset_coverage: float = 1.0  # (PB+C+Vop)/claims, discretionary screen
    issue_fee: float = 0.0
    senior_fee: float = 0.0
    repurchase_fee: float = 0.0
    issue_discount: float = 0.0
    repurchase_spread: float = 0.0
    btc_spread: float = 0.0
    sale_tax_rate: float = 0.0
    sell_for_payments: bool = True
    reserve_preferred: bool = True

    def __post_init__(self):
        if not self.name or type(self.reserve_days) is not int or self.reserve_days < 0:
            raise ValueError('Policy needs a name and nonnegative integer reserve_days')
        for name in ('cash_buffer', 'min_asset_coverage'):
            nonnegative(name, getattr(self, name))
        for name in ('buy_fraction', 'equity_fraction', 'sale_fraction_for_repurchase', 'debt_weight'):
            fraction(name, getattr(self, name))
        for name in ('repurchase_fraction', 'issue_fee', 'senior_fee', 'repurchase_fee',
                     'issue_discount', 'repurchase_spread', 'btc_spread', 'sale_tax_rate'):
            fraction(name, getattr(self, name), strict=True)


def contractual_needs(positions: list[Position], when: str, days: int,
                      include_preferred: bool) -> float:
    """Known future payments only. No future realized market path enters this forecast."""
    cutoff = (day(when) + timedelta(days=days)).isoformat()
    total = 0.0
    for p in positions:
        t = p.terms
        if p.face == 0 and p.accrued == 0:
            continue
        dates = set(d for d in t.payment_dates if when < d <= cutoff
                    and (t.kind == 'debt' or include_preferred))
        if t.maturity and when < t.maturity <= cutoff:
            dates.add(t.maturity)
        accrued, previous = p.accrued, when
        for d in sorted(dates):
            accrued += p.face*t.annual_rate*(day(d)-day(previous)).days/365.0
            total += accrued
            accrued, previous = 0.0, d
            if d == t.maturity:
                total += p.face
                break
    return total


def cash_target(state: State, event: Event, policy: Policy) -> float:
    needs = contractual_needs(state.positions, event.date, policy.reserve_days,
                              policy.reserve_preferred)
    return policy.cash_buffer + max(0.0, event.forecast_operating_needs+needs)


def linear_capacity(limit: float, inequalities: list[tuple[float, float]]) -> float:
    """Largest x in [0, limit] satisfying each intercept+slope*x >= 0."""
    lo, hi = 0.0, limit
    for a, b in inequalities:
        if b > 0:
            lo = max(lo, -a/b)
        elif b < 0:
            hi = min(hi, -a/b)
        elif a < -TOL:
            return 0.0
    return max(0.0, hi) if hi >= lo else 0.0


def quote(state: State, event: Event) -> float | None:
    k = state.backing(event.btc_price, event.operating_value)
    return event.multiple*k/state.shares if k > 0 else None


def coverage_headroom(state: State, event: Event, policy: Policy) -> float:
    assets = event.btc_price*state.btc+state.cash+event.operating_value
    return max(0.0, assets-policy.min_asset_coverage*state.claims)


def senior_amount(ledger: Ledger, event: Event, policy: Policy, offer: Offer) -> float:
    t = offer.terms
    weight = policy.debt_weight if t.kind == 'debt' else 1-policy.debt_weight
    limit = min(offer.capacity, event.senior_budget*weight)
    if not limit:
        return 0.0
    # Project the declared settlements (incl. conversion) for post-issue screens.
    pay, n, positions, _ = ledger.settlement_plan(event.conversions, event.pay_preferred)
    s = ledger.state
    required = pay+max(0.0, -event.operating_cashflow)
    base_needs = event.forecast_operating_needs + contractual_needs(
        positions, event.date, policy.reserve_days, policy.reserve_preferred)
    future_per_dollar = contractual_needs([Position(t, 1/offer.price_per_face)],
        event.date, policy.reserve_days, policy.reserve_preferred)
    net = 1-policy.senior_fee
    claims = sum(p.face+p.accrued for p in positions)
    assets = event.btc_price*s.btc+s.cash+event.operating_value-required
    liquid = s.cash-required-policy.cash_buffer
    return linear_capacity(limit, [
        (assets-policy.min_asset_coverage*claims,
         net-policy.min_asset_coverage/offer.price_per_face),
        (liquid, net),
        (liquid-base_needs, net-future_per_dollar),
    ])


@dataclass
class Snapshot:
    date: str
    status: str
    btc_price: float
    btc: float
    cash: float
    shares: float
    claims: float
    net_backing: float
    share_price: float | None
    btc_per_share: float
    backing_per_share: float
    cash_target: float
    cash_target_met: bool
    funding_gap: float = 0.0


def snapshot(ledger: Ledger, event: Event, policy: Policy, status='complete', gap=0.0):
    s = ledger.state
    k = s.backing(event.btc_price, event.operating_value)
    target = cash_target(s, event, policy)
    return Snapshot(event.date, status, event.btc_price, s.btc, s.cash, s.shares,
                    s.claims, k, quote(s, event), s.btc/s.shares, k/s.shares,
                    target, s.cash+TOL >= target, gap)


def execute_event(ledger: Ledger, event: Event, policy: Policy) -> Snapshot:
    ledger.accrue(event.date)
    if event.operating_cashflow > 0:
        ledger.post('operating_receipt', cash_in=event.operating_cashflow)
    if event.other_common_shares:
        ledger.post('stock_compensation', shares=event.other_common_shares)
    # This event convention quotes financing before any settlements or discretionary trades.
    issue_price = quote(ledger.state, event)
    issued = 0.0
    if issue_price is not None:
        execution = issue_price*(1-policy.issue_discount)
        s = ledger.state
        if execution*(1-policy.issue_fee) > s.backing(event.btc_price, event.operating_value)/s.shares:
            issued = min(policy.equity_fraction*s.backing(event.btc_price, event.operating_value),
                         event.equity_capacity, event.equity_authorization)
            if issued:
                ledger.issue_common(issued, execution, policy.issue_fee)
    # Deterministic debt-first offer processing; budget weights are not redistributed.
    for offer in sorted(event.offers, key=lambda o: (o.terms.kind, o.terms.id)):
        amount = senior_amount(ledger, event, policy, offer)
        if amount > TOL:
            ledger.issue_senior(offer.terms, amount, offer.price_per_face, policy.senior_fee)
    plan = ledger.settlement_plan(event.conversions, event.pay_preferred)
    operating_use = max(0.0, -event.operating_cashflow)
    required = plan[0]+operating_use
    shortfall = max(0.0, required-ledger.state.cash)
    sold = 0.0
    sell_price = event.btc_price*(1-policy.btc_spread)
    if shortfall > TOL and policy.sell_for_payments:
        net = ledger.sale_unit_net(sell_price, policy.sale_tax_rate)
        sold = min(shortfall/net, ledger.state.btc-ledger.state.pledged_btc,
                   event.btc_sale_capacity)
        if sold > 0:
            ledger.sell_btc(sold, sell_price, policy.sale_tax_rate, purpose='required_payments')
    gap = max(0.0, required-ledger.state.cash)
    if gap > TOL:
        # No unmodeled default waterfall or fractional payment allocation.
        return snapshot(ledger, event, policy, 'funding_gap', gap)
    ledger.settle(plan)
    if operating_use:
        ledger.post('operating_payment', cash_out=operating_use)
    target = cash_target(ledger.state, event, policy)
    rep_price = quote(ledger.state, event)
    repurchased = 0.0
    if rep_price is not None and not issued:
        s = ledger.state
        execution = rep_price*(1+policy.repurchase_spread)
        cap = min(event.repurchase_capacity, policy.repurchase_fraction*rep_price*s.shares)
        kps = s.backing(event.btc_price, event.operating_value)/s.shares
        if execution*(1+policy.repurchase_fee) < kps:
            consideration = min(cap, max(0.0, s.cash-target)/(1+policy.repurchase_fee),
                                coverage_headroom(s, event, policy)/(1+policy.repurchase_fee))
            if consideration > TOL:
                ledger.repurchase(consideration, execution, policy.repurchase_fee)
                repurchased += consideration
        # Sale-funded buybacks must pass the cost-adjusted net-backing test separately.
        s = ledger.state
        net = ledger.sale_unit_net(sell_price, policy.sale_tax_rate)
        zeta = net/(event.btc_price*(1+policy.repurchase_fee))
        kps = s.backing(event.btc_price, event.operating_value)/s.shares
        if (s.cash+TOL >= target and execution < zeta*kps and cap > repurchased
                and policy.sale_fraction_for_repurchase > 0):
            amount = min((cap-repurchased)*(1+policy.repurchase_fee)/net,
                         policy.sale_fraction_for_repurchase*(s.btc-s.pledged_btc),
                         max(0.0, event.btc_sale_capacity-sold),
                         coverage_headroom(s, event, policy)/event.btc_price)
            if amount > TOL:
                ledger.sell_btc(amount, sell_price, policy.sale_tax_rate, purpose='repurchase')
                consideration = amount*net/(1+policy.repurchase_fee)
                ledger.repurchase(consideration, execution, policy.repurchase_fee)
                sold += amount
                repurchased += consideration
    # Repurchase priority and no same-event discretionary Bitcoin round trip.
    if repurchased == 0 and sold == 0:
        s = ledger.state
        spend = max(0.0, s.cash-target)*policy.buy_fraction
        # Buying at a spread reduces marked assets only by that spread.
        buy_price = event.btc_price*(1+policy.btc_spread)
        quantity = min(spend/buy_price, event.btc_buy_capacity)
        if policy.btc_spread:
            quantity = min(quantity, coverage_headroom(s, event, policy)/(buy_price-event.btc_price))
        if quantity > TOL:
            ledger.buy_btc(quantity, buy_price)
    return snapshot(ledger, event, policy)


@dataclass
class Result:
    configuration_id: str
    input_sha256: str
    configuration: dict
    complete: bool
    expected_event_count: int
    snapshots: list[Snapshot]
    ledger: list[dict]
    final_state: dict
    shareholder_gross_return: float | None
    bitcoin_gross_return: float | None

    def to_dict(self):
        return asdict(self)


def validate_calendar(initial: State, events: tuple[Event, ...]):
    if not events:
        raise ValueError('At least one event is required')
    dates = [e.date for e in events]
    if dates != sorted(set(dates)) or dates[0] <= initial.asof:
        raise ValueError('Event dates must be strictly increasing after initial date')
    horizon, dateset = dates[-1], set(dates)
    if any(p.face > 0 and p.terms.maturity and p.terms.maturity <= initial.asof
           for p in initial.positions):
        raise ValueError('Initial state is a closing state; matured claims need prior settlement')
    instruments = [(initial.asof, p.terms) for p in initial.positions if p.face > 0]
    instruments += [(e.date, o.terms) for e in events for o in e.offers]
    for issued, terms in instruments:
        due = list(terms.payment_dates) + ([terms.maturity] if terms.maturity else [])
        if any(issued < d <= horizon and d not in dateset for d in due):
            raise ValueError(f'Calendar omits a scheduled date for {terms.id}')
        if issued != initial.asof and terms.maturity and terms.maturity <= issued:
            raise ValueError('Offer matures before or on issue date')


def run(initial: State, events: tuple[Event, ...], policy: Policy, *,
        configuration_id: str, initial_btc_price: float,
        initial_multiple: float = 1.0, initial_operating_value: float = 0.0,
        mechanism_label: str = 'supplied_path') -> Result:
    if not configuration_id:
        raise ValueError('A configuration id is required')
    initial.validate()
    validate_calendar(initial, events)
    nonnegative('initial_btc_price', initial_btc_price, positive=True)
    nonnegative('initial_multiple', initial_multiple, positive=True)
    nonnegative('initial_operating_value', initial_operating_value)
    cfg = dict(initial=asdict(initial), events=[asdict(e) for e in events],
               policy=asdict(policy), initial_btc_price=initial_btc_price,
               initial_multiple=initial_multiple, initial_operating_value=initial_operating_value,
               mechanism_label=mechanism_label, engine_version='0.1.0')
    digest = sha256(json.dumps(cfg, sort_keys=True, allow_nan=False).encode()).hexdigest()
    ledger = Ledger(initial)
    rows = []
    for event in events:
        rows.append(execute_event(ledger, event, policy))
        if rows[-1].status == 'funding_gap':
            break
    ledger.reconcile(initial)
    complete = len(rows) == len(events) and rows[-1].status == 'complete'
    k0 = initial.backing(initial_btc_price, initial_operating_value)
    start = initial_multiple*k0/initial.shares if k0 > 0 else None
    # A valuation-domain breach makes the full equity trajectory unresolved.
    equity_valid = start is not None and all(r.share_price is not None for r in rows)
    equity_return = rows[-1].share_price/start if complete and equity_valid else None
    btc_return = events[-1].btc_price/initial_btc_price  # external path exists even on company failure
    return Result(configuration_id, digest, cfg, complete, len(events), rows,
                  [asdict(e) for e in ledger.entries], asdict(ledger.state), equity_return, btc_return)


def supports(result: Result, *, minimum_cash=0.0, minimum_btc_per_share=0.0,
             minimum_equity_return=None, require_cash_target=False) -> bool:
    """Conjunction on ONE complete path, not an envelope across configurations."""
    nonnegative('minimum_cash', minimum_cash)
    nonnegative('minimum_btc_per_share', minimum_btc_per_share)
    if minimum_equity_return is not None:
        nonnegative('minimum_equity_return', minimum_equity_return)
    if not result.complete:
        return False
    initial = result.configuration['initial']
    if initial['cash']+TOL < minimum_cash or initial['btc']/initial['shares']+TOL < minimum_btc_per_share:
        return False
    if any(r.cash+TOL < minimum_cash or r.btc_per_share+TOL < minimum_btc_per_share
           or (require_cash_target and not r.cash_target_met) for r in result.snapshots):
        return False
    # Cash is tested at all executed prefixes, not just date-end summaries.
    if any(e['cash_after']+TOL < minimum_cash for e in result.ledger):
        return False
    if minimum_equity_return is not None:
        return (result.shareholder_gross_return is not None
                and result.shareholder_gross_return >= minimum_equity_return)
    return True
