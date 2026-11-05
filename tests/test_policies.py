import csv
import json
from pathlib import Path
import tempfile
import unittest
from simulation.policies import Policy,causal_projection,predict,SESSION_FIELDS
from simulation.generator import generate
from simulation.contract import read_table


def window(a,b,cpu=0,**extra):
    p=dict(cpu_pct=cpu,loss_count=0,mapping_valid=True,disk_read_bytes=0,disk_write_bytes=0,network_rx_bytes=0,network_tx_bytes=0,process_events=0,io_events=0,socket_events=0);p.update(extra)
    return dict(kind='resource',at_ms=b,available_at_ms=b,window_start_ms=a,window_end_ms=b,status='OK',payload=p)


def visible(t,cpu=0,interaction_at=0,healthy=True,extra=None):
    return [dict(kind='connection',at_ms=interaction_at,payload={'action':'CONNECT'}),dict(kind='interaction_health',at_ms=t,status='OK' if healthy else 'UNHEALTHY',payload={'healthy':healthy})]+[window(a,a+5000,cpu,**(extra or {})) for a in range(0,t,5000)]


class PolicyTests(unittest.TestCase):
    def test_causal_projection(self):
        s=dict(session_id='s',container_instance_id='c')
        r=dict(run_id='r',session_id='s',container_instance_id='c',kind='interaction',at_ms='5',available_at_ms='10',window_start_ms='',window_end_ms='',source='x',status='OK',payload_json='{"action":"EDIT","duration":999}',scenario_id='secret')
        self.assertEqual(causal_projection([r],s,5),[])
        projected=causal_projection([r],s,10)[0]
        self.assertNotIn('scenario_id',projected);self.assertEqual(projected['payload'],{'action':'EDIT'})

    def test_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=generate(Path(tmp)/'bundle',count=1)
            a=Path(tmp)/'a';b=Path(tmp)/'b';predict(root,a)
            # No truth or schedules need exist during prediction.
            for name in ('truth','events','phases'):(root/(name+'.csv')).unlink()
            sessions=read_table(root,'sessions');sessions[0]['scenario_id']='changed'
            from simulation.contract import write_table
            write_table(root/'sessions.csv','sessions',sessions)
            predict(root,b)
            self.assertEqual((a/'predictions.csv').read_bytes(),(b/'predictions.csv').read_bytes())
            self.assertEqual((a/'prediction-metadata.json').read_bytes(),(b/'prediction-metadata.json').read_bytes())

    def test_boundaries(self):
        for name in ('cpu-only','resource-multi','interaction-aware'):
            p=Policy(name)
            for t in range(5000,45000,5000):
                d,reason=p.decide({},t,visible(t))
                self.assertEqual(d,'IDLE_CANDIDATE' if t==40000 else 'RETAIN')
                if t==30000:self.assertEqual(reason,'quiet_pending')
        p=Policy('interaction-timeout')
        self.assertEqual(p.decide({},35000,visible(35000))[0],'RETAIN')
        self.assertEqual(p.decide({},40000,visible(40000))[0],'IDLE_CANDIDATE')

    def test_expected_policy_differences(self):
        # Editing protects interaction-aware while resource-only sees quiet.
        for name,expected in [('no-reclaim','RETAIN'),('interaction-timeout','RETAIN'),('cpu-only','IDLE_CANDIDATE'),('resource-multi','IDLE_CANDIDATE'),('interaction-aware','RETAIN')]:
            p=Policy(name)
            for t in range(5000,65000,5000):d,_=p.decide({},t,visible(t,interaction_at=(t//10000)*10000))
            self.assertEqual(d,expected)
        # Low CPU background process counters protect multi-signal only.
        for name,expected in [('cpu-only','IDLE_CANDIDATE'),('resource-multi','RETAIN')]:
            p=Policy(name)
            for t in range(5000,65000,5000):d,_=p.decide({},t,visible(t,extra={'process_events':1}))
            self.assertEqual(d,expected)
        # Recurrent bursts reset quiet evidence; connected abandonment can qualify.
        p=Policy('resource-multi')
        obs=[]
        for t in range(5000,100000,5000):
            obs.append(window(t-5000,t,cpu=10 if t%20000==0 else 0));d,_=p.decide({},t,obs)
            self.assertEqual(d,'RETAIN')

    def test_unknown_recovery_and_disconnect(self):
        p=Policy('interaction-aware')
        for t in range(5000,45000,5000):p.decide({},t,visible(t))
        self.assertEqual(p.decide({},45000,visible(45000,healthy=False))[0],'UNKNOWN')
        for t in range(50000,90000,5000):
            d,_=p.decide({},t,visible(t))
            self.assertEqual(d,'IDLE_CANDIDATE' if t==85000 else 'RETAIN')
        obs=visible(90000)+[dict(kind='connection',at_ms=89000,payload={'action':'DISCONNECT'})]
        self.assertEqual(p.decide({},90000,obs)[0],'IDLE_CANDIDATE')
        self.assertEqual(p.decide({},95000,visible(95000,extra={'mapping_valid':False}))[0],'UNKNOWN')

    def test_stale_missing_loss_and_delay(self):
        for extra in ({'cpu_pct':None},{'loss_count':1},{'mapping_valid':False},{'io_events':None}):
            p=Policy('resource-multi');self.assertEqual(p.decide({},40000,visible(40000,extra=extra))[0],'UNKNOWN')
        p=Policy('cpu-only');obs=[window(0,5000)]
        self.assertEqual(p.decide({},15000,obs)[0],'RETAIN')
        self.assertEqual(p.decide({},15001,obs)[0],'UNKNOWN')
        # A delayed old window cannot displace a newer one or bridge a missing gap.
        p=Policy('cpu-only');obs=[window(a,a+5000) for a in (0,5000,10000,20000,25000,30000,35000)]
        self.assertEqual(p.decide({},40000,obs)[0],'RETAIN')
