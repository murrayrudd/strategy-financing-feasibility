"""Economic checks independent of journal-prefix reconstruction."""
import math


def audit(result):
    c=result.configuration; policy=c['policy']; terms=c['strc_terms']; ident=terms['claim_id']
    points={p['date']:p for p in c['path']}
    max_error=0
    checks=0

    def equal(actual,expected,label,absolute_tolerance=1e-5):
        nonlocal max_error,checks
        error=abs(actual-expected);max_error=max(max_error,error);checks+=1
        if not math.isclose(actual,expected,rel_tol=1e-12,abs_tol=absolute_tolerance):
            raise AssertionError(f'{label}: {actual} != {expected}')

    previous=result.initial_snapshot['state']
    issues=[];common_gross=strc_gross=0
    for e in result.ledger:
        d=e['details'];after=e['after'];p=points[e['date']]
        if e['action']=='issue_common_atm':
            net=d['gross_usd']*(1-policy.get('common_issue_fee_rate',0))
            equal(after['cash_usd']-previous['cash_usd'],net,'ATM cash')
            equal(after['common_shares']-previous['common_shares'],d['gross_usd']/d['price_usd'],'ATM shares')
            common_gross+=d['gross_usd']
            if common_gross>p['common_authorization_gross_limit_usd']+1e-5:
                raise AssertionError('Common authorization exceeded')
        elif e['action']=='issue_strc':
            new=d['gross_usd']/p['strc_execution_price_usd']
            equal(after['strc_shares']-previous['strc_shares'],new,'STRC shares')
            equal(after['cash_usd']-previous['cash_usd'],d['gross_usd']*(1-policy.get('strc_issue_fee_rate',0)),'STRC cash')
            equal(after['common_shares'],previous['common_shares'],'No STRC common dilution')
            old_face=next(x['face_native'] for x in previous['claims'] if x['id']==ident)
            new_face=next(x['face_native'] for x in after['claims'] if x['id']==ident)
            equal(new_face-old_face,new*p['strc_liquidation_preference_usd'],'New preference')
            issues.append((e['date'],new));strc_gross+=d['gross_usd']
            if strc_gross>p['strc_authorization_gross_limit_usd']+1e-5:
                raise AssertionError('STRC authorization exceeded')
        elif e['action']=='purchase_bitcoin':
            amount=after['btc']-previous['btc']
            unit_cost=p['btc_price_usd']*(1+policy.get('btc_purchase_cost_rate',0))
            # Differencing large binary-float stocks loses more absolute
            # precision than the transaction amount suggests. Propagate the
            # input stock ULPs into USD rather than using an arbitrary wider
            # tolerance or replacing this independent stock-flow check.
            rounding_bound=4*(math.ulp(previous['cash_usd'])+math.ulp(after['cash_usd'])
                              +(math.ulp(previous['btc'])+math.ulp(after['btc']))*unit_cost
                              +math.ulp(amount*unit_cost))
            equal(previous['cash_usd']-after['cash_usd'],amount*unit_cost,
                  'Bitcoin purchase cash',max(1e-5,rounding_bound))
            if after['cash_usd']+after['treasuries_usd']-after['reserve_designation_usd']+1e-5<p['unreserved_cash_buffer_usd']:
                raise AssertionError('Purchase breaches cash buffer')
            if any(x['date']==e['date'] and x['action'].startswith('sell_bitcoin') for x in result.ledger):
                raise AssertionError('Same-event Bitcoin round trip')
        previous=after
    for t in terms['templates']:
        eligible=sum(shares for when,shares in issues if when<=t['record_date'])
        actual=sum(p['amount_native'] for p in result.generated_payments if p['payment_date']==t['payment_date'])
        equal(actual,eligible*terms['stated_amount_usd']*t['annual_rate']/24,'New-share dividend schedule')
    for s in result.snapshots:
        actual=next(x['face_native'] for x in s['state']['claims'] if x['id']==ident)
        equal(actual,s['state']['strc_shares']*s['strc_liquidation_preference_usd'],'Outstanding STRC preference')
        equal(s['annualized_strc_distributions_usd'],s['state']['strc_shares']*100*s['strc_annual_rate'],'Annualized STRC dividends')
    return dict(configuration_id=result.configuration_id,independent_economic_checks=checks,
                maximum_absolute_error=max_error,passed=True)
