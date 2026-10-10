"""Reproduce the four manuscript figures from the supplied plotting-data extracts."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
OUT=ROOT/'figures'
OUT.mkdir(exist_ok=True,parents=True)
plt.rcParams.update({
    'font.family':'DejaVu Serif','font.size':9,'axes.titlesize':10,
    'axes.labelsize':9,'xtick.labelsize':8,'ytick.labelsize':8,
    'axes.spines.top':False,'axes.spines.right':False,
    'axes.linewidth':.65,'xtick.major.width':.6,'ytick.major.width':.6,
    'xtick.major.size':3,'ytick.major.size':3,
    'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none',
    'svg.hashsalt':'strategy-financing-feasibility-v1','savefig.facecolor':'white','axes.unicode_minus':True,
})

def save(fig,stem):
    fig.savefig(OUT/(stem+'.png'),dpi=450)
    fig.savefig(OUT/(stem+'.svg'),metadata={'Date':None})
    fig.savefig(OUT/(stem+'.pdf'),metadata={'CreationDate':None,'ModDate':None})
    plt.close(fig)

# Figure 1: the same configurations are assessed against distinct objectives.
counts=pd.read_csv(DATA/'figure_1_outcome_counts.csv')
series=[('funded','Payments and reserves','o','-',0),
        ('nominal_value','Nominal common value','s','--',.30),
        ('bitcoin_per_share','Bitcoin per share','^',':',.55)]
fig,axes=plt.subplots(1,2,figsize=(6.6,3.65),sharey=True)
for ax,perm,title in zip(axes,['restricted','reserve_flexible'],
                        ['A  Restricted reserve use','B  Flexible reserve use']):
    q=counts[counts.permission==perm].sort_values('coordinate')
    ax.set_axisbelow(True)
    ax.grid(axis='y',color='.88',lw=.55)
    for target,label,marker,ls,gray in series:
        ax.plot(q.coordinate,q[target],marker=marker,markersize=5,
                color=str(gray),markerfacecolor='white' if target!='funded' else 'black',
                markeredgewidth=.9,linestyle=ls,lw=1.25,label=label)
    ax.set_xscale('log',base=2)
    ax.set_xlim(.43,2.32);ax.set_ylim(0,310)
    ax.set_xticks([.5,1,2],['0.5','1','2'])
    ax.set_yticks([0,75,150,225,294])
    ax.set_title(title,loc='left',pad=10)
axes[0].set_ylabel('Configurations meeting objective\n(out of 294)')
fig.supxlabel('Closing valuation multiplier relative to opening',fontsize=9,y=.185)
fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',
           bbox_to_anchor=(.52,.01),ncol=2,frameon=False,fontsize=8,
           columnspacing=1.4,handlelength=2.8)
fig.subplots_adjust(left=.12,right=.98,bottom=.33,top=.87,wspace=.17)
save(fig,'Figure_1_Payments_and_shareholder_objectives')

# Figure 2: each point represents one exactly matched historical/smooth pair.
p=pd.read_csv(DATA/'figure_2_matched_paths.csv')
both=p[p.funded_h&p.funded_s].copy()
assert len(p)==441 and len(both)==379
fig,axes=plt.subplots(1,2,figsize=(6.6,3.65))
metrics=[('common_return','A  Terminal common return',(-150,1250),[0,400,800,1200]),
         ('event_common_drawdown','B  Maximum drawdown',(-3,100),[0,25,50,75,100])]
for ax,(key,title,lim,ticks) in zip(axes,metrics):
    factor=-100 if key=='event_common_drawdown' else 100
    x=both[key+'_s']*factor;y=both[key+'_h']*factor
    ax.plot(lim,lim,ls='--',lw=.85,color='.5',zorder=1)
    ax.scatter(x,y,s=11,facecolors='none',edgecolors='.15',linewidths=.55,alpha=.60,zorder=2)
    ax.set(xlim=lim,ylim=lim,xticks=ticks,yticks=ticks)
    ax.set_aspect('equal',adjustable='box')
    ax.set_title(title,loc='left',pad=10)
    ax.set_xlabel('Smooth path (%)',labelpad=5)
    ax.set_ylabel('Historical path (%)',labelpad=3)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{x:,.0f}'))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{x:,.0f}'))
    delta=float(np.median(y-x))
    label=f'Median difference\n{delta:+.2f} percentage points'
    ax.text(.045,.955,label,transform=ax.transAxes,ha='left',va='top',fontsize=7.4,
            bbox=dict(facecolor='white',edgecolor='none',alpha=.94,pad=1.5))
fig.legend([Line2D([],[],ls='--',lw=.85,color='.5')],['Equal outcomes under both paths'],
           loc='lower center',bbox_to_anchor=(.52,.015),frameon=False,fontsize=8)
fig.subplots_adjust(left=.105,right=.98,bottom=.20,top=.87,wspace=.42)
save(fig,'Figure_2_Matched_endpoints_and_interim_stress')

# Figure 3: show the first tested success, without asserting monotonic feasibility.
req=pd.read_csv(DATA/'figure_3_bitcoin_requirements.csv')
targets=['funded','nominal_value','annual_5pct','bitcoin_per_share']
labels=['Payments and\nreserve floor','Nominal\ncommon value',
        '5% annual\ncommon return','Bitcoin\nper share']
fig,axes=plt.subplots(1,3,figsize=(6.6,3.75),sharey=True)
for ax,window,title in zip(axes,['2021-11-01','2022-05-01','2023-01-01'],
                           ['A  Nov 2021','B  May 2022','C  Jan 2023']):
    q=req[req.window==window]
    ax.axvline(58.714,color='.65',ls=':',lw=.9,zorder=0)
    for i,target in enumerate(targets):
        vals=[]
        for shape,offset,fill in [('historical',.10,'black'),('smooth_matched',-.10,'white')]:
            r=q[(q['shape']==shape)&(q.target==target)].iloc[0]
            val=r.required_terminal_bitcoin_usd/1000
            y=3-i+offset
            if pd.notna(val):
                ax.scatter(val,y,s=24,facecolors=fill,edgecolors='black',linewidths=.85,zorder=3)
                vals.append((val,y))
            else:
                ax.text(.99,y,'None in range',transform=ax.get_yaxis_transform(),
                        ha='right',va='center',fontsize=7.0,fontstyle='italic')
        if len(vals)==2:
            ax.plot([v[0] for v in vals],[v[1] for v in vals],color='.65',lw=.8,zorder=1)
    ax.set(xlim=(0,247),ylim=(-.5,3.5),xticks=[0,100,200],yticks=[3,2,1,0])
    ax.set_yticklabels(labels)
    ax.tick_params(axis='y',length=0,pad=8)
    ax.spines['left'].set_visible(False)
    ax.set_title(title,loc='left',pad=9)
    ax.grid(axis='y',color='.90',lw=.5)
fig.supxlabel('Lowest successful tested terminal Bitcoin price ($ thousands)',fontsize=9,y=.195)
handles=[Line2D([],[],ls='none',marker='o',color='black',mfc='black',ms=5),
         Line2D([],[],ls='none',marker='o',color='black',mfc='white',ms=5),
         Line2D([],[],color='.65',ls=':',lw=.9)]
fig.legend(handles,['Historical path','Smooth path','Opening price ($58,714)'],
           loc='lower center',bbox_to_anchor=(.53,.025),ncol=2,frameon=False,fontsize=8,
           columnspacing=1.2,handlelength=2)
fig.subplots_adjust(left=.22,right=.98,bottom=.31,top=.86,wspace=.22)
save(fig,'Figure_3_Bitcoin_conditions_by_objective')

# Figure 4: exact matched-case calculations used for the manuscript.
pairs=pd.read_csv(DATA/'figure_4_strc_matched_comparisons.csv')
assert len(pairs)==216
plt.rcdefaults()
plt.rcParams.update({'svg.hashsalt':'strategy-financing-feasibility-v1','pdf.fonttype':42})
plt.rcParams.update({'font.family':'DejaVu Serif','font.size':9,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none','axes.linewidth':.65})
fig,axes=plt.subplots(1,2,figsize=(6.6,2.4),sharex=True,sharey=True)
for ax,key,title in zip(axes,['bitcoin_per_share_difference','common_return_difference'],['A  Bitcoin per share','B  Common return']):
 for i,scale in enumerate([.5,1.]):
  z=pairs[pairs.strc_scale==scale][key]*100
  ax.plot([z.min(),z.max()],[i,i],color='.5',lw=.8)
  ax.plot([z.quantile(.1),z.quantile(.9)],[i,i],color='black',lw=3,solid_capstyle='butt')
  ax.scatter(z.median(),i,s=31,facecolor='white',edgecolor='black',linewidth=1,zorder=3)
  ax.annotate(f'{z.median():.2f}',(z.median(),i),xytext=(0,10),textcoords='offset points',ha='center',fontsize=8)
 ax.axvline(0,color='.55',lw=.75,ls='--');ax.set_title(title,loc='left',fontsize=10,pad=8)
 ax.set_xlim(-2,32);ax.set_ylim(-.42,1.45);ax.set_xticks([0,10,20,30]);ax.set_yticks([0,1],['Half program','Full program'])
 ax.tick_params(axis='y',length=0);ax.tick_params(axis='x',width=.6,length=3)
 ax.spines['left'].set_visible(False)
fig.supxlabel('Difference from no new STRC (percentage points)',fontsize=9,y=.025)
fig.subplots_adjust(left=.16,right=.98,bottom=.24,top=.81,wspace=.15)
fig.savefig(OUT/'Figure_4_STRC_effects.png',dpi=400)
fig.savefig(OUT/'Figure_4_STRC_effects.svg',metadata={'Date':None})
fig.savefig(OUT/'Figure_4_STRC_effects.pdf',metadata={'CreationDate':None,'ModDate':None})
plt.close(fig)

print(json.dumps({'figures_rebuilt':4,'matched_pairs':441,'jointly_compliant_pairs':379,'strc_comparisons':len(pairs)},indent=2))
