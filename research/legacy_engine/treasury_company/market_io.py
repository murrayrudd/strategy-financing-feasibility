"""Versioned extension dispatcher; the original io.py remains byte-identical."""
from .io import run_configuration as run_original_configuration


def run_configuration(raw):
    if 'configuration' in raw:
        identifier=raw['configuration_id'];cfg=dict(raw['configuration'])
    else:
        cfg=dict(raw);identifier=cfg.pop('configuration_id')
    if cfg.get('engine_version')=='0.6.0':
        cfg.pop('engine_version')
        from .settlement_growth import run_dated_configuration
        return run_dated_configuration(cfg,identifier)
    if cfg.get('engine_version')!='0.5.0':
        return run_original_configuration(raw)
    cfg.pop('engine_version')
    from .market_growth import run_dated_configuration
    return run_dated_configuration(cfg,identifier)
