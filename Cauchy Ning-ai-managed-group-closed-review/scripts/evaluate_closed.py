"""Pure closed-group three-check evaluator, standard library only.
Usage: python scripts/evaluate_closed.py input.json
JSON: {"groups":[{"groupId":"synthetic-1", "qualityConfirmed":true,
"windowAndStatusConfirmed":true,"membersConfirmed":true,
"ai":{"orders":"10","spend":"30","sales":"100"},
"off":{"orders":"15","spend":"20","sales":"100"},"targetAcosPct":"25"}]}.
Flags must be established by caller with real evidence. This module does not verify
authorization, events, windows, source completeness or settings. Percent is 0..100+
in percentage units (25 means 25 percent), not a ratio of .25.
Missing flags/data return incomplete; malformed/negative/nonfinite metrics are not zeros.
"""
import json,sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

def number(x):
 if x is None or isinstance(x,bool):return None
 try:
  v=Decimal(str(x))
  return v if v.is_finite() and v>=0 else None
 except (InvalidOperation,ValueError,TypeError):return None

def evaluate_group(g):
 reasons=[]
 for k,label in [('qualityConfirmed','查询质量未确认'),('windowAndStatusConfirmed','窗口或历史AI状态未确认'),('membersConfirmed','历史成员未确认')]:
  if g.get(k) is not True: reasons.append(label)
 values={}
 for side in ['ai','off']:
  raw=g.get(side)
  if not isinstance(raw,dict):raw={}
  values[side]={k:number(raw.get(k)) for k in ['orders','spend','sales']}
  for k,v in values[side].items():
   if v is None:reasons.append(side+'.'+k+'缺失或无效')
  if values[side]['orders'] is not None and values[side]['orders']%1: reasons.append(side+'.orders不是整数')
  if values[side]['sales']==0:reasons.append(side+'归因销售额为0，ACOS不可计算')
 target=number(g.get('targetAcosPct'))
 if target is None or target==0:reasons.append('缺少有效托管期末目标ACOS')
 if not isinstance(g.get('groupId'),str) or not g['groupId']:reasons.append('缺少文本组ID')
 result={'groupId':g.get('groupId'),'result':'未完成','reasons':reasons,'standards':None,'aiAcosPct':None,'offAcosPct':None}
 if reasons:return result
 a,b=values['ai'],values['off']
 bad=[a['orders']<b['orders'],a['spend']*b['sales']>b['spend']*a['sales'],a['spend']*100>target*a['sales']]
 result.update(result='不合格' if all(bad) else '合格',standards=['不合格' if x else '合格' for x in bad],aiAcosPct=str(a['spend']*100/a['sales']),offAcosPct=str(b['spend']*100/b['sales']))
 return result

def evaluate(data):
 gs=data.get('groups')
 if not isinstance(gs,list):raise ValueError('groups must be a list')
 if any(not isinstance(g,dict) for g in gs):raise ValueError('every group must be an object')
 ids=[g.get('groupId') for g in gs]
 if any(not isinstance(i,str) or not i for i in ids):raise ValueError('groupId must be nonempty text')
 if len(set(ids))!=len(ids):raise ValueError('duplicate groupId; normalize profile/event keys before calling')
 rows=[evaluate_group(g) for g in gs];e=sum(g['result']!='未完成' for g in rows);f=sum(g['result']=='不合格' for g in rows)
 return {'groups':rows,'counts':{'scanned':len(rows),'completed':e,'incomplete':len(rows)-e,'failed':f,'qualified':e-f,'failureRate':str(Decimal(f)/Decimal(e)) if e else None},'settingsExecuted':False,'note':'纯汇总计算，不证明数据质量、真实触发或业务验收'}

if __name__=='__main__':
 print(json.dumps(evaluate(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))),ensure_ascii=False,indent=2))
