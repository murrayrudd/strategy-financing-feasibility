"""Descriptive, matched comparisons of the crossed conditional design."""
from pathlib import Path
import json,math
import pandas as pd
R=Path(__file__).parent;O=R/'results'
def describe(s):
    s=s.dropna()
    return {'n':int(len(s)),'min':float(s.min()),'median':float(s.median()),'max':float(s.max())} if len(s) else {'n':0}
def main():
    d=pd.read_csv(O/'scenario_runs.csv');assert len(d)==2646 and not d.id.duplicated().any()
    assert d.loc[~d.funded,'return'].isna().all()
    groups=d.groupby(['regime','premium','policy'],sort=False).agg(n=('id','size'),funded=('funded','sum'),nominal=('nominal_value_supported','sum'),bitcoin_per_share=('btc_per_share_supported','sum'),median_return=('return','median'),median_btc_share=('btc_per_share_change','median')).reset_index()
    groups.to_csv(O/'scenario_groups.csv',index=False)
    keys=['window','premium','policy','regime']
    seq=d[d['shape']=='historical'].merge(d[d['shape']=='smooth_matched'],on=keys,suffixes=('_historical','_smooth'))
    assert len(seq)==1323 and (seq.bitcoin_return_historical-seq.bitcoin_return_smooth).abs().max()<1e-12
    seq['funding_switch']=seq.funded_historical!=seq.funded_smooth
    seq['return_difference']=seq.return_historical-seq.return_smooth
    seq['btc_share_difference']=seq.btc_per_share_change_historical-seq.btc_per_share_change_smooth
    seq['drawdown_difference']=seq.drawdown_historical-seq.drawdown_smooth
    seq.to_csv(O/'sequence_pairs.csv',index=False)
    sequence=[]
    for (regime,premium),g in seq.groupby(['regime','premium'],sort=False):
        both=g[g.funded_historical & g.funded_smooth]
        sequence.append(dict(regime=regime,premium=premium,n=len(g),historical_only=int((g.funded_historical & ~g.funded_smooth).sum()),smooth_only=int((~g.funded_historical & g.funded_smooth).sum()),both_funded=len(both),return_difference=describe(both.return_difference),drawdown_difference=describe(both.drawdown_difference)))
    keys=['window','shape','premium','regime'];ref=d[d.policy=='reference']
    policies=[]
    for policy in ['adaptive','principal_buffer']:
        pairs=d[d.policy==policy].merge(ref,on=keys,suffixes=('_policy','_reference'));assert len(pairs)==882
        pairs['return_difference']=pairs.return_policy-pairs.return_reference
        pairs['btc_share_difference']=pairs.btc_per_share_change_policy-pairs.btc_per_share_change_reference
        pairs['common_proceeds_difference']=pairs.common_gross_policy-pairs.common_gross_reference
        pairs.to_csv(O/(policy+'_pairs.csv'),index=False)
        for premium,g in pairs.groupby('premium',sort=False):
            both=g[g.funded_policy & g.funded_reference]
            policies.append(dict(policy=policy,premium=premium,n=len(g),policy_only=int((g.funded_policy & ~g.funded_reference).sum()),reference_only=int((~g.funded_policy & g.funded_reference).sum()),both_funded=len(both),higher_return=int((both.return_difference>1e-10).sum()),lower_return=int((both.return_difference < -1e-10).sum()),higher_btc_share=int((both.btc_share_difference>1e-10).sum()),lower_btc_share=int((both.btc_share_difference < -1e-10).sum()),return_difference=describe(both.return_difference),btc_share_difference=describe(both.btc_share_difference)))
    keys=['window','shape','policy','regime'];persist=d[d.premium=='persistence'];decomps=[]
    for prem,fac in [('compression',.5),('expansion',2.)]:
        pairs=d[d.premium==prem].merge(persist,on=keys,suffixes=('_changed','_persistent'));pairs=pairs[pairs.funded_changed & pairs.funded_persistent].copy()
        pairs['total_log_quote_change']=((1+pairs.return_changed)/(1+pairs.return_persistent)).apply(math.log)
        pairs['direct_log_multiple_change']=math.log(fac)
        pairs['corporate_log_change']=pairs.total_log_quote_change-math.log(fac)
        pairs.to_csv(O/(prem+'_attribution.csv'),index=False)
        decomps.append(dict(premium=prem,n=len(pairs),direct_log_multiple_change=math.log(fac),corporate_log_change=describe(pairs.corporate_log_change),total_log_quote_change=describe(pairs.total_log_quote_change)))
    summary=dict(runs=len(d),funded=int(d.funded.sum()),nominal=int(d.nominal_value_supported.sum()),bitcoin_per_share=int(d.btc_per_share_supported.sum()),funding_switches_matched_sequence=int(seq.funding_switch.sum()),sequence_comparisons=sequence,policy_comparisons=policies,premium_attribution=decomps,failure_dates=d[~d.funded].failure_date.value_counts().to_dict(),max_ledger_error=float(d.max_ledger_error.max()),interpretation='Finite unweighted, overlapping scenario counts; not estimated probabilities or independent replications')
    (O/'study_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
