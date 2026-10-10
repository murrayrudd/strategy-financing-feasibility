"""Strict JSON input and replay of retained configurations."""
from .core import Position, State, Terms
from .simulation import Event, Offer, Policy, run


def terms_from_dict(raw):
    d = dict(raw)
    for key in ('payment_dates', 'conversion_dates'):
        if key in d:
            d[key] = tuple(d[key])
    return Terms(**d)


def run_configuration(raw):
    if 'configuration' in raw:
        identifier = raw['configuration_id']
        cfg = dict(raw['configuration'])
    else:
        cfg = dict(raw)
        identifier = cfg.pop('configuration_id')
    version = cfg.pop('engine_version', '0.1.0')
    if version == '0.2.0':
        from .dated_v02 import run_dated_configuration
        return run_dated_configuration(cfg, identifier)
    if version == '0.3.0':
        from .dated import run_dated_configuration
        return run_dated_configuration(cfg, identifier)
    if version == '0.4.0':
        from .growth import run_dated_configuration
        return run_dated_configuration(cfg, identifier)
    if version != '0.1.0':
        raise ValueError('Configuration engine_version does not match this implementation')
    initial = dict(cfg.pop('initial'))
    initial['positions'] = [Position(terms_from_dict(p['terms']), p['face'], p.get('accrued', 0))
                            for p in initial.get('positions', [])]
    events = []
    for raw_event in cfg.pop('events'):
        e = dict(raw_event)
        offers = []
        for raw_offer in e.get('offers', []):
            o = dict(raw_offer)
            o['terms'] = terms_from_dict(o['terms'])
            offers.append(Offer(**o))
        e['offers'] = tuple(offers)
        events.append(Event(**e))
    policy = Policy(**cfg.pop('policy'))
    return run(State(**initial), tuple(events), policy, configuration_id=identifier, **cfg)
