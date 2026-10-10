"""Corporate accounts. USD, BTC and split-adjusted common shares; no price model."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from math import isfinite, isclose
from copy import deepcopy

TOL = 1e-8


def nonnegative(name: str, value: float, *, positive: bool = False) -> None:
    if not isfinite(value) or value < 0 or (positive and value <= 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")


def fraction(name: str, value: float, *, strict: bool = False) -> None:
    nonnegative(name, value)
    if value > 1 or (strict and value == 1):
        raise ValueError(f"{name} must be {'less than' if strict else 'at most'} one")


def day(text: str) -> date:
    return date.fromisoformat(text)


@dataclass(frozen=True)
class Terms:
    id: str
    kind: str  # debt or cumulative preferred, fixed rate, simple ACT/365 accrual
    annual_rate: float = 0.0
    payment_dates: tuple[str, ...] = ()
    maturity: str | None = None
    conversion_price: float | None = None
    conversion_dates: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.id or self.kind not in ('debt', 'preferred'):
            raise ValueError('An instrument needs an id and debt/preferred kind')
        nonnegative('annual_rate', self.annual_rate)
        if tuple(sorted(set(self.payment_dates))) != tuple(self.payment_dates):
            raise ValueError('payment_dates must be unique and sorted')
        for d in (*self.payment_dates, *self.conversion_dates):
            day(d)
        if self.maturity:
            day(self.maturity)
            if any(d > self.maturity for d in (*self.payment_dates, *self.conversion_dates)):
                raise ValueError('Instrument events cannot follow maturity')
        if self.conversion_price is not None:
            nonnegative('conversion_price', self.conversion_price, positive=True)
        elif self.conversion_dates:
            raise ValueError('Conversion dates require a conversion price')


@dataclass
class Position:
    terms: Terms
    face: float  # USD principal or aggregate preferred liquidation amount
    accrued: float = 0.0

    def validate(self):
        nonnegative('face', self.face)
        nonnegative('accrued', self.accrued)


@dataclass
class State:
    asof: str
    btc: float
    cash: float
    shares: float
    tax_basis: float = 0.0  # aggregate average-cost basis, not per-coin basis
    pledged_btc: float = 0.0
    positions: list[Position] = field(default_factory=list)

    @property
    def claims(self) -> float:
        return sum(p.face + p.accrued for p in self.positions)

    def validate(self):
        day(self.asof)
        for name in ('btc', 'cash', 'tax_basis', 'pledged_btc'):
            nonnegative(name, getattr(self, name))
        nonnegative('shares', self.shares, positive=True)
        if self.pledged_btc > self.btc + TOL:
            raise ValueError('Pledged BTC exceeds holdings')
        if self.btc == 0 and self.tax_basis > TOL:
            raise ValueError('Zero BTC cannot retain tax basis')
        if len({p.terms.id for p in self.positions}) != len(self.positions):
            raise ValueError('Duplicate instrument id')
        for p in self.positions:
            p.validate()
            if p.face > 0 and p.terms.maturity and p.terms.maturity < self.asof:
                raise ValueError('Outstanding instrument is past maturity')

    def backing(self, price: float, operating_value: float = 0.0) -> float:
        return price * self.btc + self.cash + operating_value - self.claims


@dataclass
class Entry:
    date: str
    action: str
    cash_in: float
    cash_out: float
    btc_change: float
    share_change: float
    basis_change: float
    claim_change: float
    cash_after: float
    btc_after: float
    shares_after: float
    claims_after: float
    details: dict


class Ledger:
    """All mutations pass through one atomic, reconciled accounting operation."""
    def __init__(self, state: State):
        state.validate()
        self.state = deepcopy(state)
        self.entries: list[Entry] = []

    def post(self, action: str, *, cash_in=0.0, cash_out=0.0, btc=0.0,
             shares=0.0, basis=0.0, positions=None, details=None):
        nonnegative('cash_in', cash_in)
        nonnegative('cash_out', cash_out)
        for x in (btc, shares, basis):
            if not isfinite(x):
                raise ValueError('Nonfinite transaction')
        old = self.state
        new = deepcopy(old)
        new.cash += cash_in - cash_out
        new.btc += btc
        new.shares += shares
        new.tax_basis += basis
        if positions is not None:
            new.positions = deepcopy(positions)
        # Only eliminate floating roundoff near exact resource exhaustion.
        for name in ('cash', 'btc', 'tax_basis'):
            if -TOL <= getattr(new, name) < 0:
                setattr(new, name, 0.0)
        new.validate()
        self.entries.append(Entry(old.asof, action, cash_in, cash_out, btc, shares,
                                  basis, new.claims-old.claims, new.cash, new.btc,
                                  new.shares, new.claims, details or {}))
        self.state = new

    def accrue(self, when: str):
        days = (day(when) - day(self.state.asof)).days
        if days <= 0:
            raise ValueError('Events must be strictly increasing')
        positions = deepcopy(self.state.positions)
        for p in positions:
            if p.face and p.terms.maturity and p.terms.maturity < when:
                raise ValueError('An event skipped a maturity')
            if p.face and any(self.state.asof < d < when for d in p.terms.payment_dates):
                raise ValueError('An event skipped an instrument payment date')
            p.accrued += p.face * p.terms.annual_rate * days / 365.0
        previous = self.state.asof
        self.state.asof = when
        try:
            self.post('accrual', positions=positions, details={'days': days})
        except Exception:
            self.state.asof = previous
            raise

    def issue_common(self, proceeds: float, share_price: float, fee: float = 0.0):
        nonnegative('proceeds', proceeds)
        nonnegative('share_price', share_price, positive=True)
        fraction('issuance fee', fee, strict=True)
        self.post('common_issue', cash_in=proceeds, cash_out=proceeds*fee,
                  shares=proceeds/share_price,
                  details={'gross': proceeds, 'price': share_price, 'fee': proceeds*fee})

    def issue_senior(self, terms: Terms, proceeds: float, price_per_face: float, fee=0.0):
        nonnegative('proceeds', proceeds, positive=True)
        nonnegative('price_per_face', price_per_face, positive=True)
        fraction('senior fee', fee, strict=True)
        if terms.id in {p.terms.id for p in self.state.positions}:
            raise ValueError('New issue id already exists')
        if terms.maturity and terms.maturity <= self.state.asof:
            raise ValueError('New instrument must mature after issuance')
        self.post('senior_issue', cash_in=proceeds, cash_out=proceeds*fee,
                  positions=self.state.positions + [Position(terms, proceeds/price_per_face)],
                  details={'id': terms.id, 'gross': proceeds, 'fee': proceeds*fee})

    def buy_btc(self, quantity: float, execution_price: float):
        nonnegative('quantity', quantity)
        nonnegative('execution_price', execution_price, positive=True)
        cost = quantity * execution_price
        self.post('btc_buy', cash_out=cost, btc=quantity, basis=cost,
                  details={'quantity': quantity, 'execution_price': execution_price})

    def sale_unit_net(self, execution_price: float, tax_rate: float) -> float:
        nonnegative('execution_price', execution_price, positive=True)
        fraction('tax_rate', tax_rate, strict=True)
        basis = self.state.tax_basis/self.state.btc if self.state.btc else 0.0
        return execution_price - tax_rate*max(0.0, execution_price-basis)

    def sell_btc(self, quantity: float, execution_price: float, tax_rate=0.0, *, purpose: str):
        nonnegative('quantity', quantity)
        net = self.sale_unit_net(execution_price, tax_rate)
        if quantity > self.state.btc-self.state.pledged_btc + TOL:
            raise ValueError('Sale exceeds available BTC')
        basis = quantity*self.state.tax_basis/self.state.btc if self.state.btc else 0.0
        self.post('btc_sale', cash_in=quantity*execution_price,
                  cash_out=quantity*(execution_price-net), btc=-quantity, basis=-basis,
                  details={'quantity': quantity, 'tax': quantity*(execution_price-net),
                           'execution_price': execution_price, 'purpose': purpose})

    def repurchase(self, consideration: float, share_price: float, fee=0.0):
        nonnegative('consideration', consideration)
        nonnegative('share_price', share_price, positive=True)
        fraction('repurchase fee', fee, strict=True)
        self.post('common_repurchase', cash_out=consideration*(1+fee),
                  shares=-consideration/share_price,
                  details={'consideration': consideration, 'price': share_price,
                           'fee': consideration*fee})

    def settlement_plan(self, conversions: dict[str, float], pay_preferred: bool):
        positions = deepcopy(self.state.positions)
        if set(conversions) - {p.terms.id for p in positions}:
            raise ValueError('Conversion of an unknown instrument')
        cash, shares, facts = 0.0, 0.0, []
        for p in positions:
            t = p.terms
            converted = conversions.get(t.id, 0.0)
            nonnegative('converted face', converted)
            if converted > p.face + TOL:
                raise ValueError('Conversion exceeds face')
            if converted and (self.state.asof not in t.conversion_dates or t.conversion_price is None):
                raise ValueError('Conversion is not eligible on this date')
            matured = t.maturity == self.state.asof
            coupon = self.state.asof in t.payment_dates
            interest = (p.accrued if matured or (coupon and (t.kind == 'debt' or pay_preferred))
                        else p.accrued * converted / p.face if p.face else 0.0)
            redemption = p.face-converted if matured else 0.0
            issued = converted/t.conversion_price if converted else 0.0
            p.face -= converted+redemption
            p.accrued -= interest
            cash += interest+redemption
            shares += issued
            facts.append({'id': t.id, 'distribution': interest, 'redemption': redemption,
                          'converted_face': converted, 'conversion_shares': issued})
        return cash, shares, positions, facts

    def settle(self, plan):
        cash, shares, positions, facts = plan
        self.post('instrument_settlement', cash_out=cash, shares=shares,
                  positions=positions, details={'instruments': facts})

    def reconcile(self, initial: State):
        """Independent sums; check every prefix, including intra-event settlement."""
        values = [initial.cash, initial.btc, initial.shares, initial.claims, initial.tax_basis]
        for e in self.entries:
            changes = [e.cash_in-e.cash_out, e.btc_change, e.share_change,
                       e.claim_change, e.basis_change]
            values = [a+b for a, b in zip(values, changes)]
            observed = [e.cash_after, e.btc_after, e.shares_after, e.claims_after]
            for total, actual in zip(values, observed):
                if not isclose(total, actual, rel_tol=1e-11, abs_tol=TOL):
                    raise AssertionError('Ledger identity failed')
            if min(values[:2]) < -TOL or values[2] <= 0:
                raise AssertionError('Resource constraint failed')
        if not isclose(values[4], self.state.tax_basis, rel_tol=1e-11, abs_tol=TOL):
            raise AssertionError('Tax basis identity failed')
