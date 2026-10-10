"""Finite-grid inverse conditions on the frozen 0.4.0 engine; retain every trial."""
from copy import deepcopy
from datetime import date
import hashlib
import json
import lzma
from pathlib import Path
import sys

from run_comparisons import START, END, factor_at
from run_financing import configuration as old_configuration, summarize
from treasury_company.io import run_configuration
from check_financing import audit

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'feasibility'
DEFAULTS = dict(family='smooth', terminal_return=0.0, access=1.0,
                terminal_multiple=1.25, buffer_usd=1_100_000_000.0,
                general_sale_usd=0.0, rate=.12, issue_fee=.01,
                channel='both', equal_capital=False)


def parameters(**changes):
    if set(changes)-set(DEFAULTS):
        raise ValueError('Unknown analysis parameter')
    p = dict(DEFAULTS, **changes)
    for k, v in p.items():
        if isinstance(DEFAULTS[k], float):
            p[k] = round(float(v), 12)
    return p


def configuration(**changes):
    p = parameters(**changes)
    # Include the same rate-effective-date event in all controlled comparisons.
    c = old_configuration('flat', p['channel'], 'rate14')
    if p['family'] == 'smooth':
        knots = [(str(START), 1), (str(END), 1+p['terminal_return'])]
    else:
        knot_date = {'early': '2026-12-15', 'late': '2027-06-15'}[p['family']]
        knots = [(str(START), 1), (knot_date, .6), (str(END), 1+p['terminal_return'])]
    for t in c['strc_terms']['templates']:
        t['annual_rate'] = p['rate'] if t['accrual_end'] >= '2027-01-01' else .12
    by_id = {t['id']: t for t in c['strc_terms']['templates']}
    for pay in c['payments']:
        if pay['claim_id'] == 'STRC' and not pay['opening_credit_native']:
            pay['amount_native'] = c['opening']['strc_shares']*100*by_id[pay['id']]['annual_rate']/24
    for point in [c['initial_point']]+c['path']:
        tau = (date.fromisoformat(point['date'])-START).days/(END-START).days
        point['btc_price_usd'] = 58_714*factor_at(point['date'], knots)
        point['multiple'] = 1.25*(p['terminal_multiple']/1.25)**tau
        point['unreserved_cash_buffer_usd'] = p['buffer_usd']
        point['btc_general_use_gross_limit_usd'] = p['general_sale_usd']
        point['strc_annual_rate'] = p['rate'] if point['date'] >= '2027-01-01' else .12
        point['common_issue_cap_gross_usd'] *= p['access']
        point['strc_issue_cap_gross_usd'] *= p['access']
        if p['equal_capital']:
            target = 200_000_000 if p['channel'] == 'both' else 400_000_000
            if p['channel'] in ('common', 'both'):
                point['common_program_target_gross_usd'] = target if point['common_program_target_gross_usd'] else 0
                point['common_authorization_gross_limit_usd'] = target*13
            if p['channel'] in ('strc', 'both'):
                point['strc_issue_target_gross_usd'] = target if point['strc_issue_target_gross_usd'] else 0
                point['strc_issue_cap_gross_usd'] = min(point['strc_issue_cap_gross_usd'], target)
                point['strc_authorization_gross_limit_usd'] = target*13
    c['policy'].update(common_issue_fee_rate=p['issue_fee'], strc_issue_fee_rate=p['issue_fee'],
                       common_fund_cash_shortfalls=not p['equal_capital'])
    c['metadata']['v04_assumptions_for_provenance_only'] = c['metadata'].pop('assumptions')
    c['metadata'].update(analysis_version='0.5.0', parameters=p, path_id=p['family'],
                         path_label=p['family'], path_knots=knots, variant='feasibility',
                         purpose='Finite-grid complete-path inverse conditions',
                         constant_multiple=1.25 if p['terminal_multiple']==1.25 else None,
                         general_sale_authorization_assumed=p['general_sale_usd']>0,
                         source_review='PARAMETER_EVIDENCE.md',
                         assumptions=[
                             'FEASIBILITY_DESIGN.md and the complete numerical parameters govern these runs; older notes are provenance only.',
                             'Initial multiple is always 1.25; terminal multiple is reached through a log-linear path and affects financing as well as valuation.',
                             'Access scales market-capacity ceilings only; program targets and cumulative budgets do not scale. Proceeds and financing mix are outputs.',
                             'The buffer limits discretionary purchases but may fund later commitments. Sale-purpose permission is independently supplied.',
                             'STRC rate changes apply from January 1, 2027 to original and newly issued shares, preserving opening credits.',
                             'No probabilities, estimated demand curve, daily feasibility guarantee, optimal allocation claim, or default waterfall is implied.'
                         ])
    key = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()[:20]
    c['configuration_id'] = 'feasibility_'+key
    c['policy']['name'] = 'Conditional feasibility '+key
    return json.loads(json.dumps(c, allow_nan=False))


def classify(r):
    a = r.assessment
    if not r.complete:
        return 0
    if not a['reserve_compliant_throughout']:
        return 1
    if not a['criteria']['equity_mapping_defined_throughout']:
        return 2
    return 4 if a['jointly_supported'] else 3


def row_for(r):
    row = summarize(r)
    marks = [r.initial_snapshot]+r.snapshots
    row.update(parameters=r.configuration['metadata']['parameters'], input_sha256=r.input_sha256,
               category=classify(r), funding_supported=r.complete and r.assessment['reserve_compliant_throughout'],
               equity_mapping_supported=r.assessment['criteria']['equity_mapping_defined_throughout'],
               first_undefined_mapping_date=next((s.get('date', s['state']['asof']) for s in marks if not s['quote_defined']), None),
               minimum_backing_usd=min(s['backing_usd'] for s in marks),
               minimum_reserve_surplus_usd=min(s['state']['reserve_designation_usd']-s['reserve_floor_usd'] for s in marks),
               terminal_price_input=r.configuration['path'][-1]['btc_price_usd'],
               processed_points=len(r.snapshots), expected_points=r.expected_event_count,
               unprocessed_points=len(r.unprocessed_path),
               new_preferred_claim_usd=r.snapshots[-1]['state']['strc_shares']*100-r.initial_snapshot['state']['strc_shares']*100,
               basic_share_dilution=r.snapshots[-1]['state']['common_shares']/r.initial_snapshot['state']['common_shares']-1)
    return row


def refined_switches(samples, evaluate, criterion, tolerance):
    """Bracket every observed switch, including reversals; never infer monotonicity."""
    out = []
    for (lo, left), (hi, right) in zip(samples, samples[1:]):
        if bool(left[criterion]) == bool(right[criterion]):
            continue
        start, end = lo, hi
        while hi-lo > tolerance:
            mid = (lo+hi)/2
            trial = evaluate(mid)
            if bool(trial[criterion]) == bool(left[criterion]):
                lo, left = mid, trial
            else:
                hi, right = mid, trial
        out.append(dict(lower=lo, upper=hi, lower_supported=bool(left[criterion]),
                        upper_supported=bool(right[criterion]), lower_id=left['id'], upper_id=right['id'],
                        initial_bracket=[start, end]))
    return out


class Study:
    def __init__(self, archive):
        self.archive = archive
        self.rows = {}
        self.groups = {}
        self.thresholds = []
        self.checks = 0
        self.max_error = 0

    def run(self, **changes):
        c = configuration(**changes)
        ident = c['configuration_id']
        if ident in self.rows:
            return self.rows[ident]
        r = run_configuration(c)
        d = r.to_dict()
        encoded = json.dumps(d, separators=(',', ':'), allow_nan=False)
        # Exact reconstruction after serialization, including incomplete paths.
        if run_configuration(json.loads(encoded)).to_dict() != d:
            raise AssertionError('Serialized replay differs: '+ident)
        verification = audit(r)
        if not r.reconciliation['all_prefixes_reconciled']:
            raise AssertionError('Journal prefix did not reconcile')
        self.checks += verification['independent_economic_checks']
        self.max_error = max(self.max_error, verification['maximum_absolute_error'])
        row = row_for(r)
        row['archive_line'] = len(self.rows)+1
        row['record_sha256'] = hashlib.sha256(encoded.encode()).hexdigest()
        row['replay_identical'] = True
        self.archive.write(encoded+'\n')
        self.rows[ident] = row
        if len(self.rows)%100 == 0:
            print(f'Retained and checked {len(self.rows)} complete input/result records', flush=True)
        return row

    def group(self, name, **changes):
        row = self.run(**changes)
        self.groups.setdefault(name, []).append(row['id'])
        return row

    def slice(self, label, axis, values, criterion='primary_joint_supported', tolerance=.0001, **fixed):
        samples = [(x, self.run(**dict(fixed, **{axis:x}))) for x in values]
        switches = refined_switches(samples, lambda x:self.run(**dict(fixed, **{axis:x})), criterion, tolerance)
        intervals = []
        active = None
        for x, row in samples:
            if row[criterion]:
                if active is None:
                    active = dict(first_sample=x, last_sample=x, first_id=row['id'], last_id=row['id'])
                else:
                    active.update(last_sample=x, last_id=row['id'])
            elif active is not None:
                intervals.append(active); active = None
        if active is not None:
            intervals.append(active)
        item = dict(label=label, axis=axis, criterion=criterion, fixed=parameters(**fixed),
                    sample_values=values, sample_ids=[r['id'] for _,r in samples],
                    sampled_supported_intervals=intervals, observed_switches=switches,
                    tolerance=tolerance, supported_samples=sum(bool(r[criterion]) for _,r in samples),
                    limitation='All sampled intervals and observed switches retained. Subgrid islands and unsampled-event behavior unresolved; no global uniqueness claim.')
        self.thresholds.append(item)
        return item


def main(resume=False):
    DEST.mkdir(exist_ok=True)
    returns = [i/100 for i in range(-70, 61, 5)]
    central_returns = [i/100 for i in range(-50, 51, 5)]
    access_values = [i/10 for i in range(11)]
    if resume and not (DEST/'index.json').exists():
        raise ValueError('Cannot resume without an existing retained analysis')
    with lzma.open(DEST/'paths.jsonl.xz', 'at' if resume else 'wt', encoding='utf-8', preset=6) as archive:
        s = Study(archive)
        if resume:
            s.rows={r['id']:r for r in json.loads((DEST/'index.json').read_text())}
            previous=json.loads((DEST/'verification.json').read_text())
            s.checks=previous['independent_economic_checks']
            s.max_error=previous['maximum_absolute_economic_error']
        for a in access_values:
            for ret in returns:
                s.group('capacity_map', access=a, terminal_return=ret)
            s.slice(f'capacity_{a:.1f}', 'terminal_return', returns, access=a)
        for m in [i/100 for i in range(75,176,5)]:
            for ret in central_returns:
                s.group('valuation_map', terminal_multiple=m, terminal_return=ret)
            if m in (.75,1,1.25,1.5,1.75):
                s.slice(f'valuation_{m:.2f}', 'terminal_return', central_returns, terminal_multiple=m)
        for permission in (0,2_000_000_000):
            for a in access_values:
                for b in range(13):
                    s.group('buffer_map', access=a, buffer_usd=b*100_000_000, general_sale_usd=permission)
        for path, family, ret in [('flat','smooth',0),('up25','smooth',.25),('down25','smooth',-.25),
                                  ('early_recovery','early',0),('late_recovery','late',0)]:
            for channel in ('common','strc','both'):
                row=s.group('equal_capital', family=family, terminal_return=ret, channel=channel, equal_capital=True)
                if not row['completed'] or abs(row['common_gross_usd']+row['strc_gross_usd']-5_200_000_000)>1e-4:
                    raise AssertionError('Equal-capital comparison failed to raise equal gross capital')
        for family in ('early','late'):
            for a in (.2,.5,1):
                s.slice(f'{family}_capacity_{a:.1f}', 'terminal_return', [i/100 for i in range(-20,61,5)], family=family, access=a)
        for rate in (.10,.12,.14):
            for fee in (.0025,.01,.02):
                s.slice(f'rate_{rate:.3f}_fee_{fee:.4f}', 'terminal_return', central_returns, rate=rate, issue_fee=fee)
        for a in (.1,.2,.25,.5,1):
            s.slice(f'buffer_capacity_{a:.2f}', 'buffer_usd', [i*50_000_000 for i in range(25)],
                    criterion='funding_supported', tolerance=100_000, access=a)
        for buffer in (0,100_000_000,500_000_000,1_100_000_000):
            s.slice(f'access_buffer_{buffer/1e9:.1f}', 'access', [i/20 for i in range(21)],
                    criterion='funding_supported', buffer_usd=buffer)
        # Targeted follow-up to the observed nonmonotonic capacity/return relation:
        # inspect a complete access slice near the equity-support boundary.
        s.slice('access_at_btc_2.75pct', 'access', [i/20 for i in range(21)], terminal_return=.0275)
        rows = list(s.rows.values())
    (DEST/'index.json').write_text(json.dumps(rows, indent=2, allow_nan=False)+'\n')
    (DEST/'groups.json').write_text(json.dumps(s.groups, indent=2)+'\n')
    (DEST/'thresholds.json').write_text(json.dumps(s.thresholds, indent=2, allow_nan=False)+'\n')
    verification = dict(analysis_version='0.5.0', engine_version='0.4.0', new_records=len(rows),
                        independent_economic_checks=s.checks, maximum_absolute_economic_error=s.max_error,
                        all_serialized_replays_identical=True, all_journal_prefixes_reconciled=True,
                        thresholds=len(s.thresholds), observed_switches=sum(len(t['observed_switches']) for t in s.thresholds),
                        probabilities_assigned=False)
    (DEST/'verification.json').write_text(json.dumps(verification, indent=2)+'\n')
    print(json.dumps(verification, indent=2), flush=True)


if __name__ == '__main__':
    main(resume='--resume' in sys.argv)
