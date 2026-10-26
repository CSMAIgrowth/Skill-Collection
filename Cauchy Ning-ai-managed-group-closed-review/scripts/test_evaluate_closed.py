import copy,unittest
from evaluate_closed import evaluate,evaluate_group

def sample():return dict(groupId='synthetic-1',qualityConfirmed=True,windowAndStatusConfirmed=True,membersConfirmed=True,ai=dict(orders='10',spend='30',sales='100'),off=dict(orders='15',spend='20',sales='100'),targetAcosPct='25')
class ReviewTests(unittest.TestCase):
 def test_ai_is_tested_side(self):
  self.assertEqual(evaluate_group(sample())['result'],'不合格')
 def test_reverse_direction_passes(self):
  g=sample();g['ai'],g['off']=g['off'],g['ai'];self.assertEqual(evaluate_group(g)['result'],'合格')
 def test_equal_orders_pass(self):
  g=sample();g['ai']['orders']='15';self.assertEqual(evaluate_group(g)['result'],'合格')
 def test_equal_acos_pass(self):
  g=sample();g['off']['spend']='30';self.assertEqual(evaluate_group(g)['result'],'合格')
 def test_equal_target_pass(self):
  g=sample();g['targetAcosPct']='30';self.assertEqual(evaluate_group(g)['result'],'合格')
 def test_zero_sales_incomplete(self):
  for side in ['ai','off']:
   g=sample();g[side]['sales']='0';self.assertEqual(evaluate_group(g)['result'],'未完成')
 def test_missing_invalid_not_zero(self):
  for v in [None,'NaN','Infinity','-1',True]:
   g=sample();g['ai']['spend']=v;self.assertEqual(evaluate_group(g)['result'],'未完成')
 def test_each_proof_required(self):
  for field in ['qualityConfirmed','windowAndStatusConfirmed','membersConfirmed']:
   g=sample();g[field]=False;self.assertEqual(evaluate_group(g)['result'],'未完成')
 def test_no_data_rate_null(self):
  self.assertIsNone(evaluate({'groups':[]})['counts']['failureRate'])
 def test_counts_and_denominator(self):
  a=sample();b=copy.deepcopy(a);b['groupId']='synthetic-2';b['membersConfirmed']=False
  c=evaluate({'groups':[a,b]})['counts'];self.assertEqual((c['scanned'],c['completed'],c['incomplete'],c['failed'],c['failureRate']),(2,1,1,1,'1'))
 def test_duplicate_group_rejected(self):
  with self.assertRaises(ValueError):evaluate({'groups':[sample(),sample()]})
 def test_fractional_orders_incomplete(self):
  g=sample();g['ai']['orders']='1.5';self.assertEqual(evaluate_group(g)['result'],'未完成')
if __name__=='__main__':unittest.main()
