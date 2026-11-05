import csv
import json
from pathlib import Path
import tempfile
import unittest
from simulation.contract import TABLES, digest, write_json, write_table
from simulation.validation import validate
from tests.fixtures import write_minimal


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.m,self.rows=write_minimal(self.root)

    def save(self):
        for name in TABLES:
            write_table(self.root/(name+'.csv'),name,self.rows[name])
            self.m['files'][name+'.csv']=digest(self.root/(name+'.csv'))
        write_json(self.root/'manifest.json',self.m)

    def test_minimal(self):
        validate(self.root)

    def test_checksums_and_versions(self):
        (self.root/'events.csv').write_text('bad')
        with self.assertRaisesRegex(ValueError,'events.csv.*checksum'): validate(self.root)
        self.m['schema_version']='99'; self.save()
        with self.assertRaisesRegex(ValueError,'unsupported schema'): validate(self.root)

    def test_references_times_truth_provenance(self):
        mutations=[('events',0,'session_id','missing','row 2.*unknown session'),('events',0,'at_ms','00:00.0','row 2.*legacy'),('truth',1,'start_ms',30001,'gap'),('truth',0,'label_source','execution_ack','row 2.*provenance')]
        for table,index,key,value,error in mutations:
            with self.subTest(key=key):
                self.m,self.rows=write_minimal(self.root); self.rows[table][index][key]=value; self.save()
                with self.assertRaisesRegex(ValueError,error): validate(self.root)

    def test_duplicate_and_lifecycle(self):
        self.rows['events'].append(dict(self.rows['events'][0])); self.save()
        with self.assertRaisesRegex(ValueError,'duplicate'): validate(self.root)
        self.rows['events'][1].update(event_id='e2',action='JOB_COMPLETE',job_id='j'); self.save()
        with self.assertRaisesRegex(ValueError,'without request'): validate(self.root)

    def test_partial_delayed_missing_window(self):
        from simulation.contract import RESOURCE
        p={k:0 for k in RESOURCE}; p.update(cpu_pct=None,memory_bytes=None,mapping_valid=True,cgroup_source='synthetic_cgroup_v2',event_source='synthetic_ebpf')
        self.rows['observations']=[dict(run_id='r',session_id='s',container_instance_id='c',kind='resource',at_ms=45000,available_at_ms=51000,window_start_ms=43000,window_end_ms=45000,source='synthetic_model',status='DEGRADED',payload_json=json.dumps(p))]
        self.save(); validate(self.root)
        self.rows['observations'][0]['available_at_ms']=44000; self.save()
        with self.assertRaisesRegex(ValueError,'row 2.*available before'): validate(self.root)

    def test_legacy(self):
        with self.assertRaisesRegex(ValueError,'legacy abbreviated timestamps'):
            validate(Path(__file__).resolve().parents[1]/'data')

    def test_measured_actual_acknowledgements(self):
        from tests.fixtures import write_measured
        self.m,self.rows=write_measured(self.root);validate(self.root)
        self.rows['truth'][-1].update(workload='ACTIVE',eligibility='RETAIN');self.save()
        with self.assertRaisesRegex(ValueError,'actual acknowledgements'):validate(self.root)
        self.m,self.rows=write_measured(self.root)
        self.rows['truth'][2].update(workload='ACTIVE');self.save()
        with self.assertRaisesRegex(ValueError,'actual acknowledgements'):validate(self.root)
        self.m,self.rows=write_measured(self.root)
        self.rows['events'][3]['action']='JOB_ERROR'
        self.save()
        with self.assertRaisesRegex(ValueError,'actual acknowledgements'):validate(self.root)

    def test_negative_counters_bounds_and_mapping(self):
        import copy
        from simulation.contract import RESOURCE
        p={k:0 for k in RESOURCE};p.update(mapping_valid=True,cgroup_source='synthetic_cgroup_v2',event_source='synthetic_ebpf')
        r=dict(run_id='r',session_id='s',container_instance_id='c',kind='resource',at_ms=5000,available_at_ms=5000,window_start_ms=0,window_end_ms=5000,source='synthetic_model',status='OK',payload_json=json.dumps(p))
        for key,value in [('cpu_pct',101),('memory_bytes',257*2**20),('disk_read_bytes',-1),('process_events',-1),('event_source','ebpf')]:
            pp=dict(p);pp[key]=value;r['payload_json']=json.dumps(pp);self.rows['observations']=[dict(r)];self.save()
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'observations.csv:row 2'):validate(self.root)
