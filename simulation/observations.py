"""Synthetic signal model; no truth labels enter this projection."""
import json
from .contract import dumps, CGROUP, COUNTERS


def observe(session, events, phases, faults, rng):
    lo=int(session['start_ms']); hi=int(session['end_ms'])
    def fault(kind,t):
        return next((f for f in faults if f['kind']==kind and f['start_ms']<=t-lo<f['end_ms']),None)
    out=[]
    def add(kind,at,payload,status='OK',start='',end='',delay=0):
        out.append(dict(run_id=session['run_id'],session_id=session['session_id'],container_instance_id=session['container_instance_id'],kind=kind,at_ms=at,available_at_ms=at+delay,window_start_ms=start,window_end_ms=end,source='synthetic_model' if kind=='resource' else 'synthetic_session_service',status=status,payload_json=dumps(payload)))
    for e in events:
        action=e['action']; at=int(e['at_ms'])
        if action.startswith('JOB_') or fault('health_outage',at): continue
        add('connection' if action in {'CONNECT','RECONNECT','DISCONNECT','LOGOUT'} else 'interaction',at,{'action':'EXECUTE_REQUEST' if action=='EXECUTE' else action})
    for at in range(lo,hi,5000):
        healthy=not bool(fault('health_outage',at))
        add('interaction_health',at,{'healthy':healthy},'OK' if healthy else 'UNHEALTHY')
    for a in range(lo,hi,5000):
        b=min(a+5000,hi)
        if fault('resource_outage',a): continue
        # Integrate over exact phase intersections and burst pulse intersections.
        cpu=.05; disk=network=proc=io=sock=0; memory=int(float(session['memory_limit_mb'])*2**20*.2)
        for p in phases:
            left=max(a,int(p['start_ms'])); right=min(b,int(p['end_ms']))
            if left>=right or not p['job_id']: continue
            par=json.loads(p['parameters_json']); w=p['workload']; overlap=right-left
            if w=='BURST':
                base=int(p['start_ms']); period=par['burst_period_ms']; width=par['burst_width_ms']
                pulse=0
                for k in range(max(0,(left-base)//period), (right-base)//period+1):
                    pulse+=max(0,min(right,base+k*period+width)-max(left,base+k*period))
                cpu+=100*par['cpu_duty']*pulse/(b-a)
                proc+=int(pulse>0)
            else:
                cpu+=100*par['cpu_duty']*overlap/(b-a)
            memory=max(memory,par['memory_bytes'])
            if w=='CPU': proc+=2
            elif w=='DISK_IO':
                # Alternating 10s waits, still unfinished execution in truth.
                if ((left-int(p['start_ms']))//10000)%2==0:
                    disk+=int(par['disk_rate_bytes_s']*overlap/1000);io+=2
            elif w=='NETWORK_WAIT':
                # Only request/response edges carry traffic: long silent wait.
                if left==int(p['start_ms']) or right==int(p['end_ms']):
                    network+=par['network_bytes']//2;sock+=1
            elif w=='LOW_CPU': proc+=1
        payload=dict(cpu_pct=round(min(100,cpu*rng.uniform(.9,1.1)),6),memory_bytes=memory,disk_read_bytes=disk,disk_write_bytes=disk//2,network_rx_bytes=network,network_tx_bytes=network//8,process_events=proc,io_events=io,socket_events=sock,loss_count=0,mapping_valid=True,cgroup_source='synthetic_cgroup_v2',event_source='synthetic_ebpf')
        status='OK'
        if fault('missing_cgroup',a):
            for k in CGROUP: payload[k]=None
            status='DEGRADED'
        if fault('missing_events',a):
            for k in COUNTERS: payload[k]=None
            status='DEGRADED'
        if fault('invalid_mapping',a): payload['mapping_valid']=False;status='DEGRADED'
        if fault('event_loss',a): payload['loss_count']=3;status='DEGRADED'
        delay=fault('delay',a)
        add('resource',b,payload,status,a,b,delay['delay_ms'] if delay else 0)
    return sorted(out,key=lambda r:(r['available_at_ms'],r['at_ms'],r['kind']))
