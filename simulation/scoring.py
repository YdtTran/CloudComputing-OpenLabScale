"""Score finalized predictions independently of policy execution."""
import csv
import hashlib
import json
from pathlib import Path
from .contract import LIMITATION, dumps, digest, read_manifest, read_table, write_json
from .policies import POLICIES,SESSION_FIELDS,PRED_FIELDS,config_values
from .validation import validate

COUNT_FIELDS=('tp','fp','tn','fn','abstain_eligible','abstain_retain','unknown_truth')
FORMULAS={
 'precision':'tp/(tp+fp)', 'recall':'tp/(tp+fn)', 'f1':'2*tp/(2*tp+fp+fn)',
 'false_idle_rate':'fp/(fp+tn)', 'false_active_rate':'fn/(fn+tp)',
 'coverage':'(tp+fp+tn+fn)/(tp+fp+tn+fn+abstain_eligible+abstain_retain)',
 'idle_capture':'tp/(tp+fn+abstain_eligible)',
}


def ratio(a,b):return a/b if b else None


def metrics(counts):
    tp,fp,tn,fn=(counts[k] for k in ('tp','fp','tn','fn'))
    definite=tp+fp+tn+fn;eligible=tp+fn+counts['abstain_eligible']
    known=definite+counts['abstain_eligible']+counts['abstain_retain']
    fractions=dict(precision=(tp,tp+fp),recall=(tp,tp+fn),f1=(2*tp,2*tp+fp+fn),false_idle_rate=(fp,fp+tn),false_active_rate=(fn,fn+tp),coverage=(definite,known),idle_capture=(tp,eligible))
    return dict(counts=counts,values={k:ratio(*v) for k,v in fractions.items()},numerators={k:v[0] for k,v in fractions.items()},denominators={k:v[1] for k,v in fractions.items()},known_truth_ticks=known,eligible_truth_ticks=eligible,definite_predictions=definite,unknown_predictions=counts['abstain_eligible']+counts['abstain_retain'],unsafe_recommendations=fp)


def join_truth(truth,sid,t):
    matches=[r for r in truth if r['session_id']==sid and int(r['start_ms'])<=t<int(r['end_ms'])]
    if len(matches)!=1:raise ValueError(f'truth.csv session {sid} at {t}: expected one half-open truth interval')
    return matches[0]


def score_rows(predictions, truth, sessions, source_modes):
    if len(set(source_modes))!=1:raise ValueError('measured and synthetic provenance cannot be pooled')
    counts={k:0 for k in COUNT_FIELDS}
    for p in predictions:
        label=join_truth(truth,p['session_id'],int(p['decision_ms']))['eligibility']
        decision=p['decision']
        if decision not in ('RETAIN','IDLE_CANDIDATE','UNKNOWN'):raise ValueError('unsupported prediction decision')
        if label=='UNKNOWN':counts['unknown_truth']+=1
        elif decision=='UNKNOWN':counts['abstain_eligible' if label=='IDLE_ELIGIBLE' else 'abstain_retain']+=1
        elif decision=='IDLE_CANDIDATE':counts['tp' if label=='IDLE_ELIGIBLE' else 'fp']+=1
        else:counts['fn' if label=='IDLE_ELIGIBLE' else 'tn']+=1
    intervals=[]
    for s in sessions:
        sid=s['session_id'];eligible=[]
        for r in sorted([r for r in truth if r['session_id']==sid],key=lambda r:int(r['start_ms'])):
            if r['eligibility']!='IDLE_ELIGIBLE':continue
            a=int(r['start_ms']);b=int(r['end_ms'])
            if eligible and eligible[-1][1]==a:eligible[-1][1]=b
            else:eligible.append([a,b])
        for a,b in eligible:
            candidates=[int(p['decision_ms']) for p in predictions if p['session_id']==sid and p['decision']=='IDLE_CANDIDATE' and a<=int(p['decision_ms'])<b]
            first=min(candidates) if candidates else None
            intervals.append(dict(session_id=sid,start_ms=a,end_ms=b,first_candidate_ms=first,latency_ms=first-a if first is not None else None,censored=first is None))
    delays=[i['latency_ms'] for i in intervals if not i['censored']]
    result=metrics(counts)
    result['latency']=dict(intervals=intervals,eligible_intervals=len(intervals),detected_intervals=len(delays),undetected_intervals=len(intervals)-len(delays),mean_detected_ms=ratio(sum(delays),len(delays)),mean_denominator=len(delays))
    return result


def score(bundle, output):
    root=Path(bundle);out=Path(output)
    # This is the first stage that opens evaluator-only truth.
    m=validate(root)
    metadata=json.loads((out/'prediction-metadata.json').read_text())
    if metadata['source_mode']!=m['source_mode']:raise ValueError('measured and synthetic provenance cannot be pooled')
    if digest(out/'predictions.csv')!=metadata['predictions_sha256']:raise ValueError('prediction checksum mismatch')
    cfg=config_values(metadata['config'])
    config_hash=hashlib.sha256(dumps(cfg).encode()).hexdigest()
    if config_hash!=metadata['config_hash']:raise ValueError('configuration hash mismatch')
    sessions=read_table(root,'sessions');obs=read_table(root,'observations')
    detector_sessions=[{k:s[k] for k in SESSION_FIELDS} for s in sessions]
    input_hash=hashlib.sha256(dumps(dict(sessions=detector_sessions,observations=obs,sample_ms=m['sample_ms'],source_mode=m['source_mode'])).encode()).hexdigest()
    if input_hash!=metadata['input_hash']:raise ValueError('predictions do not match observation inputs')
    with (out/'predictions.csv').open(newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames!=PRED_FIELDS:raise ValueError('prediction schema mismatch')
        predictions=list(reader)
    by_session={s['session_id']:s for s in sessions};seen=set()
    for index,p in enumerate(predictions,2):
        w=f'predictions.csv:row {index}'
        if p['session_id'] not in by_session:raise ValueError(w+': unknown session')
        s=by_session[p['session_id']];t=int(p['decision_ms'])
        if p['policy'] not in POLICIES or p['config_hash']!=config_hash or p['policy_version']!='1.0':raise ValueError(w+': policy/config identity mismatch')
        if p['run_id']!=s['run_id'] or p['container_instance_id']!=s['container_instance_id']:raise ValueError(w+': run/instance mismatch')
        if t%5000 or not int(s['start_ms'])<t<int(s['end_ms']):raise ValueError(w+': invalid decision tick')
        key=(p['policy'],p['session_id'],t)
        if key in seen:raise ValueError(w+': duplicate prediction')
        seen.add(key)
    expected=sum(len(range((int(s['start_ms'])//5000+1)*5000,int(s['end_ms']),5000)) for s in sessions)*len(POLICIES)
    if len(seen)!=expected:raise ValueError('predictions.csv: incomplete common policy timeline')
    truth=read_table(root,'truth')
    policies={}
    for policy in POLICIES:
        pp=[p for p in predictions if p['policy']==policy]
        def group(ss):
            ids={s['session_id'] for s in ss}
            return score_rows([p for p in pp if p['session_id'] in ids],truth,ss,[m['source_mode']])
        scenarios={name:group([s for s in sessions if s['scenario_id']==name]) for name in sorted({s['scenario_id'] for s in sessions})}
        micro=group(sessions)
        macro={}
        for metric in FORMULAS:
            values=[g['values'][metric] for g in scenarios.values() if g['values'][metric] is not None]
            macro[metric]=dict(value=ratio(sum(values),len(values)),contributing_groups=len(values),weighting='equal scenario; undefined excluded')
        policies[policy]=dict(overall_micro=micro,by_scenario=scenarios,by_seed={str(m['seed']):micro},by_scenario_seed={name+':'+str(m['seed']):value for name,value in scenarios.items()},macro_by_scenario=macro)
    result=dict(schema_version='1.0',source_mode=m['source_mode'],limitations=LIMITATION if m['source_mode']=='synthetic' else m.get('limitations', 'Measured contract data: verify actual probe coverage and independent acknowledgements; this report does not establish real-world accuracy or monitoring overhead.'),seed=m['seed'],seed_role='held-out synthetic check' if m['seed']==44 and m['source_mode']=='synthetic' else 'development' if m['seed'] in (42,43) else 'unspecified',bundle_manifest_sha256=digest(root/'manifest.json'),bundle_files=m['files'],prediction_metadata=metadata,formulas=FORMULAS,zero_denominator='null / N/A',timing='global 5000ms ticks, start < tick < end; half-open truth joins',aggregation='micro sums counts; macro equal scenario, undefined omitted with contributing count; latency mean over detected intervals only; undetected censored',policies=policies)
    write_json(out/'metrics.json',result)
    lines=['# Offline policy evaluation','',result['limitations'],'',f"Source: {m['source_mode']}; seed: {m['seed']} ({result['seed_role']}).",f"Configuration SHA-256: {config_hash}",f"Bundle manifest SHA-256: {result['bundle_manifest_sha256']}",'',result['timing']+'.',result['aggregation']+'. Zero denominators: N/A.','', '| Policy | TP | FP | TN | FN | Unknown predictions | Unknown truth | Precision | Recall | F1 | Coverage | Idle capture | Undetected intervals |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    def fmt(v):return 'N/A' if v is None else f'{v:.6f}'
    for policy,g in policies.items():
        x=g['overall_micro'];c=x['counts'];v=x['values']
        lines.append('| '+' | '.join(map(str,[policy,c['tp'],c['fp'],c['tn'],c['fn'],x['unknown_predictions'],c['unknown_truth']]+[fmt(v[k]) for k in ('precision','recall','f1','coverage','idle_capture')]+[x['latency']['undetected_intervals']]))+' |')
    lines+=['','## Formulas','']+[f'- {k}: `{v}`' for k,v in FORMULAS.items()]
    for policy,g in policies.items():
        lines+=['',f'## {policy}: scenario / seed {m["seed"]}','','| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
        for scenario,x in g['by_scenario'].items():
            lines.append('| '+' | '.join([scenario]+[fmt(x['values'][k]) for k in ('precision','recall','f1','false_idle_rate','false_active_rate','coverage','idle_capture')]+[fmt(x['latency']['mean_detected_ms']),str(x['latency']['undetected_intervals'])])+' |')
        lines+=['','Equal-scenario macro (contributing groups): '+', '.join(f"{k}={fmt(v['value'])} ({v['contributing_groups']})" for k,v in g['macro_by_scenario'].items())+'.']
    lines+=['','Counts, all numerators/denominators, per-interval latency, seed groups, hashes and effective configuration are in metrics.json.','']
    (out/'report.md').write_text('\n'.join(lines))
    return result
