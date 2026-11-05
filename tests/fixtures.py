"""Small hand-authored contracts, independent of the scenario generator."""
from pathlib import Path
from simulation.contract import TABLES, digest, write_json, write_table


def write_minimal(path, mode='synthetic'):
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    rows = {name: [] for name in TABLES}
    rows['sessions'] = [dict(run_id='r', session_id='s', user_id='u', container_instance_id='c', scenario_id='minimal', start_ms=0, end_ms=45000, cpu_limit_cores=.5, memory_limit_mb=256)]
    rows['events'] = [dict(run_id='r', event_id='e', session_id='s', at_ms=0, action='CONNECT', job_id='', parameters_json='{}')]
    for start, end, interaction, eligibility in [(0,30000,'RECENT','RETAIN'),(30000,45000,'ABSENT','IDLE_ELIGIBLE')]:
        rows['truth'].append(dict(run_id='r', session_id='s', start_ms=start,end_ms=end,interaction=interaction, connection='CONNECTED',workload='IDLE',eligibility=eligibility,reason='hand-authored',label_source='synthetic_scenario' if mode=='synthetic' else 'execution_ack'))
    for name in TABLES:
        write_table(root / (name+'.csv'),name,rows[name])
    manifest = dict(schema_version='1.0',generator_version='fixture-1',run_id='r',seed=42,config={},duration_ms=45000,sample_ms=5000,interaction_truth_ms=30000,clock='elapsed_ms',origin_utc=None,source_mode=mode,files={name+'.csv':digest(root/(name+'.csv')) for name in TABLES})
    write_json(root/'manifest.json',manifest)
    return manifest, rows


def write_measured(path):
    """One acknowledged job and one unconfirmed request; plans differ from actual."""
    root=Path(path);m,rows=write_minimal(root,'measured')
    m['duration_ms']=100000;rows['sessions'][0]['end_ms']=100000
    for n,at,action,job in [(1,10000,'EXECUTE','j1'),(2,12000,'JOB_START','j1'),(3,22000,'JOB_COMPLETE','j1'),(4,50000,'EXECUTE','j2')]:
        rows['events'].append(dict(run_id='r',event_id='e'+str(n),session_id='s',at_ms=at,action=action,job_id=job,parameters_json='{}'))
    for n,a,b,job in [(1,10000,25000,'j1'),(2,50000,70000,'j2')]:
        rows['phases'].append(dict(run_id='r',phase_id='p'+str(n),session_id='s',job_id=job,start_ms=a,end_ms=b,workload='CPU',parameters_json='{"cpu_duty":0.5,"outcome":"COMPLETE"}'))
    rows['truth']=[]
    for a,b,interaction,workload,eligibility in [(0,12000,'RECENT','IDLE','RETAIN'),(12000,22000,'RECENT','ACTIVE','RETAIN'),(22000,40000,'RECENT','IDLE','RETAIN'),(40000,50000,'ABSENT','IDLE','IDLE_ELIGIBLE'),(50000,80000,'RECENT','UNKNOWN','RETAIN'),(80000,100000,'ABSENT','UNKNOWN','UNKNOWN')]:
        rows['truth'].append(dict(run_id='r',session_id='s',start_ms=a,end_ms=b,interaction=interaction,connection='CONNECTED',workload=workload,eligibility=eligibility,reason='actual_ack_or_unconfirmed',label_source='execution_ack'))
    for name in TABLES:
        write_table(root/(name+'.csv'),name,rows[name]);m['files'][name+'.csv']=digest(root/(name+'.csv'))
    write_json(root/'manifest.json',m)
    return m,rows
