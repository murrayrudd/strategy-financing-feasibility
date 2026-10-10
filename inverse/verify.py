"""Search fixtures and builder comparisons used by the public replication package."""
import argparse
import gzip
import json
from study import ROOT, OUT, search_grid, write_json, PricePath, run_configuration


def algorithm_checks():
 cases=[('interior_band',lambda x:.2<=x<=.6,2),('two_bands',lambda x:(.1<=x<=.3) or (.6<=x<=.9),4),
        ('empty',lambda x:False,0),('all',lambda x:True,0)]
 for name,rule,n in cases:
  cache={}
  def probe(x):cache[x]=({'p':rule(x)},None,None);return cache[x][0]
  probe.cache=cache;search_grid(probe,[i/10 for i in range(11)],['p'],1e-4)
  coords=sorted(cache);trans=[(a,b) for a,b in zip(coords,coords[1:]) if cache[a][0]['p']!=cache[b][0]['p']]
  assert len(trans)==n,(name,trans)
  assert all(b-a<=1e-4 for a,b in trans)
 return len(cases)

def builder_checks():
    from scenario_study import build
    with gzip.open(ROOT / 'data/builder_references.json.gz', 'rt') as f:
        references = json.load(f)['records']
    assert len(references) == 270
    for r in references:
        name = r['id']
        rest = name[11:]
        shape = 'smooth_matched' if rest.startswith('smooth_matched') else 'historical'
        rest = rest[len(shape) + 1:]
        premium = rest.split('_')[0]
        rest = rest[len(premium) + 1:]
        policy = 'principal_buffer' if rest.startswith('principal_buffer') else rest.split('_')[0]
        regime = rest[len(policy) + 1:]
        prices = PricePath(r['configuration']['metadata']['common_price_interface']['price_path'])
        c = build(prices, policy, premium, regime)
        assert c['engine_version'] == '0.6.0'
        result = run_configuration(c)
        assert result.snapshots == r['snapshots'], name
        assert result.assessment == r['assessment'], name
    return len(references)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--builder-only', action='store_true')
    args = parser.parse_args()
    if args.builder_only:
        result = dict(rebuilt_runs=builder_checks(), all_snapshots_and_assessments_identical=True, engine_version='0.6.0')
        write_json(OUT / 'builder_verification.json', result)
        print(json.dumps(result))
    else:
        from verify_package import main
        main()
