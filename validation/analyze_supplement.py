from pathlib import Path
import json
import pandas as pd
R=Path(__file__).parent;O=R/'results'
s=pd.read_csv(O/'supplemental_runs.csv')
b=pd.concat([pd.read_csv(O/'scenario_archives'/f'{w}.csv') for w in ['2022-05-01','2023-01-01']],ignore_index=True)
k=['window','shape','premium','policy','regime'];m=s.merge(b,on=k,suffixes=('_control','_main'));assert len(m)==198
m['return_change']=m.return_control-m.return_main;m['btc_share_change']=m.btc_per_share_change_control-m.btc_per_share_change_main
m.to_csv(O/'supplemental_pairs.csv',index=False)
rows=[]
for key,g in m.groupby(['control','volatility','reference_horizon_years'],sort=False):
 both=g[g.funded_main & g.funded_control]
 rows.append(dict(control=key[0],volatility=float(key[1]),reference_horizon_years=float(key[2]),n=len(g),control_funded=int(g.funded_control.sum()),main_funded=int(g.funded_main.sum()),control_only_funded=int((g.funded_control & ~g.funded_main).sum()),main_only_funded=int((~g.funded_control & g.funded_main).sum()),joint_funded=len(both),return_change_min=float(both.return_change.min()),return_change_median=float(both.return_change.median()),return_change_max=float(both.return_change.max())))
# Paired policy ranking under each alternative reference.
x=s[s.control=='valuation_reference'];ref=x[x.policy=='reference'];others=x[x.policy=='adaptive'];keys=['window','premium','regime','volatility','reference_horizon_years'];t=others.merge(ref,on=keys,suffixes=('_adaptive','_reference'));both=t[t.funded_adaptive&t.funded_reference]
ranking=dict(comparisons=len(t),adaptive_only_funded=int((t.funded_adaptive&~t.funded_reference).sum()),reference_only_funded=int((~t.funded_adaptive&t.funded_reference).sum()),joint_funded=len(both),adaptive_higher_btc_per_share=int((both.btc_per_share_change_adaptive>both.btc_per_share_change_reference+1e-10).sum()),adaptive_lower_btc_per_share=int((both.btc_per_share_change_adaptive<both.btc_per_share_change_reference-1e-10).sum()),adaptive_higher_return=int((both.return_adaptive>both.return_reference+1e-10).sum()),adaptive_lower_return=int((both.return_adaptive<both.return_reference-1e-10).sum()))
res={'runs':len(s),'controls':rows,'valuation_reference_policy_comparison':ranking,'interpretation':'Targeted, retrospective sensitivity controls; no global robustness or probability claim'}
(O/'supplemental_summary.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2))
