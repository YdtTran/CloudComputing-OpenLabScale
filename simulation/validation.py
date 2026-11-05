"""Strict versioned contract checks. Errors name the file and CSV row."""
import json
import math
from pathlib import Path
from .contract import (SCHEMA, TABLES, ACTIONS, WORKLOADS, COUNTERS, CGROUP,
                       RESOURCE, KINDS, digest, read_manifest, read_table)


def validate(root):
    root = Path(root)
    m = read_manifest(root)
    def require(ok, where, message):
        if not ok:
            raise ValueError(f'{where}: {message}')
    def number(value, where, integer=True, minimum=0):
        try:
            result = int(value) if integer else float(value)
            require(not isinstance(value, bool) and math.isfinite(result) and result >= minimum, where, 'number outside allowed bounds')
            if integer:
                require(str(result) == str(value), where, 'expected integer elapsed milliseconds or count')
            return result
        except (ValueError, TypeError, OverflowError) as e:
            raise ValueError(f'{where}: expected {"integer" if integer else "finite number"} >= {minimum}; ambiguous legacy timing is unsupported') from e
    require(m.get('schema_version') == SCHEMA, 'manifest.json', 'unsupported schema_version; expected 1.0')
    for field in ['generator_version','run_id','seed','config','duration_ms','sample_ms','interaction_truth_ms','clock','origin_utc','source_mode','files']:
        require(field in m, 'manifest.json', f'missing {field}')
    require(m['source_mode'] in ('synthetic', 'measured'), 'manifest.json', 'source_mode must be synthetic or measured; pooling prohibited')
    require(m['sample_ms'] == 5000 and m['interaction_truth_ms'] == 30000 and m['clock'] == 'elapsed_ms', 'manifest.json', 'requires 5000ms sampling, 30000ms truth grace and elapsed_ms clock')
    require(isinstance(m['config'], dict) and isinstance(m['run_id'], str) and bool(m['run_id']), 'manifest.json','invalid config/run_id')
    number(m['seed'], 'manifest.json:seed', minimum=-2**63)
    duration = number(m['duration_ms'], 'manifest.json:duration_ms', minimum=1)
    if m['origin_utc'] is not None:
        from datetime import datetime
        try:
            require(m['origin_utc'].endswith('Z'), 'manifest.json', 'origin_utc must be UTC ending Z')
            datetime.fromisoformat(m['origin_utc'].replace('Z','+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError('manifest.json: invalid UTC origin') from e
    require(set(m['files']) == {n+'.csv' for n in TABLES}, 'manifest.json','files must hash exactly five schema tables')
    data = {}
    for name in TABLES:
        file = name+'.csv'
        require((root/file).is_file(),file,'missing table')
        require(digest(root/file) == m['files'][file], file, 'SHA-256 checksum mismatch')
        data[name] = read_table(root,name)
    sessions = {}
    instances = set()
    for index, s in enumerate(data['sessions'],2):
        w=f'sessions.csv:row {index}'
        for field in ('session_id','user_id','container_instance_id','scenario_id'):
            require(bool(s[field]),w,f'empty {field}')
        require(s['session_id'] not in sessions,w,'duplicate session_id')
        require(s['container_instance_id'] not in instances,w,'duplicate container_instance_id; restarts need a new instance')
        instances.add(s['container_instance_id'])
        sessions[s['session_id']] = s
        a=number(s['start_ms'],w); b=number(s['end_ms'],w)
        require(a < b <= duration,w,'invalid session bounds')
        require(number(s['cpu_limit_cores'],w,False) > 0 and number(s['memory_limit_mb'],w,False)>0,w,'resource limits must be positive')
    require(bool(sessions),'sessions.csv','at least one session required')
    ids={'events':set(),'phases':set()}
    grouped={name:{sid:[] for sid in sessions} for name in TABLES if name!='sessions'}
    synthetic=m['source_mode']=='synthetic'
    for name,rows in data.items():
        for index,r in enumerate(rows,2):
            w=f'{name}.csv:row {index}'
            require(r['run_id']==m['run_id'],w,'run_id mismatch')
            require(r['session_id'] in sessions,w,'unknown session_id')
            s=sessions[r['session_id']]; lo=int(s['start_ms']); hi=int(s['end_ms'])
            if name=='sessions':
                continue
            grouped[name][r['session_id']].append(r)
            if name in ids:
                key='event_id' if name=='events' else 'phase_id'
                require(r[key] and r[key] not in ids[name],w,f'duplicate/empty {key}')
                ids[name].add(r[key])
            if name in ('phases','truth'):
                a=number(r['start_ms'],w); b=number(r['end_ms'],w)
                require(lo<=a<b<=hi,w,'invalid half-open interval')
            if name in ('events','observations'):
                t=number(r['at_ms'],w)
                require(lo<=t<=hi,w,'event outside session lifetime')
            if name in ('events','phases','observations'):
                try:
                    p=json.loads(r['payload_json'] if name=='observations' else r['parameters_json'])
                    require(isinstance(p,dict),w,'JSON payload must be object')
                except json.JSONDecodeError as e:
                    raise ValueError(f'{w}: invalid JSON payload') from e
            if name=='events':
                require(r['action'] in ACTIONS,w,'unsupported action')
                if r['action'].startswith('JOB_') or r['action']=='EXECUTE':
                    require(bool(r['job_id']),w,'job action requires job_id')
            if name=='phases':
                require(r['workload'] in WORKLOADS,w,'unsupported workload')
                require(bool(r['job_id']) == (r['workload']!='IDLE'),w,'nonidle phase requires job; idle cannot have job')
                allowed={'cpu_duty','memory_bytes','disk_file_bytes','disk_rate_bytes_s','network_bytes','response_delay_ms','burst_width_ms','burst_period_ms','outcome'}
                require(not set(p)-allowed,w,'unsupported replay parameters')
                for key,value in p.items():
                    if key=='outcome':
                        require(value in ('COMPLETE','ERROR','INTERRUPT','UNCONFIRMED'),w,'invalid outcome')
                    else:
                        n=number(value,w,integer=key!='cpu_duty')
                        bound={'cpu_duty':1,'memory_bytes':float(s['memory_limit_mb'])*2**20,'disk_file_bytes':2**30,'disk_rate_bytes_s':2**28,'network_bytes':2**30,'response_delay_ms':b-a,'burst_width_ms':b-a,'burst_period_ms':b-a}[key]
                        require(n<=bound,w,f'{key} exceeds replay limit')
                if 'burst_width_ms' in p:
                    require(0<p['burst_width_ms']<=p.get('burst_period_ms',0),w,'invalid burst width/period')
            if name=='observations':
                require(r['container_instance_id']==s['container_instance_id'],w,'container mapping mismatch')
                require(r['kind'] in KINDS and r['status'] in ('OK','DEGRADED','UNHEALTHY'),w,'invalid observation kind/status')
                available=number(r['available_at_ms'],w)
                require(available>=t,w,'observation available before occurrence')
                expected=('synthetic_model' if synthetic else 'measured_collector') if r['kind']=='resource' else ('synthetic_session_service' if synthetic else 'session_service')
                require(r['source']==expected,w,'source provenance mismatch')
                if r['kind']=='resource':
                    a=number(r['window_start_ms'],w); b=number(r['window_end_ms'],w)
                    require(lo<=a<b<=hi and b==t and b-a<=5000,w,'invalid resource window bounds/end/availability')
                    require(set(p)==set(RESOURCE),w,'resource payload fields must match dictionary')
                    require(p['cgroup_source']==('synthetic_cgroup_v2' if synthetic else 'cgroup_v2') and p['event_source']==('synthetic_ebpf' if synthetic else 'ebpf'),w,'resource group provenance mismatch')
                    require(p['mapping_valid'] is None or isinstance(p['mapping_valid'],bool),w,'mapping_valid must be bool/null')
                    for key in CGROUP+COUNTERS:
                        if p[key] is not None:
                            value=number(p[key],w,integer=key!='cpu_pct')
                            if key=='cpu_pct': require(value<=100,w,'CPU exceeds quota percent')
                            if key=='memory_bytes': require(value<=float(s['memory_limit_mb'])*2**20,w,'memory exceeds limit')
                    degraded=any(p[k] is None for k in CGROUP+COUNTERS+['mapping_valid']) or p['mapping_valid'] is not True or (p['loss_count'] or 0)>0
                    require(not degraded or r['status']!='OK',w,'missing/lost/unmapped resource must be degraded')
                else:
                    require(not r['window_start_ms'] and not r['window_end_ms'],w,'point observation cannot have windows')
                    if r['kind']=='interaction_health':
                        require(set(p)=={'healthy'} and isinstance(p['healthy'],bool),w,'health requires only healthy boolean')
                        require(p['healthy']==(r['status']=='OK'),w,'health status inconsistent')
                    else:
                        require(set(p)=={'action'} and p['action'] in {'EDIT','EXECUTE_REQUEST','CONNECT','DISCONNECT','RECONNECT','LOGOUT'},w,'interaction payload must contain only observed action')
            if name=='truth':
                for field, choices in [('interaction',{'RECENT','ABSENT','UNKNOWN'}),('connection',{'CONNECTED','DISCONNECTED','UNKNOWN'}),('workload',{'ACTIVE','IDLE','UNKNOWN'}),('eligibility',{'RETAIN','IDLE_ELIGIBLE','UNKNOWN'})]:
                    require(r[field] in choices,w,f'invalid {field} label')
                require(r['label_source']==('synthetic_scenario' if synthetic else 'execution_ack'),w,'truth provenance mismatch')
                expected='RETAIN' if r['interaction']=='RECENT' or r['workload']=='ACTIVE' else ('UNKNOWN' if 'UNKNOWN' in (r['interaction'],r['workload']) else 'IDLE_ELIGIBLE')
                require(r['eligibility']==expected,w,'eligibility contradicts independent labels')
    for sid,s in sessions.items():
        truth=sorted(grouped['truth'][sid],key=lambda r:int(r['start_ms']))
        cursor=int(s['start_ms'])
        for r in truth:
            require(int(r['start_ms'])==cursor,'truth.csv session '+sid,'overlap or gap in complete truth coverage')
            cursor=int(r['end_ms'])
        require(cursor==int(s['end_ms']),'truth.csv session '+sid,'truth does not cover session end')
        windows=sorted([r for r in grouped['observations'][sid] if r['kind']=='resource'],key=lambda r:int(r['window_start_ms']))
        for prev,r in zip(windows,windows[1:]):
            require(int(prev['window_end_ms'])<=int(r['window_start_ms']),'observations.csv session '+sid,'overlapping/duplicate resource windows')
        events=sorted(grouped['events'][sid],key=lambda r:int(r['at_ms']))
        jobs={}; connection=False
        for r in events:
            action=r['action']; job=r['job_id']; t=int(r['at_ms'])
            w='events.csv:row '+str(data['events'].index(r)+2)
            if action in ('CONNECT','RECONNECT'):
                require(not connection,w,'already connected')
                connection=True
            elif action in ('DISCONNECT','LOGOUT'):
                require(connection,w,'disconnect without connection')
                connection=False
            elif action in ('EDIT','EXECUTE'):
                require(connection,w,'user action while disconnected')
            if action=='EXECUTE':
                require(job not in jobs,w,'duplicate execution request')
                jobs[job]={'request':t,'start':None,'end':None,'outcome':None}
            elif action.startswith('JOB_'):
                require(job in jobs,w,'job acknowledgement without request')
                j=jobs[job]
                if action=='JOB_START':
                    require(j['start'] is None and j['end'] is None,w,'duplicate/out-of-order job start')
                    j['start']=t
                else:
                    require(j['start'] is not None and j['end'] is None,w,'terminal job without unique acknowledged start')
                    j['end']=t; j['outcome']=action
        phases=grouped['phases'][sid]
        for r in phases:
            if r['job_id']:
                require(r['job_id'] in jobs,'phases.csv session '+sid,'phase job lacks EXECUTE request')
        for job,j in jobs.items():
            pp=sorted([p for p in phases if p['job_id']==job],key=lambda p:int(p['start_ms']))
            require(bool(pp),'events.csv session '+sid,'job has no phase group')
            require(j['request']<=int(pp[0]['start_ms']),'phases.csv session '+sid,'phase before request')
            for left,right in zip(pp,pp[1:]):
                require(int(left['end_ms'])==int(right['start_ms']),'phases.csv session '+sid,'job phase gap/overlap')
            if synthetic:
                outcome=json.loads(pp[-1]['parameters_json']).get('outcome','COMPLETE')
                require(outcome=='UNCONFIRMED' or (j['start']==int(pp[0]['start_ms']) and j['end']==int(pp[-1]['end_ms'])),'events.csv session '+sid,'synthetic phase lifecycle mismatch')
        if not synthetic:
            # Planned intervals never establish execution. Unconfirmed or failed work
            # requires UNKNOWN; only a successful acknowledged interval is ACTIVE.
            for r in truth:
                a=int(r['start_ms']); b=int(r['end_ms'])
                boundaries={a,b}
                for j in jobs.values():
                    for t in (j['request'],j['start'],j['end']):
                        if t is not None and a<t<b: boundaries.add(t)
                for p in phases:
                    for t in (int(p['start_ms']),int(p['end_ms'])):
                        if a<t<b: boundaries.add(t)
                for t in sorted(boundaries)[:-1]:
                    active=any(j['start'] is not None and j['end'] is not None and j['outcome']=='JOB_COMPLETE' and j['start']<=t<j['end'] for j in jobs.values())
                    uncertain=any(j['request']<=t and (j['end'] is None or t<j['end']) and not (j['start'] is not None and j['end'] is not None and j['outcome']=='JOB_COMPLETE') for j in jobs.values())
                    expected='ACTIVE' if active else ('UNKNOWN' if uncertain else 'IDLE')
                    require(r['workload']==expected,'truth.csv session '+sid,'measured workload must follow actual acknowledgements; unconfirmed/failed job is UNKNOWN, never planned success')
    return m
