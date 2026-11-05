"""Fixed, inspectable 300-second templates; units are elapsed milliseconds."""
from .contract import WORKLOADS


def parameters(workload, duration=160000):
    return dict(cpu_duty={'CPU':.75,'DISK_IO':.005,'NETWORK_WAIT':.002,'BURST':.8,'LOW_CPU':.004}.get(workload,0),memory_bytes=64*2**20,disk_file_bytes=16*2**20 if workload=='DISK_IO' else 0,disk_rate_bytes_s=2*2**20 if workload=='DISK_IO' else 0,network_bytes=1024*1024 if workload=='NETWORK_WAIT' else 0,response_delay_ms=min(120000,duration) if workload=='NETWORK_WAIT' else 0,burst_width_ms=200,burst_period_ms=10000,outcome='COMPLETE')


def template(name, family, phases=(), edits=(), transitions=(), faults=()):
    return dict(id=name,family=family,duration_ms=300000,events=[(0,'CONNECT')]+[(t,'EDIT') for t in edits]+list(transitions),phases=[dict(start_ms=a,end_ms=b,workload=w,parameters=parameters(w,b-a),job='main') for a,b,w in phases],faults=list(faults))


TEMPLATES = [
    template('cpu-background','CPU',[(20000,180000,'CPU')],transitions=[(40000,'DISCONNECT')]),
    template('disk-wait','DISK_IO',[(20000,180000,'DISK_IO')]),
    template('network-wait','NETWORK_WAIT',[(20000,180000,'NETWORK_WAIT')],transitions=[(40000,'DISCONNECT')]),
    template('bursty','BURST',[(20000,180000,'BURST')]),
    template('low-use','LOW_CPU',[(20000,180000,'LOW_CPU')]),
    template('pure-idle','IDLE'),
    template('mixed','MIXED',[(20000,70000,'CPU'),(70000,120000,'DISK_IO'),(120000,180000,'BURST')],edits=[10000]),
    template('editing-only','IDLE',edits=range(10000,180001,10000)),
    template('reconnect','IDLE',edits=[10000,20000,30000]+list(range(100000,180001,10000)),transitions=[(40000,'DISCONNECT'),(90000,'RECONNECT')]),
    template('signal-loss','IDLE',edits=[10000,20000],faults=[
        dict(kind='health_outage',start_ms=50000,end_ms=100000),
        dict(kind='resource_outage',start_ms=150000,end_ms=175000),
        dict(kind='missing_cgroup',start_ms=110000,end_ms=115000),
        dict(kind='missing_events',start_ms=120000,end_ms=125000),
        dict(kind='invalid_mapping',start_ms=130000,end_ms=135000),
        dict(kind='event_loss',start_ms=180000,end_ms=185000),
        dict(kind='delay',start_ms=190000,end_ms=195000,delay_ms=15000),
    ]),
]
