"""Causal policy inputs. This module never opens plans, phases or truth."""
import csv
import hashlib
import json
import math
from pathlib import Path
from .contract import dumps, write_json, read_manifest, read_table, digest

POLICIES=('no-reclaim','interaction-timeout','cpu-only','resource-multi','interaction-aware')
DEFAULTS=dict(cpu_threshold_pct=1.0,quiet_ms=30000,hysteresis_ms=10000,interaction_grace_ms=30000,interaction_timeout_ms=40000,freshness_ms=10000,socket_grace_ms=160000)
SESSION_FIELDS=('run_id','session_id','container_instance_id','start_ms','end_ms','cpu_limit_cores','memory_limit_mb')
OBS_FIELDS=('run_id','session_id','container_instance_id','kind','at_ms','available_at_ms','window_start_ms','window_end_ms','source','status','payload_json')
PRED_FIELDS='policy policy_version config_hash run_id session_id container_instance_id decision_ms decision reason'.split()


def config_values(overrides=None):
    cfg=dict(DEFAULTS)
    if overrides:
        if set(overrides)-set(cfg):raise ValueError('unknown policy configuration fields')
        cfg.update(overrides)
    for key,v in cfg.items():
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:
            raise ValueError(f'policy configuration {key} must be finite nonnegative number')
        if key.endswith('_ms') and (not isinstance(v,int) or v==0):raise ValueError(f'{key} must be positive integer ms')
    if cfg['cpu_threshold_pct']>100:raise ValueError('CPU threshold exceeds 100%')
    return cfg


def causal_projection(observations, session, decision_ms):
    """Explicit allowlist and two-clock gate, including payload allowlists."""
    result=[]
    for r in observations:
        if r['session_id']!=session['session_id'] or r['container_instance_id']!=session['container_instance_id']:continue
        if int(r['at_ms'])>decision_ms or int(r['available_at_ms'])>decision_ms:continue
        o={key:r[key] for key in OBS_FIELDS}
        p=json.loads(o.pop('payload_json'))
        if r['kind']=='resource':
            if int(r['window_end_ms'])>decision_ms:continue
            allowed={'cpu_pct','memory_bytes','disk_read_bytes','disk_write_bytes','network_rx_bytes','network_tx_bytes','process_events','io_events','socket_events','loss_count','mapping_valid','cgroup_source','event_source'}
        elif r['kind']=='interaction_health':allowed={'healthy'}
        else:allowed={'action'}
        o['payload']={k:v for k,v in p.items() if k in allowed}
        result.append(o)
    return sorted(result,key=lambda r:(int(r['at_ms']),int(r['available_at_ms']),r['kind']))


class Policy:
    def __init__(self,name,config=None):
        if name not in POLICIES:raise ValueError('unknown policy')
        self.name=name;self.cfg=config_values(config)
        self.quiet_start=None;self.quiet_end=None;self.seen_end=None;self.recovery_after=-1
        self.socket_wait_start=None

    def reset(self,t):
        self.quiet_start=None;self.quiet_end=None;self.recovery_after=t
        self.socket_wait_start=None

    def decide(self,session,t,observations):
        c=self.cfg
        if self.name=='no-reclaim':return 'RETAIN','reference'
        needs_interaction=self.name in ('interaction-timeout','interaction-aware')
        interactions=[r for r in observations if r['kind'] in ('interaction','connection')]
        recent=max((int(r['at_ms']) for r in interactions if r['payload'].get('action') in ('EDIT','EXECUTE_REQUEST','CONNECT','RECONNECT')),default=None)
        if needs_interaction:
            health=[r for r in observations if r['kind']=='interaction_health']
            h=health[-1] if health else None
            if not h or t-int(h['at_ms'])>c['freshness_ms'] or h['payload'].get('healthy') is not True or h['status']!='OK':
                self.reset(t);return 'UNKNOWN','interaction_health'
            if recent is None:
                self.reset(t);return 'UNKNOWN','missing_interaction_origin'
        if self.name=='interaction-timeout':
            return ('IDLE_CANDIDATE','interaction_timeout') if t-recent>=c['interaction_timeout_ms'] else ('RETAIN','recent_interaction')
        resources=sorted((r for r in observations if r['kind']=='resource'),key=lambda r:int(r['window_end_ms']))
        if not resources or t-int(resources[-1]['window_end_ms'])>c['freshness_ms']:
            self.reset(t);return 'UNKNOWN','resource_stale_or_missing'
        required=['cpu_pct','loss_count','mapping_valid']
        if self.name!='cpu-only':required+=['disk_read_bytes','disk_write_bytes','network_rx_bytes','network_tx_bytes','process_events','io_events','socket_events']
        latest=resources[-1]
        def valid(r):
            p=r['payload']
            return all(p.get(k) is not None for k in required) and p['mapping_valid'] is True and p['loss_count']==0 and r['status']!='UNHEALTHY'
        if not valid(latest):
            self.seen_end=int(latest['window_end_ms']);self.reset(t)
            return 'UNKNOWN','resource_missing_loss_or_mapping'
        # A recovered window must include no time for which evidence was unknown.
        for r in resources:
            a=int(r['window_start_ms']);b=int(r['window_end_ms'])
            if self.seen_end is not None and b<=self.seen_end:continue
            self.seen_end=b
            if not valid(r) or a<self.recovery_after:
                self.quiet_start=None;self.quiet_end=None;self.socket_wait_start=None;continue
            p=r['payload'];quiet=p['cpu_pct']<c['cpu_threshold_pct']
            sock=p.get('socket_events') or 0
            if sock>0:
                self.socket_wait_start=b if self.socket_wait_start is None else None
            elif self.socket_wait_start is not None and b-self.socket_wait_start>=c['socket_grace_ms']:
                self.socket_wait_start=None
            if self.name!='cpu-only':
                quiet=quiet and all(p[k]==0 for k in required if k not in ('cpu_pct','loss_count','mapping_valid'))
                if self.socket_wait_start is not None:quiet=False
            if not quiet:
                self.quiet_start=None;self.quiet_end=None;continue
            if self.quiet_end!=a:self.quiet_start=a
            if self.name=='interaction-aware':self.quiet_start=max(self.quiet_start,recent)
            self.quiet_end=b
        if self.name=='interaction-aware' and t-recent<c['interaction_grace_ms']:
            return 'RETAIN','recent_interaction'
        if self.name in ('resource-multi','interaction-aware') and self.socket_wait_start is not None:
            return 'RETAIN','awaiting_socket_response'
        if self.quiet_start is None or self.quiet_end is None:return 'RETAIN','activity_or_recovery'
        elapsed=self.quiet_end-self.quiet_start
        if elapsed>=c['quiet_ms']+c['hysteresis_ms']:return 'IDLE_CANDIDATE','quiet_hysteresis_complete'
        return 'RETAIN','quiet_pending' if elapsed>=c['quiet_ms'] else 'quiet_observing'


def predict(bundle, output, overrides=None):
    root=Path(bundle);out=Path(output);out.mkdir(parents=True,exist_ok=True)
    cfg=config_values(overrides);m=read_manifest(root)
    if m.get('schema_version')!='1.0' or m.get('sample_ms')!=5000:raise ValueError('unsupported policy input schema/timing')
    sessions=[{k:s[k] for k in SESSION_FIELDS} for s in read_table(root,'sessions')]
    observations=read_table(root,'observations')
    # Hash only detector inputs: truth/scenario changes cannot affect predictions.
    input_hash=hashlib.sha256(dumps(dict(sessions=sessions,observations=observations,sample_ms=m['sample_ms'],source_mode=m['source_mode'])).encode()).hexdigest()
    config_hash=hashlib.sha256(dumps(cfg).encode()).hexdigest()
    path=out/'predictions.csv'
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,PRED_FIELDS,lineterminator='\n');w.writeheader()
        for name in POLICIES:
            for s in sessions:
                policy=Policy(name,cfg)
                lo=int(s['start_ms']);hi=int(s['end_ms'])
                obs=[r for r in observations if r['session_id']==s['session_id']]
                for t in range((lo//5000+1)*5000,hi,5000):
                    visible=causal_projection(obs,s,t)
                    decision,reason=policy.decide(s,t,visible)
                    w.writerow(dict(policy=name,policy_version='1.0',config_hash=config_hash,run_id=s['run_id'],session_id=s['session_id'],container_instance_id=s['container_instance_id'],decision_ms=t,decision=decision,reason=reason))
    write_json(out/'prediction-metadata.json',dict(policy_versions={p:'1.0' for p in POLICIES},config=cfg,config_hash=config_hash,input_hash=input_hash,source_mode=m['source_mode'],predictions_sha256=digest(path)))
    return path
