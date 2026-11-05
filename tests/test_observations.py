import copy
import json
from pathlib import Path
import tempfile
import unittest
from simulation.generator import expand,stream,generate,build_truth
from simulation.observations import observe
from simulation.scenarios import TEMPLATES
from simulation.contract import digest,read_table


class ObservationTests(unittest.TestCase):
    def inputs(self,index=9):
        _,r=expand();s=r['sessions'][index]
        return s,[e for e in r['events'] if e['session_id']==s['session_id']],[p for p in r['phases'] if p['session_id']==s['session_id']]

    def test_projection_partial_and_delay(self):
        s,e,p=self.inputs();s['end_ms']=299001
        faults=[dict(kind='delay',start_ms=295000,end_ms=300000,delay_ms=7000)]
        obs=observe(s,e,p,faults,stream(42,9,'noise'))
        last=[o for o in obs if o['kind']=='resource'][-1]
        self.assertEqual((last['window_start_ms'],last['window_end_ms'],last['available_at_ms']),(295000,299001,306001))
        text=json.dumps(obs)
        for forbidden in ('scenario_id','job_id','parameters_json','eligibility','outcome','cpu_duty'):
            self.assertNotIn(forbidden,text)

    def test_faults_do_not_change_truth(self):
        s,e,p=self.inputs();before=build_truth(s,e,p)
        obs=observe(s,e,p,TEMPLATES[9]['faults'],stream(42,9,'noise'))
        self.assertEqual(before,build_truth(s,e,p))
        resource={o['window_start_ms']:o for o in obs if o['kind']=='resource'}
        self.assertNotIn(150000,resource)
        self.assertIsNone(json.loads(resource[110000]['payload_json'])['cpu_pct'])
        self.assertIsNone(json.loads(resource[120000]['payload_json'])['socket_events'])
        self.assertFalse(json.loads(resource[130000]['payload_json'])['mapping_valid'])
        self.assertEqual(json.loads(resource[180000]['payload_json'])['loss_count'],3)
        self.assertEqual(resource[190000]['available_at_ms'],210000)
        health=[o for o in obs if o['kind']=='interaction_health' and o['at_ms']==50000][0]
        self.assertFalse(json.loads(health['payload_json'])['healthy'])
        # Inject an edit into an outage; it disappears from observations, not truth.
        e.append(dict(run_id=s['run_id'],session_id=s['session_id'],at_ms=70000,action='EDIT',job_id=''))
        obs=observe(s,e,p,TEMPLATES[9]['faults'],stream(42,9,'noise'))
        self.assertFalse(any(o['kind']=='interaction' and o['at_ms']==70000 for o in obs))

    def test_default_generation_and_reproducibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=generate(Path(tmp)/'a');b=generate(Path(tmp)/'b')
            self.assertEqual({p.name:digest(p) for p in a.iterdir()},{p.name:digest(p) for p in b.iterdir()})
            with self.assertRaisesRegex(ValueError,'overwrite'):generate(a)
            generate(a,overwrite=True)
            for seed in (43,44):generate(Path(tmp)/str(seed),seed=seed)
            self.assertTrue(all(o['source'].startswith('synthetic_') for o in read_table(a,'observations')))
