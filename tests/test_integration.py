import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from simulation.generator import generate
from simulation.policies import predict,POLICIES
from simulation.scoring import score,FORMULAS
from simulation.contract import digest,read_table

ROOT=Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def test_full_flow_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshots=[]
            for repeat in ('a','b'):
                bundle=Path(tmp)/repeat/'bundle';out=Path(tmp)/repeat/'report'
                # Run public commands in a clean process with only Python 3.
                for command in [('generate',str(bundle)),('validate',str(bundle)),('predict',str(bundle),str(out)),('score',str(bundle),str(out))]:
                    subprocess.run([sys.executable,'-m','simulation',*command],cwd=ROOT,check=True,capture_output=True)
                snapshots.append({str(p.relative_to(bundle.parent)):digest(p) for p in bundle.parent.rglob('*') if p.is_file()})
                with (out/'predictions.csv').open() as f:predictions=list(csv.DictReader(f))
                self.assertEqual({p['policy'] for p in predictions},set(POLICIES))
                self.assertEqual(len(read_table(bundle,'sessions')),10)
                result=json.loads((out/'metrics.json').read_text())
                self.assertEqual(result['source_mode'],'synthetic')
                self.assertIn('not real monitoring accuracy',result['limitations'])
                for name,g in result['policies'].items():
                    self.assertEqual(len(g['by_scenario']),10)
                    self.assertEqual(set(g['overall_micro']['denominators']),set(FORMULAS))
                    self.assertEqual(len(g['macro_by_scenario']),7)
                    self.assertIn('42',g['by_seed'])
                    self.assertEqual(len(result['prediction_metadata']['config_hash']),64)
                self.assertEqual(result['policies']['no-reclaim']['overall_micro']['counts']['tp'],0)
                self.assertIsNone(result['policies']['no-reclaim']['overall_micro']['values']['precision'])
            self.assertEqual(snapshots[0],snapshots[1])

    def test_observation_identity_and_config_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=generate(Path(tmp)/'b',count=1);out=Path(tmp)/'out'
            predict(b,out,{'cpu_threshold_pct':2.0});r=score(b,out)
            self.assertEqual(r['prediction_metadata']['config']['cpu_threshold_pct'],2.0)
            metadata=json.loads((out/'prediction-metadata.json').read_text());metadata['source_mode']='measured'
            (out/'prediction-metadata.json').write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError,'cannot be pooled'):score(b,out)
