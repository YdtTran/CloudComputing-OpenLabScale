"""Independent scenario, truth and noisy observation timelines."""
import copy
import json
import random
from pathlib import Path
from . import VERSION
from .contract import TABLES, SCHEMA, LIMITATION, dumps, identity, write_json, write_table, digest
from .scenarios import TEMPLATES


def stream(seed, index, purpose):
    t=TEMPLATES[index%len(TEMPLATES)]
    return random.Random(int(identity(seed,t['id'],index//len(TEMPLATES),VERSION,purpose),16))


def expand(seed=42, count=10, start_offset_ms=0, cpu_limit_cores=.5, memory_limit_mb=256):
    if count<1 or start_offset_ms<0 or not 0<cpu_limit_cores<=64 or not 1<=memory_limit_mb<=65536:
        raise ValueError('count >=1, offset >=0, CPU in (0,64], memory in [1,65536] MiB required')
    run=identity(seed,VERSION,'run')
    rows={name:[] for name in TABLES}
    for index in range(count):
        t=copy.deepcopy(TEMPLATES[index%len(TEMPLATES)])
        rng=stream(seed,index,'schedule'); offset=index*start_offset_ms
        sid=identity(seed,index,VERSION,'session'); cid=identity(seed,index,VERSION,'instance')
        rows['sessions'].append(dict(run_id=run,session_id=sid,user_id=identity(seed,index,VERSION,'user'),container_instance_id=cid,scenario_id=t['id'],start_ms=offset,end_ms=offset+t['duration_ms'],cpu_limit_cores=cpu_limit_cores,memory_limit_mb=memory_limit_mb))
        events=[dict(at_ms=offset+at,action=action,job_id='',parameters_json='{}') for at,action in t['events']]
        jobs={p['job'] for p in t['phases']}
        for job in sorted(jobs):
            pp=[p for p in t['phases'] if p['job']==job]; jid=identity(seed,index,job,VERSION)
            a=min(p['start_ms'] for p in pp)+offset; b=max(p['end_ms'] for p in pp)+offset
            for at,action in [(a,'EXECUTE'),(a,'JOB_START'),(b,'JOB_COMPLETE')]:
                events.append(dict(at_ms=at,action=action,job_id=jid,parameters_json='{}'))
            for phase_index,p in enumerate(pp):
                params=p['parameters']
                params['cpu_duty']=round(params['cpu_duty']*rng.uniform(.9,1.1),6)
                params['memory_bytes']=min(int(memory_limit_mb*2**20*.75),int(params['memory_bytes']*rng.uniform(.9,1.1)))
                rows['phases'].append(dict(run_id=run,session_id=sid,phase_id=identity(seed,index,job,phase_index,VERSION),job_id=jid,start_ms=offset+p['start_ms'],end_ms=offset+p['end_ms'],workload=p['workload'],parameters_json=dumps(params)))
        # Explicit jobless idle phases fill the replay timeline.
        cursor=offset
        for p in sorted([p for p in rows['phases'] if p['session_id']==sid],key=lambda p:p['start_ms']):
            if cursor<p['start_ms']:
                rows['phases'].append(dict(run_id=run,session_id=sid,phase_id=identity(sid,cursor,'idle'),job_id='',start_ms=cursor,end_ms=p['start_ms'],workload='IDLE',parameters_json='{}'))
            cursor=p['end_ms']
        if cursor<offset+t['duration_ms']:
            rows['phases'].append(dict(run_id=run,session_id=sid,phase_id=identity(sid,cursor,'idle'),job_id='',start_ms=cursor,end_ms=offset+t['duration_ms'],workload='IDLE',parameters_json='{}'))
        for n,e in enumerate(sorted(events,key=lambda e:e['at_ms'])):
            rows['events'].append(dict(run_id=run,session_id=sid,event_id=identity(sid,n,'event'),**e))
    return run,rows


def build_truth(session, events, phases, mode='synthetic'):
    """Scenario/ack semantics only: never accepts resource observations."""
    lo=int(session['start_ms']); hi=int(session['end_ms'])
    relevant={'CONNECT','RECONNECT','EDIT','EXECUTE'}
    points={lo,hi}
    for e in events:
        t=int(e['at_ms']); points.add(t)
        if e['action'] in relevant and t+30000<hi: points.add(t+30000)
    for p in phases: points.update((int(p['start_ms']),int(p['end_ms'])))
    result=[]
    for a,b in zip(sorted(points),sorted(points)[1:]):
        if a>=hi or a==b: continue
        past=[e for e in events if int(e['at_ms'])<=a]
        recent=any(e['action'] in relevant and a-int(e['at_ms'])<30000 for e in past)
        connections=[e for e in past if e['action'] in {'CONNECT','RECONNECT','DISCONNECT','LOGOUT'}]
        connection='UNKNOWN' if not connections else ('CONNECTED' if connections[-1]['action'] in {'CONNECT','RECONNECT'} else 'DISCONNECTED')
        active=[p for p in phases if int(p['start_ms'])<=a<int(p['end_ms']) and p['job_id']]
        workload='IDLE'
        if active:
            workload='UNKNOWN' if any(json.loads(p['parameters_json']).get('outcome')=='UNCONFIRMED' for p in active) else 'ACTIVE'
        interaction='RECENT' if recent else 'ABSENT'
        eligibility='RETAIN' if recent or workload=='ACTIVE' else ('UNKNOWN' if workload=='UNKNOWN' else 'IDLE_ELIGIBLE')
        state=dict(interaction=interaction,connection=connection,workload=workload,eligibility=eligibility,reason='recent_interaction' if recent else ('unfinished_job' if workload=='ACTIVE' else ('unconfirmed_execution' if workload=='UNKNOWN' else 'no_job_or_recent_interaction')),label_source='synthetic_scenario' if mode=='synthetic' else 'execution_ack')
        if result and all(result[-1][k]==v for k,v in state.items()):
            result[-1]['end_ms']=b
        else:
            result.append(dict(run_id=session['run_id'],session_id=session['session_id'],start_ms=a,end_ms=b,**state))
    return result


def generate(output, seed=42, count=10, start_offset_ms=0, cpu_limit_cores=.5, memory_limit_mb=256, overwrite=False):
    root=Path(output)
    if root.exists() and any(root.iterdir()) and not overwrite:
        raise ValueError(f'{root}: output exists; choose --overwrite explicitly')
    run,rows=expand(seed,count,start_offset_ms,cpu_limit_cores,memory_limit_mb)
    from .observations import observe
    for index,s in enumerate(rows['sessions']):
        events=[e for e in rows['events'] if e['session_id']==s['session_id']]
        phases=[p for p in rows['phases'] if p['session_id']==s['session_id']]
        rows['truth'].extend(build_truth(s,events,phases))
        rows['observations'].extend(observe(s,events,phases,TEMPLATES[index%len(TEMPLATES)]['faults'],stream(seed,index,'noise')))
    root.mkdir(parents=True,exist_ok=True)
    for name in TABLES: write_table(root/(name+'.csv'),name,rows[name])
    write_json(root/'manifest.json',dict(schema_version=SCHEMA,generator_version=VERSION,run_id=run,seed=seed,config=dict(session_count=count,start_offset_ms=start_offset_ms,cpu_limit_cores=cpu_limit_cores,memory_limit_mb=memory_limit_mb),duration_ms=max(s['end_ms'] for s in rows['sessions']),sample_ms=5000,interaction_truth_ms=30000,clock='elapsed_ms',origin_utc=None,source_mode='synthetic',limitations=LIMITATION,files={name+'.csv':digest(root/(name+'.csv')) for name in TABLES}))
    from .validation import validate
    validate(root)
    return root
