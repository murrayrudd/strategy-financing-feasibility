from pathlib import Path
from lxml import etree
import json,re,csv
D=Path(__file__).parent/'data'
allrows=[]
for meta in json.loads((D/'filing_manifest.json').read_text()):
 if 'error' in meta:continue
 root=etree.HTML((D/'filings'/(meta['date']+'.html')).read_bytes())
 contexts={}
 for e in root.iter():
  if isinstance(e.tag,str) and e.tag.split(':')[-1]=='context':
   vals={};dims=[]
   for c in e.iter():
    tag=c.tag.split(':')[-1] if isinstance(c.tag,str) else ''
    if tag in ['instant','startdate','enddate']:vals[tag]=''.join(c.itertext())
    elif tag=='explicitmember':dims.append((c.get('dimension'),''.join(c.itertext())))
   contexts[e.get('id')]={**vals,'dims':dims}
 facts=[]
 for e in root.iter():
  name=e.get('name','');ctx=e.get('contextref')
  if not ctx:continue
  raw=''.join(e.itertext()).strip().replace(',','').replace('−','-')
  try:v=float(raw)*10**int(e.get('scale',0))*(-1 if e.get('sign')=='-' else 1)
  except:continue
  facts.append({'name':name,'value':v,'unit':e.get('unitref'),'context':contexts.get(ctx,{}),'raw':raw})
 # Store complete numerical facts for reproducible extraction; no inferred values.
 (D/'filings'/(meta['date']+'_facts.json')).write_text(json.dumps(facts))
 def matches(names,instant=None):return [f for f in facts if f['name'] in names and (instant is None or f['context'].get('instant')==instant)]
 d=meta['date'];datefacts=[f for f in facts if f['context'].get('instant')==d]
 btc=matches(['mstr:NumberOfBitcoinHeld','us-gaap:CryptoAssetNumberOfUnits'],d)
 shares=matches(['us-gaap:CommonStockSharesOutstanding'],d)
 covers=matches(['dei:EntityCommonStockSharesOutstanding'])
 cash=matches(['us-gaap:CashAndCashEquivalentsAtCarryingValue'],d)
 debt=matches(['us-gaap:LongTermDebt'],d)
 row={**meta,'btc_candidates':btc,'share_candidates':shares,'cover_candidates':covers,'cash_candidates':cash,'debt_candidates':debt}
 allrows.append(row)
 print(d,'BTC',[(f['value'],f['context']['dims']) for f in btc],'shares',[(f['value'],f['context']['dims']) for f in shares], 'debt',[f['value'] for f in debt])
(D/'account_candidates.json').write_text(json.dumps(allrows,indent=2))
