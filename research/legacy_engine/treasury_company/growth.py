"""ATM and STRC financing with generated commitments (engine 0.4.0).

The dated 0.3 engine remains frozen. Prices, investor capacity, and policies are
conditional inputs. This is an economic ledger, not a legal or market forecast.
"""
from copy import deepcopy
from calendar import monthrange
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
import hashlib
import json
from .dated import (Claim, Opening as BaseOpening, Payment, Point as BasePoint,
                    DatedPolicy as BasePolicy, DatedResult, Journal as BaseJournal,
                    mark as base_mark, validate as base_validate, earned, day,
                    finite, TOL, RATIO_TOL)


@dataclass
class Opening(BaseOpening):
    strc_shares: float = 0


@dataclass
class Point(BasePoint):
    common_program_target_gross_usd: float = 0
    strc_issue_target_gross_usd: float = 0
    strc_issue_cap_gross_usd: float = 0
    strc_authorization_gross_limit_usd: float = 0
    strc_execution_price_usd: float = 100
    strc_liquidation_preference_usd: float = 100
    strc_annual_rate: float = .12
    btc_purchase_cap: float = 0
    unreserved_cash_buffer_usd: float = 0


@dataclass
class Policy(BasePolicy):
    common_fund_cash_shortfalls: bool = True
    common_growth_min_net_premium: float = 1
    common_access_min_multiple: float = 0
    strc_min_execution_price_usd: float = 99
    strc_max_execution_price_usd: float = 101
    require_positive_backing_for_strc: bool = True
    strc_issue_fee_rate: float = 0
    strc_reserve_months: float = 12
    purchase_bitcoin: bool = False
    purchase_fraction: float = 1
    deploy_existing_surplus_cash: bool = False
    btc_purchase_cost_rate: float = 0


@dataclass
class DividendTemplate:
    id: str
    record_date: str
    accrual_end: str
    payment_date: str
    annual_rate: float


@dataclass
class StrcTerms:
    claim_id: str
    stated_amount_usd: float
    opening_annual_rate: float
    templates: list
    business_holidays: list


@dataclass
class GrowthResult(DatedResult):
    generated_payments: list
    financing_decisions: list


class Journal(BaseJournal):
    monetary = BaseJournal.monetary + ('strc_shares',)


def mark(s, point):
    result = base_mark(s, point)
    result.update(strc_shares=s.strc_shares,
                  annualized_strc_distributions_usd=s.strc_shares*100*point.strc_annual_rate,
                  strc_annual_rate=point.strc_annual_rate,
                  strc_liquidation_preference_usd=point.strc_liquidation_preference_usd,
                  backing_per_common_share_usd=result['backing_usd']/s.common_shares,
                  unreserved_cash_buffer_usd=point.unreserved_cash_buffer_usd,
                  cash_buffer_compliant=(result['liquid_assets_usd']-s.reserve_designation_usd+TOL
                                         >= point.unreserved_cash_buffer_usd))
    return result


def reserve_point(point, state, opening, policy, terms):
    change = terms.stated_amount_usd*(state.strc_shares*point.strc_annual_rate
                                     - opening.strc_shares*terms.opening_annual_rate)
    return replace(point, reserve_floor_usd=max(0, point.reserve_floor_usd
                                               +policy.strc_reserve_months/12*change))


def next_business_day(dt, holidays):
    while dt.weekday() >= 5 or str(dt) in holidays:
        dt += timedelta(days=1)
    return dt


def validate_growth(opening, payments, initial_point, points, policy, criteria, terms):
    base_validate(opening, payments, initial_point, points, policy, criteria)
    finite(opening.strc_shares, 'Opening STRC shares', 0)
    finite(terms.opening_annual_rate, 'Opening STRC rate', 0)
    if terms.stated_amount_usd != 100 or terms.opening_annual_rate <= 0:
        raise ValueError('STRC uses a $100 stated amount and a positive supplied rate')
    by_id = {c.id:c for c in opening.claims}
    c = by_id.get(terms.claim_id)
    if c is None or c.currency != 'USD' or c.kind != 'cumulative_preferred':
        raise ValueError('STRC must identify a USD cumulative preferred claim')
    if abs(c.face_native-opening.strc_shares*initial_point.strc_liquidation_preference_usd)>TOL:
        raise ValueError('STRC shares and opening liquidation claim do not reconcile')
    if initial_point.strc_annual_rate != terms.opening_annual_rate:
        raise ValueError('Initial rate and reserve reference rate must agree')
    for k in ('require_positive_backing_for_strc','purchase_bitcoin','deploy_existing_surplus_cash','common_fund_cash_shortfalls'):
        if not isinstance(getattr(policy,k),bool): raise ValueError(k+' must be boolean')
    for k in ('common_growth_min_net_premium','common_access_min_multiple','strc_reserve_months',
              'strc_min_execution_price_usd','strc_max_execution_price_usd',
              'strc_issue_fee_rate','purchase_fraction','btc_purchase_cost_rate'):
        finite(getattr(policy,k),k,0)
    if not 0 < policy.strc_min_execution_price_usd <= policy.strc_max_execution_price_usd:
        raise ValueError('Invalid STRC execution band')
    if policy.strc_issue_fee_rate >= 1 or policy.purchase_fraction > 1 or policy.btc_purchase_cost_rate >= 1:
        raise ValueError('Invalid financing/allocation fraction')
    templates=terms.templates
    if not templates or templates[0].record_date != opening.asof or templates[-1].accrual_end <= points[-1].date:
        raise ValueError('STRC calendar must begin at opening and extend beyond the horizon')
    dates={p.date for p in points}
    template_ids=set()
    for i,t in enumerate(templates):
        if t.id in template_ids: raise ValueError('Duplicate STRC template')
        template_ids.add(t.id)
        if not day(t.record_date)<day(t.accrual_end)<=day(t.payment_date):
            raise ValueError('Invalid STRC dividend period')
        a=day(t.record_date)
        if a.day==15:
            expected=a.replace(day=monthrange(a.year,a.month)[1])
        elif a.day==monthrange(a.year,a.month)[1]:
            expected=(a+timedelta(days=1)).replace(day=15)
        else:
            raise ValueError('STRC record date must be a regular semimonthly boundary')
        if day(t.accrual_end)!=expected:
            raise ValueError('STRC dividend template must cover one full semimonthly period')
        if i and templates[i-1].accrual_end != t.record_date:
            raise ValueError('STRC calendar has a gap or overlap')
        if str(next_business_day(day(t.accrual_end),terms.business_holidays)) != t.payment_date:
            raise ValueError('STRC cash date must follow the supplied business calendar')
        if t.payment_date<=points[-1].date and t.payment_date not in dates:
            raise ValueError('Missing path point for a generated STRC payment')
        finite(t.annual_rate,'STRC period rate',0)
        if t.annual_rate<=0: raise ValueError('Use positive STRC rates in this route')
    record_dates={t.record_date for t in templates}
    for p in [initial_point]+points:
        for k in ('common_program_target_gross_usd','strc_issue_target_gross_usd','strc_issue_cap_gross_usd',
                  'strc_authorization_gross_limit_usd','strc_execution_price_usd',
                  'strc_liquidation_preference_usd','strc_annual_rate','btc_purchase_cap',
                  'unreserved_cash_buffer_usd'):
            finite(getattr(p,k),k,0)
        if p.strc_liquidation_preference_usd<100 or p.strc_execution_price_usd<=0 or p.strc_annual_rate<=0:
            raise ValueError('Invalid STRC price, preference or rate')
        if p.date>opening.asof:
            active=next(t for t in templates if t.record_date<p.date<=t.accrual_end)
            if abs(active.annual_rate-p.strc_annual_rate)>RATIO_TOL:
                raise ValueError('STRC current rate conflicts with the supplied dividend period')
        if p.strc_issue_target_gross_usd>TOL:
            if p.date not in record_dates or next_business_day(day(p.date),terms.business_holidays)!=day(p.date):
                raise ValueError('STRC issuance restricted to business-day regular record dates')
    # Prevent fixed opening-share payments from silently ignoring a rate scenario.
    by_template={t.payment_date:t for t in templates}
    original_strc=[p for p in payments if p.claim_id==terms.claim_id]
    if opening.strc_shares>0:
        if len(original_strc)!=len(templates) or {p.payment_date for p in original_strc}!=set(by_template):
            raise ValueError('Every STRC period requires one original-share dividend')
    elif original_strc:
        raise ValueError('No original-share STRC dividends when opening shares are zero')
    for p in payments:
        if p.claim_id!=terms.claim_id: continue
        if p.kind!='dividend' or not p.declared or p.settlement!='cash':
            raise ValueError('STRC route assumes declared cash distributions')
        t=by_template.get(p.payment_date)
        if t is None or p.accrual_start!=t.record_date or p.accrual_end!=t.accrual_end:
            raise ValueError('Original-share STRC accrual period conflicts with the calendar')
        if p.opening_credit_native: continue  # preserve already-declared opening amounts
        if t is None or abs(p.amount_native-opening.strc_shares*100*t.annual_rate/24)>TOL:
            raise ValueError('Opening-share STRC dividend conflicts with the period rate')


def run_dated_configuration(raw, configuration_id):
    cfg = deepcopy(raw)
    allowed = {'engine_version', 'opening', 'payments', 'initial_point', 'path', 'policy', 'criteria', 'metadata', 'strc_terms'}
    if set(cfg)-allowed:
        raise ValueError(f'Unknown dated configuration fields: {set(cfg)-allowed}')
    cfg['engine_version'] = '0.4.0'
    digest = hashlib.sha256(json.dumps(cfg, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    initial = dict(cfg['opening'])
    initial['claims'] = [Claim(**c) for c in initial['claims']]
    opening = Opening(**initial)
    payments = [Payment(**p) for p in cfg['payments']]
    initial_point = Point(**cfg['initial_point'])
    points = [Point(**p) for p in cfg['path']]
    policy = Policy(**cfg['policy'])
    td = deepcopy(cfg['strc_terms'])
    td['templates'] = [DividendTemplate(**t) for t in td['templates']]
    terms = StrcTerms(**td)
    criteria = cfg.get('criteria', {})
    validate_growth(opening, payments, initial_point, points, policy, criteria, terms)
    journal = Journal(opening)
    initial_snapshot = mark(opening, initial_point)
    tracked = {p.id: p.opening_credit_native for p in payments}
    settled, snapshots, failure = set(), [], None
    common_issued_gross = strc_issued_gross = 0
    generated, decisions = [], []
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
        # Mark all STRC shares at the supplied preference; no fabricated daily history.
        pref_face = next(c.face_native for c in journal.state.claims if c.id==terms.claim_id)
        pref_change = journal.state.strc_shares*point.strc_liquidation_preference_usd-pref_face
        if abs(pref_change)>TOL:
            journal.post(point.date,'mark_strc_liquidation_claim',faces={terms.claim_id:pref_change},
                         details=dict(preference_usd=point.strc_liquidation_preference_usd))
        strc_gate = policy.strc_min_execution_price_usd <= point.strc_execution_price_usd <= policy.strc_max_execution_price_usd
        if policy.require_positive_backing_for_strc:
            strc_gate = strc_gate and mark(journal.state,point)['backing_usd']>0
        strc_auth = max(0,point.strc_authorization_gross_limit_usd-strc_issued_gross)
        strc_gross = min(point.strc_issue_target_gross_usd,point.strc_issue_cap_gross_usd,strc_auth) if strc_gate else 0
        decision = dict(date=point.date,strc_price_and_backing_gate_open=strc_gate,
                        strc_requested_gross_usd=point.strc_issue_target_gross_usd,
                        strc_market_capacity_gross_usd=point.strc_issue_cap_gross_usd,
                        strc_remaining_authorization_gross_usd=strc_auth,
                        strc_executed_gross_usd=strc_gross)
        decisions.append(decision)
        if strc_gross>TOL:
            new_shares = strc_gross/point.strc_execution_price_usd
            net = strc_gross*(1-policy.strc_issue_fee_rate)
            journal.post(point.date,'issue_strc',{'cash_usd':net,'strc_shares':new_shares},
                         faces={terms.claim_id:new_shares*point.strc_liquidation_preference_usd},
                         details=dict(gross_usd=strc_gross,fee_usd=strc_gross-net,
                                      price_usd=point.strc_execution_price_usd,new_shares=new_shares,
                                      added_stated_amount_usd=new_shares*100,
                                      added_annualized_distributions_usd=new_shares*100*point.strc_annual_rate))
            strc_issued_gross += strc_gross
            lot_number=sum(1 for e in journal.entries if e['action']=='issue_strc')
            for t in terms.templates:
                if t.record_date<point.date: continue
                p=Payment(id=f'strc_lot_{lot_number}_{t.id}',claim_id=terms.claim_id,
                          kind='dividend',payment_date=t.payment_date,
                          amount_native=new_shares*100*t.annual_rate/24,
                          accrual_start=t.record_date,accrual_end=t.accrual_end,
                          note='New STRC: issued before record cutoff; following full-period dividend')
                if p.id in tracked: raise ValueError('Generated payment id collision')
                payments.append(p);generated.append(asdict(p));tracked[p.id]=0
        point = reserve_point(point,journal.state,opening,policy,terms)
        decision['effective_reserve_floor_usd']=point.reserve_floor_usd
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
        pre_common_mark=mark(s,point)
        quote = pre_common_mark['conditional_common_price_usd']
        issue_price = quote*(1-policy.common_issue_discount) if quote else None
        may_issue = issue_price is not None and point.multiple>=policy.common_access_min_multiple
        net_premium=(issue_price*(1-policy.common_issue_fee_rate)/(pre_common_mark['backing_usd']/s.common_shares)
                     if issue_price else None)
        liquidity_allowed=may_issue and policy.common_fund_cash_shortfalls and (policy.common_issue_mode=='liquidity' or net_premium>=1)
        minimum_growth_premium=max(policy.common_growth_min_net_premium,
                                   1 if policy.common_issue_mode=='accretive_only' else 0)
        growth_allowed=may_issue and net_premium+RATIO_TOL>=minimum_growth_premium
        required_gross=need/(1-policy.common_issue_fee_rate) if liquidity_allowed else 0
        program_gross=point.common_program_target_gross_usd if growth_allowed else 0
        authorization=max(0,point.common_authorization_gross_limit_usd-common_issued_gross)
        gross=min(point.common_issue_cap_gross_usd,authorization,max(required_gross,program_gross))
        decision.update(common_quote_usd=quote,common_net_premium=net_premium,
                        common_funding_gate_open=bool(liquidity_allowed),common_growth_gate_open=bool(growth_allowed),
                        common_requested_program_gross_usd=point.common_program_target_gross_usd,
                        common_funding_need_gross_usd=required_gross,
                        common_market_capacity_gross_usd=point.common_issue_cap_gross_usd,
                        common_remaining_authorization_gross_usd=authorization,
                        common_executed_gross_usd=gross)
        if gross>TOL:
            net=gross*(1-policy.common_issue_fee_rate)
            journal.post(point.date,'issue_common_atm',{'cash_usd':net,'common_shares':gross/issue_price},
                         details=dict(gross_usd=gross,fee_usd=gross-net,price_usd=issue_price,
                                      funding_need_net_usd=need,net_premium=net_premium))
            common_issued_gross += gross
            need=max(0,need-net)
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
                          and gross <= TOL and strc_gross <= TOL and buyback_price is not None
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
        # Allocate only cash available after settlement and reserve designation.
        # Unsold/unspent funds carry forward; no forced deployment or round trip.
        s=journal.state
        repurchase_today=any(e['date']==point.date and e['action']=='repurchase_common' for e in journal.entries)
        purchase_spend=0
        if (policy.purchase_bitcoin and sold<=TOL and not repurchase_today
            and s.reserve_designation_usd+TOL>=point.reserve_floor_usd):
            available_cash=max(0,min(s.cash_usd,s.cash_usd+s.treasuries_usd-s.reserve_designation_usd
                                      -point.unreserved_cash_buffer_usd))
            net_capital=gross*(1-policy.common_issue_fee_rate)+strc_gross*(1-policy.strc_issue_fee_rate)
            budget=(available_cash if policy.deploy_existing_surplus_cash else net_capital)*policy.purchase_fraction
            unit_cost=point.btc_price_usd*(1+policy.btc_purchase_cost_rate)
            purchase_spend=min(budget,available_cash,point.btc_purchase_cap*unit_cost)
            if purchase_spend>TOL:
                bought=purchase_spend/unit_cost
                journal.post(point.date,'purchase_bitcoin',{'cash_usd':-purchase_spend,'btc':bought},
                             details=dict(cash_spent_usd=purchase_spend,bitcoin_market_value_usd=bought*point.btc_price_usd,
                                          execution_cost_usd=purchase_spend-bought*point.btc_price_usd,
                                          btc_price_usd=point.btc_price_usd))
        decision['bitcoin_purchase_cash_usd']=purchase_spend
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
    return GrowthResult(configuration_id, digest, cfg, complete, len(points), initial_snapshot,
                       snapshots, journal.entries, failure,
                       [asdict(p) for p in points[len(snapshots):]], assessment, journal.reconcile(), generated, decisions)
