import unittest
from evaluate_settings import target_rules, r1_rule, evaluate, HIT, MISS, UNKNOWN

class SettingsRules(unittest.TestCase):
    def test_r1_boundaries(self):
        self.assertEqual(r1_rule([20,30],2,2),MISS)
        self.assertEqual(r1_rule([20,30.01],2,2),HIT)
    def test_r1_partial_proof(self):
        self.assertEqual(r1_rule([20,35],3,2),HIT)
        self.assertEqual(r1_rule([20,25],3,2),UNKNOWN)
        self.assertEqual(r1_rule([20],1,1),MISS)
    def test_single_campaign_without_performance(self):
        self.assertEqual(r1_rule([],1,0),MISS)
        self.assertEqual(r1_rule([],0,0),UNKNOWN)
    def test_target_boundaries(self):
        self.assertEqual(target_rules(35,100,20,2)[1],MISS)
        self.assertEqual(target_rules(35.01,100,20,2)[1],HIT)
        self.assertEqual(target_rules(45,100,20,2)[2],MISS)
        self.assertEqual(target_rules(45.01,100,20,2)[2],HIT)
    def test_growth_vs_stability(self):
        self.assertEqual(target_rules(30,100,20,1)[1],HIT)
        self.assertEqual(target_rules(30,100,20,2)[1],MISS)
        self.assertEqual(target_rules(30,100,20,3)[1],HIT)
    def test_missing_zero_and_fault(self):
        self.assertEqual(target_rules(10,0,20,1)[1:],(UNKNOWN,UNKNOWN))
        self.assertEqual(target_rules(None,100,20,1)[1:],(UNKNOWN,UNKNOWN))
        self.assertEqual(target_rules(30,100,20,1,False)[1:],(UNKNOWN,UNKNOWN))
        self.assertEqual(target_rules(30,100,None,1)[1:],(UNKNOWN,UNKNOWN))
    def test_supported_goal(self):
        self.assertEqual(target_rules(60,100,20,9)[1:],(UNKNOWN,HIT))
    def test_below_target(self):
        self.assertEqual(target_rules(10,100,40,2)[1:],(MISS,HIT))
    def test_missing_members_does_not_gate_target(self):
        self.assertEqual(target_rules(30,100,20,1)[1:],(HIT,MISS))
    def test_paused_and_no_records_excluded_only_from_r1(self):
        members=[dict(aiGroupId=1,amazonCampaignId=str(i),campaignState=s)
                 for i,s in [(1,'enabled'),(2,'enabled'),(3,'paused'),(4,'enabled')]]
        daily=[dict(campaignId=i,date=str(d),Spend=s,Sales=100,Conversions=1)
               for i,s in [(1,20),(2,25),(3,60)] for d in range(14)]
        source=dict(scope={},groups=[dict(aiGroupId=1,numCampaign=4,rank=1,
            targetType=1,targetAcos=20,rollupAccepted=True)],members=members,
            daily=daily,rollups=[dict(aiGroupId=1,Spend=1470,Sales=4200,Conversions=42)])
        g=evaluate(source)['groups'][0]
        self.assertEqual(g['r1'],MISS)
        self.assertEqual(g['r1_eligible'],2)
        self.assertEqual(g['r1_excluded_paused'],1)
        self.assertEqual(g['r1_excluded_no_records'],1)
        self.assertEqual(g['range'],5)
        self.assertEqual(g['acos'],35)
        self.assertEqual(g['r2'],HIT)
    def test_partial_days_accepted_zero_sales_activity_excluded(self):
        source=dict(scope={},groups=[dict(aiGroupId=1,numCampaign=3,rank=1,targetType=1,targetAcos=10,rollupAccepted=True)],
            members=[dict(aiGroupId=1,amazonCampaignId=str(i),campaignState='enabled') for i in (1,2,3)],
            daily=[dict(campaignId=i,date='20261001',Spend=s,Sales=v,Conversions=1 if v else 0) for i,s,v in [(1,20,100),(2,25,100),(3,10,0)]],
            rollups=[dict(aiGroupId=1,Spend=55,Sales=200,Conversions=2)])
        g=evaluate(source)['groups'][0]
        self.assertEqual(g['r1'],MISS)
        self.assertEqual(g['r1_eligible'],2)
        self.assertEqual(g['acos'],27.5)
    def test_pre_exclusion(self):
        source=dict(scope={},groups=[dict(aiGroupId=1,numCampaign=1,rank=1,targetType=1,targetAcos=10,rollupAccepted=True)],
            members=[dict(aiGroupId=1,amazonCampaignId='1',campaignState='paused')],daily=[],rollups=[])
        g=evaluate(source)['groups'][0]
        self.assertTrue(g['excluded'])
        self.assertEqual(g['r1'],'不执行判定')
        source['members'][0]['campaignState']='enabled'
        source['rollups']=[dict(aiGroupId=1,Spend=0,Sales=0,Conversions=0)]
        self.assertTrue(evaluate(source)['groups'][0]['excluded'])
        source['rollups']=[]
        self.assertFalse(evaluate(source)['groups'][0]['excluded'])

if __name__ == "__main__":
    unittest.main()

