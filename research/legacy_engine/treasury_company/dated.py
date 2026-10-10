"""Dated claims with purpose-specific sale permissions (engine 0.3.0).

This is an economic cash/claim ledger, not a GAAP ledger or a security pricer.
Amounts and settlement choices are explicit scenario inputs. A fixed schedule
cannot silently adapt to a different issuance, redemption, or conversion path.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import math

TOL = 1e-5
RATIO_TOL = 1e-12


def day(value):
    return date.fromisoformat(value)


def finite(value, label, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite number')
    if minimum is not None and value < minimum:
        raise ValueError(f'{label} must be >= {minimum}')


@dataclass
class Claim:
    id: str
    kind: str  # debt, cumulative_preferred, noncumulative_preferred
    currency: str
    face_native: float
    accrued_native: float = 0


@dataclass
class Opening:
    asof: str
    btc: float
    cash_usd: float
    treasuries_usd: float
    restricted_cash_usd: float
    reserve_designation_usd: float
    common_shares: float
    claims: list
    unallocated_payable_usd: float = 0
    pledged_btc: float = 0


@dataclass
class Payment:
    id: str
    claim_id: str
    kind: str  # interest, dividend, principal
    payment_date: str
    amount_native: float
    accrual_start: str | None = None
    accrual_end: str | None = None
    opening_credit_native: float = 0
    declared: bool = True
    settlement: str = 'cash'  # shares requires an explicit, externally verified election
    common_shares: float = 0
    share_settlement_authorized: bool = False
    note: str = ''


@dataclass
class Point:
    date: str
    btc_price_usd: float
    fx_usd_per_unit: dict
    multiple: float = 1
    net_operating_value_usd: float = 0
    operating_cashflow_usd: float = 0
    common_issue_cap_gross_usd: float = 0
    common_authorization_gross_limit_usd: float = 0
    treasury_liquidation_cap_usd: float = 0
    btc_sale_cap: float = 0
    reserve_floor_usd: float = 0
    allow_general_use_of_reserve: bool = False
    # Cumulative gross sale limits since opening; capacity is not authorization.
    btc_general_use_gross_limit_usd: float = 0
    btc_reserve_build_gross_limit_usd: float = 0
    btc_distribution_sales_authorized: bool = False
    common_repurchase_cap_usd: float = 0
    common_repurchase_gross_limit_usd: float = 0
    common_repurchase_share_cap: float = 0
    btc_repurchase_sales_authorized: bool = False


@dataclass
class DatedPolicy:
    name: str
    refill_reserve_floor: bool = True
    sell_btc_for_funding: bool = True
    common_issue_mode: str = 'liquidity'  # or accretive_only
    common_issue_fee_rate: float = 0
    common_issue_discount: float = 0
    btc_sale_cost_rate: float = 0
    effective_sale_tax_cash_fraction: float = 0
    repurchase_common_from_btc: bool = False
    common_repurchase_fee_rate: float = 0
    common_repurchase_spread: float = 0


@dataclass
class DatedResult:
    configuration_id: str
    input_sha256: str
    configuration: dict
    complete: bool
    expected_event_count: int
    initial_snapshot: dict
    snapshots: list
    ledger: list
    failure: dict | None
    unprocessed_path: list
    assessment: dict
    reconciliation: dict

    def to_dict(self):
        return asdict(self)


def state_dict(s):
    return asdict(s)


def mark(s, point):
    claims = sum((c.face_native+c.accrued_native)*point.fx_usd_per_unit[c.currency]
                 for c in s.claims) + s.unallocated_payable_usd
    liquid = s.cash_usd+s.treasuries_usd
    backing = (s.btc*point.btc_price_usd+liquid+s.restricted_cash_usd
               +point.net_operating_value_usd-claims)
    quote = point.multiple*backing/s.common_shares if backing > 0 else None
    return dict(state=state_dict(s), claims_usd=claims, liquid_assets_usd=liquid,
                backing_usd=backing, conditional_common_price_usd=quote,
                btc_per_common_share=s.btc/s.common_shares,
                reserve_floor_usd=point.reserve_floor_usd,
                reserve_compliant=s.reserve_designation_usd+TOL >= point.reserve_floor_usd,
                quote_defined=quote is not None)


class Journal:
    """Each atomic entry retains its deltas and closing state for prefix checks."""
    monetary = ('btc', 'cash_usd', 'treasuries_usd', 'restricted_cash_usd',
                'reserve_designation_usd', 'common_shares', 'unallocated_payable_usd', 'pledged_btc')

    def __init__(self, opening):
        self.initial = deepcopy(opening)
        self.state = deepcopy(opening)
        self.entries = []

    def post(self, when, action, balances=None, faces=None, accruals=None, details=None):
        balances, faces, accruals = balances or {}, faces or {}, accruals or {}
        s = deepcopy(self.state)
        s.asof = when
        for key, change in balances.items():
            if key not in self.monetary:
                raise ValueError(f'Unknown balance {key}')
            finite(change, key)
            setattr(s, key, getattr(s, key)+change)
        by_id = {c.id: c for c in s.claims}
        for changes, field_name in ((faces, 'face_native'), (accruals, 'accrued_native')):
            for key, change in changes.items():
                finite(change, key)
                setattr(by_id[key], field_name, getattr(by_id[key], field_name)+change)
        for key in self.monetary:
            if getattr(s, key) < -TOL:
                raise ValueError(f'Negative {key} after {action}')
        if s.common_shares <= 0 or s.pledged_btc > s.btc+TOL:
            raise ValueError('Invalid shares or encumbered Bitcoin balance')
        if s.reserve_designation_usd > s.cash_usd+s.treasuries_usd+TOL:
            raise ValueError('Reserve designation exceeds its asset pool')
        if any(c.face_native < -TOL or c.accrued_native < -TOL for c in s.claims):
            raise ValueError('Claim retirement or payment exceeds recorded claim')
        self.entries.append(dict(date=when, action=action, balances=balances,
                                 face_changes_native=faces, accrual_changes_native=accruals,
                                 details=details or {}, after=state_dict(s)))
        self.state = s

    def reconcile(self):
        balances = {k: getattr(self.initial, k) for k in self.monetary}
        faces = {c.id: c.face_native for c in self.initial.claims}
        accrued = {c.id: c.accrued_native for c in self.initial.claims}
        max_error = 0
        for entry in self.entries:
            for target, changes in ((balances, entry['balances']),
                                    (faces, entry['face_changes_native']),
                                    (accrued, entry['accrual_changes_native'])):
                for k, v in changes.items():
                    target[k] += v
            after = entry['after']
            errors = [abs(balances[k]-after[k]) for k in balances]
            for c in after['claims']:
                errors += [abs(faces[c['id']]-c['face_native']),
                           abs(accrued[c['id']]-c['accrued_native'])]
            max_error = max([max_error]+errors)
            if after['cash_usd'] < -TOL or after['reserve_designation_usd'] > after['cash_usd']+after['treasuries_usd']+TOL:
                raise AssertionError('Invalid ledger prefix')
        if max_error > TOL:
            raise AssertionError('Ledger does not reconcile')
        return dict(all_prefixes_reconciled=True, entries_checked=len(self.entries),
                    max_absolute_reconstruction_error=max_error,
                    reserve_counted_as_asset=False)


def validate(opening, payments, initial_point, points, policy, criteria):
    day(opening.asof)
    if initial_point.date != opening.asof:
        raise ValueError('Opening mark must use the opening date')
    for key in Journal.monetary:
        finite(getattr(opening, key), key, 0)
    if opening.common_shares <= 0 or opening.pledged_btc > opening.btc:
        raise ValueError('Invalid opening shares or pledged Bitcoin')
    if opening.reserve_designation_usd > opening.cash_usd+opening.treasuries_usd:
        raise ValueError('Opening reserve exceeds cash plus Treasury assets')
    if not points or any(day(a.date) >= day(b.date) for a, b in zip([initial_point]+points, points)):
        raise ValueError('Path must be nonempty and strictly increasing')
    claims = {c.id: c for c in opening.claims}
    if len(claims) != len(opening.claims):
        raise ValueError('Duplicate claim id')
    for c in opening.claims:
        if c.kind not in ('debt', 'cumulative_preferred', 'noncumulative_preferred'):
            raise ValueError('Unsupported claim kind')
        finite(c.face_native, c.id, 0)
        finite(c.accrued_native, c.id, 0)
    if policy.common_issue_mode not in ('liquidity', 'accretive_only'):
        raise ValueError('Unsupported common issue mode')
    for k in ('refill_reserve_floor', 'sell_btc_for_funding', 'repurchase_common_from_btc'):
        if not isinstance(getattr(policy, k), bool):
            raise ValueError(f'{k} must be boolean')
    for k in ('common_issue_fee_rate', 'common_issue_discount', 'btc_sale_cost_rate',
              'effective_sale_tax_cash_fraction', 'common_repurchase_fee_rate', 'common_repurchase_spread'):
        finite(getattr(policy, k), k, 0)
        if getattr(policy, k) >= 1:
            raise ValueError(f'{k} must be < 1')
    if policy.btc_sale_cost_rate+policy.effective_sale_tax_cash_fraction >= 1:
        raise ValueError('Bitcoin sale has no positive net cash proceeds')
    for p in [initial_point]+points:
        day(p.date)
        for k in ('allow_general_use_of_reserve', 'btc_distribution_sales_authorized', 'btc_repurchase_sales_authorized'):
            if not isinstance(getattr(p,k), bool):
                raise ValueError(f'{k} must be boolean')
        for k in ('btc_price_usd', 'multiple', 'common_issue_cap_gross_usd',
                  'common_authorization_gross_limit_usd', 'treasury_liquidation_cap_usd',
                  'btc_sale_cap', 'reserve_floor_usd', 'btc_general_use_gross_limit_usd',
                  'btc_reserve_build_gross_limit_usd', 'common_repurchase_cap_usd',
                  'common_repurchase_gross_limit_usd', 'common_repurchase_share_cap'):
            finite(getattr(p, k), k, 0)
        if p.btc_price_usd <= 0 or p.multiple <= 0:
            raise ValueError('Bitcoin price and valuation multiple must be positive')
        for k in ('net_operating_value_usd', 'operating_cashflow_usd'):
            finite(getattr(p, k), k)
        for currency in {c.currency for c in opening.claims} | {'USD'}:
            finite(p.fx_usd_per_unit.get(currency), f'{p.date} FX {currency}', 0)
            if p.fx_usd_per_unit[currency] <= 0:
                raise ValueError('FX rates must be positive')
        if p.fx_usd_per_unit['USD'] != 1:
            raise ValueError('USD numeraire must equal one')
    ids, credits, retirement = set(), {c: 0 for c in claims}, {}
    event_dates = {p.date for p in points}
    for pay in payments:
        if not isinstance(pay.declared, bool) or not isinstance(pay.share_settlement_authorized, bool):
            raise ValueError('Declaration and settlement authorization must be boolean')
        if pay.id in ids or pay.claim_id not in claims:
            raise ValueError('Duplicate payment id or unknown claim')
        ids.add(pay.id)
        if pay.kind not in ('interest', 'dividend', 'principal'):
            raise ValueError('Unsupported payment kind')
        c = claims[pay.claim_id]
        if (pay.kind in ('interest', 'principal')) != (c.kind == 'debt'):
            raise ValueError('Payment kind conflicts with claim kind')
        for k in ('amount_native', 'opening_credit_native', 'common_shares'):
            finite(getattr(pay, k), k, 0)
        if pay.amount_native <= 0:
            raise ValueError('Omit zero payments')
        if pay.settlement not in ('cash', 'shares'):
            raise ValueError('Unsupported settlement mode')
        if pay.settlement == 'shares' and (not pay.share_settlement_authorized or pay.common_shares <= 0):
            raise ValueError('Share settlement needs explicit authorization and share quantity')
        if pay.settlement == 'cash' and pay.common_shares:
            raise ValueError('Cash settlement cannot create shares')
        if day(pay.payment_date) <= day(opening.asof):
            raise ValueError('Payment dates must follow opening')
        if pay.payment_date <= points[-1].date and pay.payment_date not in event_dates:
            raise ValueError(f'Missing path point for {pay.id}')
        if pay.opening_credit_native > pay.amount_native+TOL:
            raise ValueError('Opening credit exceeds payment')
        if pay.kind == 'principal':
            if not pay.declared or pay.opening_credit_native or pay.accrual_start or pay.accrual_end:
                raise ValueError('Principal retirement is separate from accrued distributions')
            if pay.claim_id in retirement or abs(pay.amount_native-c.face_native) > TOL:
                raise ValueError('This engine requires exactly one full-face retirement per debt')
            retirement[pay.claim_id] = pay.payment_date
        else:
            if pay.kind == 'interest' and not pay.declared:
                raise ValueError('Contractual interest cannot be skipped as undeclared')
            if not pay.accrual_start or not pay.accrual_end:
                raise ValueError('Distribution needs an explicit accrual period')
            if not day(pay.accrual_start) < day(pay.accrual_end) <= day(pay.payment_date):
                raise ValueError('Invalid accrual or settlement dates')
            if pay.accrual_end <= opening.asof and abs(pay.opening_credit_native-pay.amount_native) > TOL:
                raise ValueError('Already earned distribution must have full opening credit')
            if pay.opening_credit_native and not pay.declared and c.kind == 'noncumulative_preferred':
                raise ValueError('Undeclared noncumulative dividend has no payable')
            credits[pay.claim_id] += pay.opening_credit_native
    for c in opening.claims:
        if abs(credits[c.id]-c.accrued_native) > TOL:
            raise ValueError(f'Opening credits do not allocate {c.id} accrued balance')
    for pay in payments:
        if pay.kind != 'principal' and pay.claim_id in retirement and pay.payment_date > retirement[pay.claim_id]:
            raise ValueError('Distribution scheduled after full retirement; supply adjusted schedule')
    allowed = {'require_reserve_compliance', 'min_terminal_equity_return', 'min_terminal_btc_per_share_ratio'}
    if set(criteria)-allowed:
        raise ValueError('Unknown support criterion')
    for k, v in criteria.items():
        if k == 'require_reserve_compliance':
            if not isinstance(v, bool):
                raise ValueError('Reserve criterion must be boolean')
        else:
            finite(v, k)


def earned(pay, when, opening_date, claim):
    if pay.kind == 'principal' or (claim.kind == 'noncumulative_preferred' and not pay.declared):
        return 0
    start = max(day(pay.accrual_start), day(opening_date))
    end = day(pay.accrual_end)
    fraction = 1 if end <= start else min(1, max(0, (day(when)-start).days/(end-start).days))
    return pay.opening_credit_native+(pay.amount_native-pay.opening_credit_native)*fraction


def run_dated_configuration(raw, configuration_id):
    cfg = deepcopy(raw)
    allowed = {'engine_version', 'opening', 'payments', 'initial_point', 'path', 'policy', 'criteria', 'metadata'}
    if set(cfg)-allowed:
        raise ValueError(f'Unknown dated configuration fields: {set(cfg)-allowed}')
    cfg['engine_version'] = '0.3.0'
    digest = hashlib.sha256(json.dumps(cfg, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    initial = dict(cfg['opening'])
    initial['claims'] = [Claim(**c) for c in initial['claims']]
    opening = Opening(**initial)
    payments = [Payment(**p) for p in cfg['payments']]
    initial_point = Point(**cfg['initial_point'])
    points = [Point(**p) for p in cfg['path']]
    policy = DatedPolicy(**cfg['policy'])
    criteria = cfg.get('criteria', {})
    validate(opening, payments, initial_point, points, policy, criteria)
    journal = Journal(opening)
    initial_snapshot = mark(opening, initial_point)
    tracked = {p.id: p.opening_credit_native for p in payments}
    settled, snapshots, failure = set(), [], None
    common_issued_gross = 0
    general_sale_gross = reserve_build_gross = distribution_sale_net = 0
    eligible_paid = repurchased_gross = 0
    for point in points:
        s = journal.state
        claims = {c.id: c for c in s.claims}
        accrual = {}
        for p in payments:
            if p.id in settled or p.kind == 'principal':
                continue
            target = earned(p, point.date, opening.asof, claims[p.claim_id])
            delta = target-tracked[p.id]
            if delta < -TOL:
                raise AssertionError('Accrued amount fell without settlement')
            accrual[p.claim_id] = accrual.get(p.claim_id, 0)+delta
            tracked[p.id] = target
        journal.post(point.date, 'accrue_scheduled_distributions', accruals=accrual)
        if point.operating_cashflow_usd > 0:
            journal.post(point.date, 'operating_cash_receipt', {'cash_usd': point.operating_cashflow_usd})
        due = [p for p in payments if p.payment_date == point.date and p.declared]
        eligible = sum(p.amount_native*point.fx_usd_per_unit[claims[p.claim_id].currency]
                       for p in due if p.kind != 'principal' and p.settlement == 'cash')
        principal = sum(p.amount_native*point.fx_usd_per_unit[claims[p.claim_id].currency]
                        for p in due if p.kind == 'principal' and p.settlement == 'cash')
        operating_use = max(0, -point.operating_cashflow_usd)
        general = principal+operating_use
        cash_due = eligible+general
        s = journal.state
        protected_after = max(0, s.reserve_designation_usd-eligible)
        if point.allow_general_use_of_reserve:
            protected_after = 0
        required_after = max(protected_after, point.reserve_floor_usd if policy.refill_reserve_floor else 0)
        liquidatable = min(s.treasuries_usd, point.treasury_liquidation_cap_usd)
        need = max(0, cash_due+required_after-s.cash_usd-s.treasuries_usd,
                   cash_due-s.cash_usd-liquidatable)
        quote = mark(s, point)['conditional_common_price_usd']
        issue_price = quote*(1-policy.common_issue_discount) if quote else None
        may_issue = issue_price is not None
        if policy.common_issue_mode == 'accretive_only' and may_issue:
            may_issue = issue_price*(1-policy.common_issue_fee_rate) >= mark(s, point)['backing_usd']/s.common_shares
        # The limit is cumulative gross issuance authorized since opening.
        authorization = max(0, point.common_authorization_gross_limit_usd-common_issued_gross)
        gross = min(point.common_issue_cap_gross_usd, authorization,
                    need/(1-policy.common_issue_fee_rate)) if may_issue else 0
        if gross > TOL:
            net = gross*(1-policy.common_issue_fee_rate)
            journal.post(point.date, 'issue_common_for_funding',
                         {'cash_usd': net, 'common_shares': gross/issue_price},
                         details=dict(gross_usd=gross, fee_usd=gross-net, price_usd=issue_price))
            common_issued_gross += gross
            need = max(0, need-net)
        unit_net = point.btc_price_usd*(1-policy.btc_sale_cost_rate-policy.effective_sale_tax_cash_fraction)
        net_fraction = unit_net/point.btc_price_usd
        available = max(0, journal.state.btc-journal.state.pledged_btc)
        s = journal.state
        general_need = max(0, general-max(0, s.cash_usd+s.treasuries_usd-s.reserve_designation_usd))
        if point.allow_general_use_of_reserve:
            general_need = max(0, general-s.cash_usd-s.treasuries_usd)
        general_requested = min(need, general_need)
        market_net = min(available, point.btc_sale_cap)*unit_net if policy.sell_btc_for_funding else 0
        general_net = min(general_requested, market_net,
                          max(0, point.btc_general_use_gross_limit_usd-general_sale_gross)*net_fraction)
        # Distribution proceeds can fund due payments or replace earlier paid
        # distributions. They cannot be relabeled as general-use proceeds.
        remaining_need = max(0, need-general_requested)
        distribution_credit = max(0, eligible_paid+eligible-distribution_sale_net)
        distribution_net = min(remaining_need, market_net-general_net, distribution_credit) if point.btc_distribution_sales_authorized else 0
        build_net = min(max(0, remaining_need-distribution_net),
                        max(0, market_net-general_net-distribution_net),
                        max(0, point.btc_reserve_build_gross_limit_usd-reserve_build_gross)*net_fraction)
        sold = (general_net+distribution_net+build_net)/unit_net
        general_sale_gross += general_net/net_fraction
        distribution_sale_net += distribution_net
        reserve_build_gross += build_net/net_fraction
        if sold > 0:
            gross_btc = sold*point.btc_price_usd
            journal.post(point.date, 'sell_bitcoin_for_funding', {'btc': -sold, 'cash_usd': sold*unit_net},
                         details=dict(gross_usd=gross_btc, execution_cost_usd=gross_btc*policy.btc_sale_cost_rate,
                                      cash_tax_assumption_usd=gross_btc*policy.effective_sale_tax_cash_fraction,
                                      general_use_net_usd=general_net, distribution_net_usd=distribution_net,
                                      reserve_build_net_usd=build_net,
                                      motivation='Dated cash needs and reserve policy under supplied capital-allocation rule'))
        s = journal.state
        liquidation = min(s.treasuries_usd, point.treasury_liquidation_cap_usd, max(0, cash_due-s.cash_usd))
        if liquidation > TOL:
            journal.post(point.date, 'liquidate_treasuries_at_par',
                         {'cash_usd': liquidation, 'treasuries_usd': -liquidation})
        s = journal.state
        cash_gap = max(0, cash_due-s.cash_usd)
        authorization_gap = max(0, cash_due+protected_after-s.cash_usd-s.treasuries_usd)
        sale_purpose_gap = max(0, general_need-general_net)
        if cash_gap > TOL or authorization_gap > TOL or sale_purpose_gap > TOL:
            failure = dict(date=point.date, cash_gap_usd=cash_gap,
                           reserve_authorization_gap_usd=authorization_gap,
                           btc_general_use_funding_gap_usd=sale_purpose_gap,
                           due_payment_ids=[p.id for p in due], operating_cash_use_usd=operating_use,
                           reason='Joint dated settlement unsupported; no default waterfall imposed')
            snapshots.append(dict(date=point.date, settled=False, cash_due_usd=cash_due,
                                  payments=[], **mark(s, point)))
            break
        faces, paid_accrual, stock_shares = {}, {}, 0
        for p in due:
            if p.kind == 'principal':
                faces[p.claim_id] = faces.get(p.claim_id, 0)-p.amount_native
            else:
                if abs(tracked[p.id]-p.amount_native) > TOL:
                    raise AssertionError('Payment is not fully accrued at settlement')
                paid_accrual[p.claim_id] = paid_accrual.get(p.claim_id, 0)-p.amount_native
            stock_shares += p.common_shares
            settled.add(p.id)
        remaining_liquid = s.cash_usd+s.treasuries_usd-cash_due
        reserve_after_payment = max(0, s.reserve_designation_usd-eligible)
        if point.allow_general_use_of_reserve:
            reserve_after_payment = min(reserve_after_payment, remaining_liquid)
        journal.post(point.date, 'settle_dated_commitments',
                     {'cash_usd': -cash_due, 'common_shares': stock_shares,
                      'reserve_designation_usd': reserve_after_payment-s.reserve_designation_usd},
                     faces, paid_accrual,
                     dict(payment_ids=[p.id for p in due], eligible_distributions_usd=eligible,
                          principal_cash_usd=principal, operating_cash_use_usd=operating_use,
                          reserve_override=point.allow_general_use_of_reserve))
        eligible_paid += eligible
        s = journal.state
        if policy.refill_reserve_floor:
            increase = max(0, min(point.reserve_floor_usd, s.cash_usd+s.treasuries_usd)-s.reserve_designation_usd)
            if increase > TOL:
                journal.post(point.date, 'designate_reserve', {'reserve_designation_usd': increase},
                             details={'cash_movement_usd': 0})
        # A separately authorized capital-allocation choice after commitments.
        # Price is fixed immediately before this trade; no simultaneous issue/buyback.
        s = journal.state
        quote = mark(s, point)['conditional_common_price_usd']
        buyback_price = quote*(1+policy.common_repurchase_spread) if quote else None
        may_repurchase = (policy.repurchase_common_from_btc and point.btc_repurchase_sales_authorized
                          and gross <= TOL and buyback_price is not None
                          and s.reserve_designation_usd+TOL >= point.reserve_floor_usd
                          and all(c.accrued_native <= TOL for c in s.claims if c.kind.endswith('preferred')))
        if may_repurchase:
            # Screen backing per share after all sale friction and repurchase fees.
            net_cost_per_share = buyback_price*(1+policy.common_repurchase_fee_rate)/net_fraction
            may_repurchase = net_cost_per_share < mark(s, point)['backing_usd']/s.common_shares
        if may_repurchase:
            remaining_btc = min(max(0,s.btc-s.pledged_btc), max(0,point.btc_sale_cap-sold))
            spend = min(point.common_repurchase_cap_usd,
                        max(0,point.common_repurchase_gross_limit_usd-repurchased_gross),
                        point.common_repurchase_share_cap*buyback_price,
                        s.common_shares*.99*buyback_price,
                        remaining_btc*unit_net/(1+policy.common_repurchase_fee_rate))
            if spend > TOL:
                cost = spend*(1+policy.common_repurchase_fee_rate)
                btc_for_buyback = cost/unit_net
                journal.post(point.date, 'sell_bitcoin_for_common_repurchase',
                             {'btc':-btc_for_buyback,'cash_usd':cost},
                             details=dict(gross_usd=btc_for_buyback*point.btc_price_usd,
                                          execution_cost_usd=btc_for_buyback*point.btc_price_usd*policy.btc_sale_cost_rate,
                                          cash_tax_assumption_usd=btc_for_buyback*point.btc_price_usd*policy.effective_sale_tax_cash_fraction))
                journal.post(point.date, 'repurchase_common',
                             {'cash_usd':-cost,'common_shares':-spend/buyback_price},
                             details=dict(gross_repurchase_usd=spend,fee_usd=cost-spend,price_usd=buyback_price,
                                          pretrade_backing_per_share=mark(s,point)['backing_usd']/s.common_shares))
                repurchased_gross += spend
        snapshots.append(dict(date=point.date, settled=True, cash_due_usd=cash_due,
                              payments=[p.id for p in due], **mark(journal.state, point)))
    complete = failure is None
    all_quotes_defined = all(x['quote_defined'] for x in [initial_snapshot]+snapshots)
    terminal_return = (snapshots[-1]['conditional_common_price_usd']/initial_snapshot['conditional_common_price_usd']-1
                       if complete and all_quotes_defined else None)
    btc_ratio = snapshots[-1]['btc_per_common_share']/initial_snapshot['btc_per_common_share'] if complete and opening.btc > 0 else None
    reserve_compliant = all(x['reserve_compliant'] for x in [initial_snapshot]+snapshots)
    tests = {'all_dated_commitments_met': complete, 'equity_mapping_defined_throughout': all_quotes_defined and complete}
    if criteria.get('require_reserve_compliance'):
        tests['reserve_floor_at_every_path_point'] = reserve_compliant and complete
    if 'min_terminal_equity_return' in criteria:
        tests['terminal_equity_return_threshold'] = terminal_return is not None and terminal_return+RATIO_TOL >= criteria['min_terminal_equity_return']
    if 'min_terminal_btc_per_share_ratio' in criteria:
        tests['terminal_btc_per_share_threshold'] = btc_ratio is not None and btc_ratio+RATIO_TOL >= criteria['min_terminal_btc_per_share_ratio']
    assessment = dict(complete_path=complete, reserve_compliant_throughout=reserve_compliant,
                      conditional_terminal_equity_return=terminal_return,
                      terminal_btc_per_share_ratio=btc_ratio, criteria=tests,
                      jointly_supported=all(tests.values()), probabilities_assigned=False)
    return DatedResult(configuration_id, digest, cfg, complete, len(points), initial_snapshot,
                       snapshots, journal.entries, failure,
                       [asdict(p) for p in points[len(snapshots):]], assessment, journal.reconcile())
