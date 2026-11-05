"""Evaluator labels from actual acknowledgements, never planned phase intervals."""


def build_truth(session, events):
    lo, hi = int(session['start_ms']), int(session['end_ms'])
    events = sorted(events, key=lambda e: int(e['at_ms']))
    jobs = {}
    recent_actions = {'CONNECT', 'RECONNECT', 'EDIT', 'EXECUTE'}
    boundaries = {lo, hi}
    for e in events:
        t = int(e['at_ms'])
        boundaries.add(t)
        if e['action'] in recent_actions and t + 30000 < hi:
            boundaries.add(t + 30000)
        action, job = e['action'], e['job_id']
        if action == 'EXECUTE':
            jobs[job] = dict(request=t, start=None, end=None, outcome=None)
        elif action.startswith('JOB_'):
            if job not in jobs:
                raise ValueError('acknowledgement without actual request')
            if action == 'JOB_START':
                jobs[job]['start'] = t
            else:
                jobs[job].update(end=t, outcome=action)
    points = sorted(t for t in boundaries if lo <= t <= hi)
    result = []
    for a, b in zip(points, points[1:]):
        past = [e for e in events if int(e['at_ms']) <= a]
        recent = any(e['action'] in recent_actions and a - int(e['at_ms']) < 30000 for e in past)
        connections = [e for e in past if e['action'] in {'CONNECT', 'RECONNECT', 'DISCONNECT', 'LOGOUT'}]
        connection = ('UNKNOWN' if not connections else 'CONNECTED' if connections[-1]['action'] in {'CONNECT', 'RECONNECT'} else 'DISCONNECTED')
        active = any(j['start'] is not None and j['end'] is not None and j['outcome'] == 'JOB_COMPLETE' and j['start'] <= a < j['end'] for j in jobs.values())
        uncertain = any(j['request'] <= a and (j['end'] is None or a < j['end']) and not (j['start'] is not None and j['end'] is not None and j['outcome'] == 'JOB_COMPLETE') for j in jobs.values())
        workload = 'ACTIVE' if active else 'UNKNOWN' if uncertain else 'IDLE'
        eligibility = 'RETAIN' if recent or active else 'UNKNOWN' if uncertain else 'IDLE_ELIGIBLE'
        result.append(dict(run_id=session['run_id'], session_id=session['session_id'],
                           start_ms=a, end_ms=b, interaction='RECENT' if recent else 'ABSENT',
                           connection=connection, workload=workload, eligibility=eligibility,
                           reason='actual_ack_and_executed_interaction', label_source='execution_ack'))
    return result
