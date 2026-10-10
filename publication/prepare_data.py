from pathlib import Path
import pandas as pd
import numpy as np
import json,hashlib,shutil

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
DATA=ROOT/'data';DATA.mkdir(parents=True,exist_ok=True)
xp=BASE/'inverse/results/scenario_evaluations.csv'
fp=BASE/'inverse/results/required_conditions.csv'
X=pd.read_csv(xp);F=pd.read_csv(fp)
v=X[(X.axis=='valuation')&(X.policy=='reference')&X.coordinate.isin([.5,1,2])]
outcomes=['payments','funded','nominal_value','annual_5pct','bitcoin_per_share']
counts=v.groupby(['permission','coordinate'])[outcomes].sum().astype(int).reset_index()
sizes=v.groupby(['permission','coordinate']).size().reset_index(name='configurations')
counts=counts.merge(sizes,on=['permission','coordinate'])
assert (counts.configurations==294).all()
assert counts.funded.tolist()==[294,294,294,254,266,267]
assert counts.nominal_value.tolist()==[144,198,222,144,198,220]
assert counts.bitcoin_per_share.tolist()==[206,64,202,205,64,202]
counts.to_csv(DATA/'figure_1_outcome_counts.csv',index=False)

v=v[v.permission=='restricted']
keys=['window','coordinate','regime']
cols=keys+['job_id','funded','common_return','event_common_drawdown','scheduled_bitcoin_return']
p=v[v['shape']=='historical'][cols].merge(v[v['shape']=='smooth_matched'][cols],
                                         on=keys,suffixes=('_h','_s'),validate='one_to_one')
assert len(p)==441
assert np.allclose(p.scheduled_bitcoin_return_h,p.scheduled_bitcoin_return_s,atol=1e-12,rtol=1e-12)
assert int((p.funded_h&p.funded_s).sum())==379
assert int((~p.funded_h&p.funded_s).sum())==25
assert int((p.funded_h&~p.funded_s).sum())==4
b=p[p.funded_h&p.funded_s]
assert round(((b.event_common_drawdown_s-b.event_common_drawdown_h)*100).median(),1)==29.3
assert round(((b.common_return_h-b.common_return_s)*100).median(),2)==-.38
p.to_csv(DATA/'figure_2_matched_paths.csv',index=False)

q=F[(F.axis=='bitcoin')&(F.policy=='reference')&(F.premium=='persistence')&
    (F.regime=='drawdown_closure')&(F.permission=='restricted')&
    F.target.isin(['funded','nominal_value','annual_5pct','bitcoin_per_share'])]
cols=['job_id','window','shape','target','lowest_feasible_tested','required_terminal_bitcoin_usd',
      'lower_failing_coordinate','lower_domain','upper_domain','observed_reversal',
      'observed_feasible_bands']
q=q[cols]
assert len(q)==24 and q.required_terminal_bitcoin_usd.isna().sum()==1
assert not q.observed_reversal.any()
q.to_csv(DATA/'figure_3_bitcoin_requirements.csv',index=False)

pairs_path=BASE/'inverse/results/strc_matched_comparisons.csv'
z=pd.read_csv(pairs_path)
z=z[(z.future_strc_rate==.12)&z.jointly_funded]
assert len(z)==216
z.to_csv(DATA/'figure_4_strc_matched_comparisons.csv',index=False)

manifest={'inputs':[{ 'path':str(p.relative_to(BASE)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                    for p in [xp,fp,pairs_path]],
          'model_evaluations_retained':len(X),'new_model_evaluations':0,
          'verification':{'figure_1_matches_table_E1':True,'figure_2_matches_section_4_3':True,
                          'figure_3_matches_table_3':True,'figure_4_matched_cases':216}}
(ROOT/'source_manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
