import unittest
from simulation.scoring import score_rows,join_truth


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.s=[dict(session_id='s',start_ms=0,end_ms=30000)]
        self.truth=[dict(session_id='s',start_ms=0,end_ms=10000,eligibility='RETAIN'),dict(session_id='s',start_ms=10000,end_ms=25000,eligibility='IDLE_ELIGIBLE'),dict(session_id='s',start_ms=25000,end_ms=30000,eligibility='UNKNOWN')]

    def predictions(self,decisions):
        return [dict(session_id='s',decision_ms=(i+1)*5000,decision=d) for i,d in enumerate(decisions)]

    def test_hand_calculated(self):
        p=self.predictions(['IDLE_CANDIDATE','RETAIN','IDLE_CANDIDATE','UNKNOWN','IDLE_CANDIDATE'])
        r=score_rows(p,self.truth,self.s,['synthetic'])
        self.assertEqual(r['counts'],dict(tp=1,fp=1,tn=0,fn=1,abstain_eligible=1,abstain_retain=0,unknown_truth=1))
        self.assertEqual(r['values'],dict(precision=.5,recall=.5,f1=.5,false_idle_rate=1.,false_active_rate=.5,coverage=.75,idle_capture=1/3))
        self.assertEqual(r['latency']['mean_detected_ms'],5000)
        self.assertEqual(r['denominators']['coverage'],4)
        self.assertEqual(r['unsafe_recommendations'],1)
        self.assertEqual(join_truth(self.truth,'s',10000)['eligibility'],'IDLE_ELIGIBLE')
        self.assertEqual(join_truth(self.truth,'s',25000)['eligibility'],'UNKNOWN')

    def test_unknown_and_censoring(self):
        r=score_rows(self.predictions(['UNKNOWN']*5),self.truth,self.s,['synthetic'])
        self.assertEqual(r['values']['coverage'],0)
        self.assertIsNone(r['values']['precision']);self.assertIsNone(r['values']['recall']);self.assertIsNone(r['values']['f1'])
        self.assertEqual(r['values']['idle_capture'],0)
        self.assertEqual(r['latency']['undetected_intervals'],1)
        self.assertIsNone(r['latency']['mean_detected_ms'])
        self.assertIsNone(r['latency']['intervals'][0]['latency_ms'])

    def test_absent_positive_and_no_zero_delay(self):
        truth=[dict(session_id='s',start_ms=0,end_ms=30000,eligibility='RETAIN')]
        r=score_rows(self.predictions(['RETAIN']*5),truth,self.s,['synthetic'])
        self.assertIsNone(r['values']['recall']);self.assertIsNone(r['values']['precision'])
        self.assertIsNone(r['values']['idle_capture']);self.assertEqual(r['values']['coverage'],1)
        self.assertEqual(r['latency']['eligible_intervals'],0)
        r=score_rows(self.predictions(['RETAIN']*5),self.truth,self.s,['synthetic'])
        self.assertEqual(r['latency']['undetected_intervals'],1)
        self.assertIsNone(r['latency']['mean_detected_ms'])

    def test_provenance_pooling(self):
        with self.assertRaisesRegex(ValueError,'cannot be pooled'):
            score_rows([],[],[],['synthetic','measured'])
