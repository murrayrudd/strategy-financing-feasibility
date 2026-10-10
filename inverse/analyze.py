"""Build economic outputs from completed inverse searches, without rerunning models."""
import gzip,json,math,base64,html
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from study import HERE,INPUT,OUT,YEARS,write_json

def collect():
 jobs=json.loads((INPUT/'jobs.json').read_text());rows=[];frontiers=[];bands=[];witness=[]
 for j in jobs:
  p=OUT/'jobs'/j['job_id'];s=json.loads(p.with_suffix('.json').read_text())
  with gzip.open(p.with_suffix('.probes.json.gz'),'rt') as f:probes=json.load(f)
  for r in probes:r['event_common_drawdown']=min(0.,r['event_common_drawdown'])
  rows.extend(probes)
  for r in s['search_summary']:
   z={k:v for k,v in r.items() if k not in ('witness','feasible_bands','transitions')}
   z['observed_feasible_bands']=len(r['feasible_bands']);z['transition_count']=len(r['transitions'])
   low=z['lowest_feasible_tested'];z['lower_failing_coordinate']=None
   if low is not None:
    fail=[t['left'] for t in r['transitions'] if t['right']==low and not t['left_pass']]
    z['lower_failing_coordinate']=fail[0] if fail else None
    for k,v in r['witness'].items():
     if k not in z:z['witness_'+k]=v
    if j['axis']=='bitcoin':
     z['required_terminal_bitcoin_usd']=58714*low;z['required_bitcoin_total_return']=low-1;z['required_bitcoin_annual_return']=low**(1/YEARS)-1
   if j['axis']=='valuation':
    at1=next(r for r in probes if r['coordinate']==1.)
    static=1/(1+at1['common_return']) if at1['payments'] and at1['common_return'] is not None else None
    z['fixed_ledger_nominal_multiple_factor']=static
    if z['target']=='nominal_value' and static is not None and low is not None:z['inverse_minus_fixed_ledger_factor']=low-static
   frontiers.append(z)
   for bi,(lo,hi) in enumerate(r['feasible_bands']):
    bands.append({**{k:j[k] for k in ('job_id','axis','window','shape','premium','policy','regime','permission','timing')},'target':r['target'],'band_index':bi,'lowest_tested_pass':lo,'highest_tested_pass':hi})
 probes=pd.DataFrame(rows);f=pd.DataFrame(frontiers);b=pd.DataFrame(bands)
 probes.to_csv(OUT/'scenario_evaluations.csv',index=False);f.to_csv(OUT/'required_conditions.csv',index=False);b.to_csv(OUT/'feasible_bands.csv',index=False)
 return probes,f,b

def grouped(f):
 rows=[]
 selected=f[(f.axis=='valuation')&(f.policy=='reference')]
 for keys,g in selected.groupby(['target','permission','regime']):
  x=g.lowest_feasible_tested.dropna()
  rows.append(dict(target=keys[0],permission=keys[1],regime=keys[2],cases=len(g),feasible_within_domain=len(x),
   feasible_at_lower_bound=int((g.boundary_status=='feasible_at_lower_domain').sum()),observed_reversals=int(g.observed_reversal.sum()),
   minimum=float(x.min()) if len(x) else None,median=float(x.median()) if len(x) else None,maximum=float(x.max()) if len(x) else None))
 z=pd.DataFrame(rows);z.to_csv(OUT/'valuation_requirements_summary.csv',index=False);return z

def strc_comparisons(probes):
 s=probes[probes.kind=='strc'].copy();s.to_csv(OUT/'strc_outcomes.csv',index=False)
 keys=['base_id','future_strc_rate'];baseline=s[s.strc_scale==0].set_index(keys);rows=[]
 for _,r in s[s.strc_scale>0].iterrows():
  b=baseline.loc[(r.base_id,r.future_strc_rate)]
  d={k:r[k] for k in ('base_id','window','shape','premium','policy','regime','strc_scale','future_strc_rate')}
  d.update(baseline_funded=bool(b.funded),with_strc_funded=bool(r.funded),
   funding_gained=bool(r.funded and not b.funded),funding_lost=bool(b.funded and not r.funded),jointly_funded=bool(r.funded and b.funded),
   common_return_difference=r.common_return-b.common_return if r.funded and b.funded else None,
   bitcoin_per_share_difference=r.bitcoin_per_share_change-b.bitcoin_per_share_change if r.funded and b.funded else None,
   additional_common_gross_usd=r.common_gross_usd-b.common_gross_usd,
   additional_btc_sold=r.bitcoin_sold-b.bitcoin_sold,
   new_strc_annual_distribution_usd=r.annualized_new_strc_distribution_usd,
   new_strc_gross_usd=r.strc_gross_usd)
  rows.append(d)
 pairs=pd.DataFrame(rows);pairs.to_csv(OUT/'strc_matched_comparisons.csv',index=False)
 return s,pairs

def figures(f,pairs):
 folder=HERE/'figures';folder.mkdir(exist_ok=True)
 plt.rcParams.update({'font.family':'DejaVu Serif','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none','figure.dpi':140})
 sale=f[(f.axis=='sale_authority')&(f.target=='funded')].lowest_feasible_tested.dropna().sort_values()/1e6
 fig,ax=plt.subplots(figsize=(7.5,4.2));ax.step(sale,np.arange(1,len(sale)+1),where='post',color='black',lw=1.8)
 ax.set(xlabel='General-use sale authority required (million USD, gross)',ylabel='Number of baseline stopped paths supported',title='Sale authority needed to complete the financing program');ax.grid(axis='y',color='.87');fig.tight_layout()
 for ext in ('png','svg'):fig.savefig(folder/f'sale_authority_requirements.{ext}',bbox_inches='tight')
 plt.close(fig)
 q=f[(f.axis=='bitcoin')&(f.target=='nominal_value')&(f.policy=='reference')&(f.premium=='persistence')&(f.regime=='drawdown_closure')].copy()
 q=q.sort_values(['window','shape','permission']);fig,ax=plt.subplots(figsize=(8,5.5))
 for i,(_,r) in enumerate(q.iterrows()):
  found=pd.notna(r.lowest_feasible_tested);val=100*(r.lowest_feasible_tested-1) if found else 300
  ax.scatter(val,i,marker='o' if r.permission=='reserve_flexible' else 's',facecolor='black' if found else 'white',edgecolor='black',s=40)
  if not found:ax.annotate('outside search range',(val,i),xytext=(5,0),textcoords='offset points',fontsize=8,va='center')
 ax.set_yticks(range(len(q)),[r.window+' / '+('historical' if r['shape']=='historical' else 'smooth')+' / '+('flexible' if r.permission=='reserve_flexible' else 'restricted') for _,r in q.iterrows()])
 ax.axvline(0,color='.6',lw=.8);ax.set(xlabel='Lowest feasible tested terminal Bitcoin return (%)',title='Bitcoin conditions for preserving nominal common value\nPersistent valuation multiple; drawdown closure; reference issuance policy');ax.grid(axis='x',color='.9');fig.tight_layout()
 for ext in ('png','svg'):fig.savefig(folder/f'bitcoin_required_conditions.{ext}',bbox_inches='tight')
 plt.close(fig)
 fig,axes=plt.subplots(1,2,figsize=(9,3.4))
 for ax,key,title in zip(axes,['bitcoin_per_share_difference','common_return_difference'],['Bitcoin per share growth','Common share return']):
  for i,scale in enumerate((.5,1.)):
   a=pairs[(pairs.future_strc_rate==.12)&(pairs.strc_scale==scale)&pairs.jointly_funded][key].dropna()*100
   if len(a):
    ax.plot([a.quantile(.1),a.quantile(.9)],[i,i],color='.4',lw=2);ax.scatter(a.median(),i,color='black',s=38)
  ax.axvline(0,color='.6',ls='--',lw=.9);ax.set_yticks([0,1],['Half new STRC program','Full new STRC program']);ax.set(title=title);ax.set_ylim(-.35,1.35);ax.grid(axis='x',color='.9')
 axes[1].tick_params(labelleft=False);fig.suptitle('STRC changes asset accumulation and shareholder outcomes\n12% future rate; medians and 10th–90th percentile scenario ranges',fontsize=11);fig.supxlabel('Difference from no new STRC (percentage points)',fontsize=10);fig.tight_layout()
 for ext in ('png','svg'):fig.savefig(folder/f'strc_shareholder_tradeoffs.{ext}',bbox_inches='tight')
 plt.close(fig)

def report(probes,f,b,v,s,pairs):
 sale=f[(f.axis=='sale_authority')&(f.target=='funded')];values=sale.lowest_feasible_tested.dropna()
 selected=f[(f.axis=='valuation')&(f.target=='nominal_value')&(f.policy=='reference')]
 flex=selected[selected.permission=='reserve_flexible'].set_index(['window','shape','regime']);res=selected[selected.permission=='restricted'].set_index(['window','shape','regime'])
 recovered=int((flex.lowest_feasible_tested.notna()&res.lowest_feasible_tested.isna()).sum())
 z=pairs[(pairs.strc_scale==1)&(pairs.future_strc_rate==.12)];joint=z[z.jointly_funded]
 example=s[(s.window=='2022-05-01')&(s['shape']=='historical')&(s.premium=='persistence')&(s.policy=='reference')&(s.regime=='drawdown_closure')&(s.future_strc_rate==.12)].sort_values('strc_scale')
 case=f[(f.axis=='bitcoin')&(f.target=='nominal_value')&(f.policy=='reference')&(f.premium=='persistence')&(f.regime=='drawdown_closure')].sort_values(['window','shape','permission'])
 capacity=f[(f.axis=='capacity')&(f.target=='funded')]
 summary=dict(evaluations=len(probes),inverse_jobs=int(f.job_id.nunique()),strc_configurations=len(s),
  original_stopped_paths=len(sale),sale_authority_solutions=len(values),
  sale_authority_gross_usd=dict(min=float(values.min()),median=float(values.median()),max=float(values.max())),
  strc_full_vs_none_at_12pct=dict(comparisons=len(z),funding_gained=int(z.funding_gained.sum()),funding_lost=int(z.funding_lost.sum()),jointly_funded=len(joint),
   median_bitcoin_per_share_difference=float(joint.bitcoin_per_share_difference.median()),median_common_return_difference=float(joint.common_return_difference.median())),
  valuation_nominal_solutions_added_by_reserve_flexibility=recovered,
  searched_target_sets_with_reversals=int(f.observed_reversal.sum()),
  capacity_funded_solutions=int(capacity.lowest_feasible_tested.notna().sum()),capacity_searches=len(capacity))
 write_json(OUT/'economic_summary.json',summary)
 def table(df):return df.to_html(index=False,border=0,float_format=lambda x:f'{x:,.3f}',na_rep='Outside tested range',escape=True)
 def image(name):
  encoded=base64.b64encode((HERE/'figures'/name).read_bytes()).decode();return '<img src="data:image/png;base64,'+encoded+'" alt="'+name+'">'
 vt=v[v.target=='nominal_value'][['permission','regime','cases','feasible_within_domain','median','minimum','maximum']].copy()
 vt.columns=['Reserve use','Financing access','Cases','Solutions in range','Median required factor','Smallest','Largest']
 ex=example[['strc_scale','funded','strc_gross_usd','common_gross_usd','bitcoin_sold','bitcoin_per_share_change','common_return','annualized_strc_distribution_usd']].copy()
 for col in ('strc_gross_usd','common_gross_usd','annualized_strc_distribution_usd'):ex[col]/=1e9
 for col in ('bitcoin_per_share_change','common_return'):ex[col]*=100
 ex.columns=['New STRC program fraction','Payments and reserve compliant','STRC raised ($bn)','Common raised ($bn)','Bitcoin sold','Bitcoin/share change (%)','Common return (%)','Annual STRC distributions ($bn)']
 ct=case[['window','shape','permission','lowest_feasible_tested','required_terminal_bitcoin_usd','required_bitcoin_total_return']].copy();ct['required_bitcoin_total_return']*=100
 ct.columns=['Historical shape source','Shape','Reserve use','Required Bitcoin factor','Terminal Bitcoin price ($)','Terminal Bitcoin return (%)']
 ct['Terminal Bitcoin price ($)']=ct['Terminal Bitcoin price ($)'].round(-2)
 labels={'reserve_flexible':'General use allowed','restricted':'Restricted','smooth_matched':'Smooth','historical':'Historical','open':'Open','capacity':'Capacity constrained','drawdown_closure':'Drawdown closure'}
 vt=vt.replace(labels);ct=ct.replace(labels)
 rates=s[s.strc_scale==1].groupby('future_strc_rate').agg(cases=('funded','size'),funded=('funded','sum'),median_annual_strc=('annualized_strc_distribution_usd','median'),median_common_return=('common_return','median')).reset_index()
 rates['future_strc_rate']*=100;rates['median_annual_strc']/=1e9;rates['median_common_return']*=100
 rates.columns=['Future STRC rate (%)','Cases','Payments and reserve compliant','Median annual STRC distributions ($bn)','Median common return (%)']
 caprows=[]
 for permission in ('restricted','reserve_flexible'):
  for target,label in [('funded','Payments and reserve compliance'),('nominal_value','Nominal common-value preservation'),('bitcoin_per_share','Bitcoin per share preservation')]:
   g=f[(f.axis=='capacity')&(f.permission==permission)&(f.target==target)]
   caprows.append({'Reserve use':labels[permission],'Target':label,'Cases':len(g),'Feasible at zero capacity':int((g.lowest_feasible_tested==0).sum()),'Solutions up to twice baseline':int(g.lowest_feasible_tested.notna().sum()),'Median required capacity factor':g.lowest_feasible_tested.median()})
 captable=pd.DataFrame(caprows)
 captable.to_csv(OUT/'capacity_requirements_summary.csv',index=False)
 text=f'''<!doctype html><html lang="en-US"><meta charset="utf-8"><title>Strategy inverse financing model results</title><style>
 body{{font:17px/1.55 Georgia,serif;color:#171717;max-width:1150px;margin:45px auto;padding:0 28px}}h1{{font-size:32px;line-height:1.2}}h2{{margin-top:36px;font-size:24px}}p{{max-width:950px}}table{{width:100%;border-collapse:collapse;font:13px/1.4 Arial,sans-serif;margin:20px 0}}th,td{{padding:9px;border-bottom:1px solid #ccc;text-align:left}}th{{background:#eee}}img{{max-width:100%;height:auto;margin:15px 0}}.small{{font-size:14px;color:#444}}@media print{{body{{margin:12mm;font-size:11pt}}table{{font-size:8pt}}img{{max-height:220mm}}h2{{break-after:avoid}}}}
 </style><body><h1>Required conditions for treasury-company financing and shareholder outcomes</h1>
 <p>Modeling results · October 8, 2026 · Frozen Strategy corporate opening, June 30, 2026–September 30, 2027</p>
 <p><strong>The inverse framework now starts with an outcome and searches for the conditions that support it.</strong> Each candidate reruns financing, distributions, purchases, sales, reserves, and dilution through the full horizon. The outputs distinguish completed payments, reserve compliance, preservation of nominal common value, a 5% annual common-return target, and preservation of Bitcoin per basic share.</p>
 <p>The study contains {len(probes):,} evaluated configurations across {int(f.job_id.nunique()):,} inverse searches and {len(s):,} STRC comparisons. Requirements are reported as feasible ranges and neighboring passing/failing cases. {int(f.observed_reversal.sum()):,} target searches exhibit an observed reversal, confirming that a single monotone threshold would be inadequate for all outcomes.</p>
 <h2>Asset-use flexibility can resolve the baseline payment stops</h2>
 <p>All {len(values)} original stopped configurations have a sufficient general-use sale authorization within the $2 billion search limit. The lowest feasible tested authority ranges from ${values.min()/1e6:,.2f} million to ${values.max()/1e6:,.2f} million, with a median of ${values.median()/1e6:,.2f} million. Each reported transition is bracketed within $1 million. This is a cumulative gross authorization; actual sales and total Bitcoin liquidation are reported separately. These searches retain the original immediate-settlement timing so the permission effect can be compared directly with the original 335 stops.</p>
 {image('sale_authority_requirements.png')}
 <h2>Valuation requirements depend on the Bitcoin path and available financing</h2>
 <p>The primary frontier covers all 49 historical windows and their smooth counterparts, three financing-access regimes, and restricted or flexible reserve use. The table gives the closing valuation multiple required relative to its opening value, under the reference issuance policy. All candidates use next-business-day settlement with advance cash planning. Reserve flexibility adds {recovered} nominal-value solutions within the searched domain. The CSV also compares these complete-path requirements with simple repricing of an unchanged ledger.</p>
 {table(vt)}
 <p>Medians and ranges summarize cases with a solution in the tested domain; solution counts show where the composition differs.</p>
 <h2>Payment survival can require asset sales even when new financing is unavailable</h2>
 <p>With general reserve use allowed, all 108 focused configurations complete payments and meet the reserve floor at zero new-financing capacity. Only 48 preserve nominal common value at that setting, and none preserve Bitcoin per share. Under restricted use, 86 of 108 configurations can complete within the capacity search from zero to twice baseline; the median lowest sufficient capacity among those solutions is 0.488 times baseline. Capacity therefore supports distinct objectives: maintaining payment continuity, limiting Bitcoin liquidation, and protecting common value.</p>
 {table(captable)}
 <h2>The Bitcoin conditions required to preserve common value</h2>
 <p>The focused searches vary the terminal Bitcoin price while preserving each path's deviations from its smooth trend. Financing closure and volatility-based capacity are recalculated from the resulting path. The example below holds the valuation multiple persistent and applies the drawdown-closure regime. Differences between historical and smooth paths show why a terminal price alone does not define the required conditions.</p>
 {table(ct)}{image('bitcoin_required_conditions.png')}
 <h2>STRC changes both accumulation and the future payment burden</h2>
 <p>The STRC comparison varies new issuance from zero to half or all of the baseline program while leaving the common channel unchanged. It also varies future STRC rates from 10% to 16%, preserving already declared opening payments. Existing STRC remains in every configuration. At a 12% future rate, full new STRC issuance gains payment-and-reserve compliance in {int(z.funding_gained.sum())} matched cases and loses it in {int(z.funding_lost.sum())}; {len(joint)} pairs complete under both settings. Among those jointly funded pairs, median Bitcoin-per-share growth changes by {joint.bitcoin_per_share_difference.median()*100:+.2f} percentage points and the common return by {joint.common_return_difference.median()*100:+.2f} points.</p>
 <p>The worked May 2022 historical path below uses persistent valuation, drawdown closure, reference common issuance, and flexible reserve use. It reports the cash raised and the resulting STRC distribution burden alongside holdings and shareholder outcomes.</p>
 {table(ex)}{image('strc_shareholder_tradeoffs.png')}
 <p>With the full new-issuance program available, the rate comparisons below retain the same 108 market and policy combinations at each rate. Annual distributions include both opening and newly issued STRC. Return medians summarize completed paths; the completion counts remain visible.</p>{table(rates)}
 <h2>Why the inverse procedure retains more than one feasible range</h2>
 <p>One controlled example identifies the decision behind a nonmonotone result. With a compressed valuation multiple and constrained capacity, the reference policy issues $176.0 million of common shares on July 14, 2027 when net proceeds exceed net face backing per share. A slightly higher Bitcoin path moves that ratio below one, so the issue is skipped; the path later stops at the September principal payment under the original use restrictions. The feasible sets therefore reflect identifiable financing decisions, not only terminal asset values. The adjacent passing and failing runs are retained in <code>issuance_gate_example.json</code> and its worked ledgers.</p>
 <h2>Implications for the paper</h2>
 <p>The results support an argument about required conditions and management choices: payment continuity, common-share preservation, and Bitcoin accumulation have different feasible sets. General-use permissions, financing capacity and timing, and the mix of common and preferred issuance determine which outcomes can coexist. The model makes those trade-offs measurable without treating aggregate holdings as a sufficient indicator of resilience.</p>
 <p>These are bounded searches on a fixed 457-day corporate schedule. They identify sufficient tested conditions, not probabilities or infinite-horizon solvency. A passing point has a complete rerun; an interior boundary has adjacent passing and failing witnesses. Unobserved islands between grid points remain outside the search resolution. Future financing and valuation paths are scenario inputs.</p>
 <h2>Outputs and verification</h2>
 <p><code>required_conditions.csv</code> contains targets, lowest feasible tested settings, failure brackets, and economic outcomes at each passing witness. <code>feasible_bands.csv</code> retains every observed feasible interval. <code>scenario_evaluations.csv</code> contains all tested settings and failure classes. <code>strc_outcomes.csv</code> and <code>strc_matched_comparisons.csv</code> report financing, dilution, sales, and distribution obligations. Figures are supplied in grayscale PNG and editable SVG.</p>
 <p>The engine's accounting mechanisms are retained. The study-builder repair preserves engine 0.6.0 instead of silently selecting 0.5.0. Reproduction checks and economic identities are recorded in <code>verification.json</code>. All source configurations and search recipes are retained so each reported boundary can be regenerated.</p></body></html>'''
 (HERE/'Strategy_Inverse_Model_Results_2026-10-08.html').write_text(text)
 print(json.dumps(summary,indent=2))

if __name__=='__main__':
 p,f,b=collect();v=grouped(f);s,pairs=strc_comparisons(p);figures(f,pairs);report(p,f,b,v,s,pairs)
