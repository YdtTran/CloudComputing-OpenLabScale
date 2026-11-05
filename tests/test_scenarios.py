import unittest
from simulation.scenarios import TEMPLATES
from simulation.contract import WORKLOADS


class ScenarioTests(unittest.TestCase):
    def test_coverage_and_bounds(self):
        self.assertEqual(len(TEMPLATES),10)
        self.assertEqual({t['family'] for t in TEMPLATES},WORKLOADS)
        self.assertTrue({'editing-only','reconnect','signal-loss','cpu-background','pure-idle'}<={t['id'] for t in TEMPLATES})
        for t in TEMPLATES:
            self.assertEqual(t['duration_ms'],300000)
            last=max([x[0]+30000 for x in t['events']]+[p['end_ms'] for p in t['phases']])
            self.assertGreaterEqual(300000-last,90000)
            for p in t['phases']:
                self.assertTrue(p['job'])
                self.assertTrue(0<=p['parameters']['cpu_duty']<=1)
                self.assertLessEqual(p['parameters']['memory_bytes'],256*2**20)
                self.assertLessEqual(p['parameters']['burst_width_ms'],p['parameters']['burst_period_ms'])

    def test_stable_expansion_and_links(self):
        from simulation.generator import expand
        _,a=expand(42,10); _,b=expand(42,13)
        for name in ('sessions','events','phases'):
            ids={s['session_id'] for s in a['sessions']}
            self.assertEqual(a[name],[r for r in b[name] if r['session_id'] in ids])
        self.assertEqual(expand(),expand())
        for p in a['phases']:
            if p['job_id']:
                self.assertTrue(any(e['action']=='EXECUTE' and e['job_id']==p['job_id'] for e in a['events']))
        self.assertTrue(all('cpu' not in s['session_id'] for s in a['sessions']))
        _,offset=expand(43,2,1234)
        self.assertEqual(offset['sessions'][1]['start_ms'],1234)

    def test_independent_truth(self):
        from simulation.generator import expand,build_truth
        import json
        _,rows=expand()
        def truth(name,t):
            s=next(s for s in rows['sessions'] if s['scenario_id']==name)
            ev=[e for e in rows['events'] if e['session_id']==s['session_id']]
            pp=[p for p in rows['phases'] if p['session_id']==s['session_id']]
            return next(r for r in build_truth(s,ev,pp) if r['start_ms']<=t<r['end_ms'])
        self.assertEqual(truth('editing-only',180000)['eligibility'],'RETAIN')
        self.assertEqual(truth('editing-only',210000)['eligibility'],'IDLE_ELIGIBLE')
        self.assertEqual(truth('cpu-background',60000)['connection'],'DISCONNECTED')
        self.assertEqual(truth('cpu-background',60000)['workload'],'ACTIVE')
        self.assertEqual(truth('network-wait',120000)['eligibility'],'RETAIN')
        self.assertEqual(truth('pure-idle',30000)['eligibility'],'IDLE_ELIGIBLE')
        s=rows['sessions'][0]; ev=[e for e in rows['events'] if e['session_id']==s['session_id']]; pp=[p for p in rows['phases'] if p['session_id']==s['session_id']]
        for p in pp:
            if p['job_id']:
                params=json.loads(p['parameters_json']);params['outcome']='UNCONFIRMED';p['parameters_json']=json.dumps(params)
        self.assertTrue(any(r['eligibility']=='UNKNOWN' for r in build_truth(s,ev,pp)))
