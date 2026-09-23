"""Read actual receiver/capture/foreground evidence, independent of task summaries."""
import argparse,datetime,json,pathlib
p=argparse.ArgumentParser();p.add_argument('run',type=pathlib.Path);p.add_argument('--queue-handoff',action='store_true');args=p.parse_args();run=args.run
read=lambda path:json.loads(path.read_text())
def rows(path):return [json.loads(s) for s in path.read_text().splitlines() if s.startswith('{')]
events={k:rows(run/k/'events.jsonl') for k in ('A','B')}
trials={k:rows(run/k/'trial.jsonl') for k in ('A','B')}
inputs={k:[e for e in v if e['event']=='injected'] for k,v in events.items()}
cap=rows(run/'capture/capture.jsonl');fore=rows(run/'Foreground/foreground.jsonl');actions=rows(run/'foreground-input.jsonl')
sessions={k:read(run/k/'session.json') for k in ('A','B','Foreground')}
sp=read(run/'spaces-prepared.json')['windows'];checks={};detail={}
checks['distinct_real_tasks']=len({sessions[k]['thread_id'] for k in ('A','B')})==2
checks['distinct_fullscreen_spaces']=all(len(w['spaces'])==1 for w in sp) and len({w['spaces'][0] for w in sp})==2 and all(read(run/k/'native-fullscreen.json')['fullscreen'] for k in ('A','B'))
windows={}
for label in ('A','B'):
    grouped={}
    for row in inputs[label]:grouped.setdefault(row['command_id'],[]).append(row)
    windows[label]=[dict(id=k,start=v[0]['time'],end=v[-1]['time'],types=sorted({x['input']['type'] for x in v})) for k,v in grouped.items()]
    own=sessions[label]['thread_id'];other='B' if label=='A' else 'A'
    accepted=[read(f) for f in (run/label).glob('command-*.accepted')]
    checks[label+'_only_own_identity']=all(c['thread_id']==own for c in accepted) and all(e['pid']==sessions[label]['pid'] for e in inputs[label])
    checks[label+'_no_receiver_error']=not any(e['event']=='error' for e in events[label])
    checks[label+'_all_batches_observed']=len(grouped)>0 and len(grouped)==sum(t['event']=='batch_observed' for t in trials[label])
    checks[label+'_no_foreign_text']=not any(e['event']=='state_changed' and e['state']['text'].startswith(other+'-') for e in events[label])
    checks[label+'_closed_cleanly']=bool(sessions[label].get('closed')) and not read(pathlib.Path(sessions[label]['registry'])).get('recording')
    detail[label]=dict(events=len(inputs[label]),batches=windows[label],result=read(run/label/'trial-result.json')['success'])
overlaps=[dict(A=x['id'],B=y['id'],start=max(x['start'],y['start']),end=min(x['end'],y['end'])) for x in windows['A'] for y in windows['B'] if max(x['start'],y['start'])<min(x['end'],y['end'])]
checks['actual_input_overlap']=len(overlaps)>0;detail['overlaps']=overlaps
# Pair nearby actual injections of each class; this avoids inferring overlap from client start times.
together={}
for typ in ('A','LEFTMOUSE','MOUSEMOVE','MIDDLEMOUSE'):
    distances=[min(abs(e['time']-f['time']) for f in inputs['B'] if f['input']['type']==typ) for e in inputs['A'] if e['input']['type']==typ]
    together[typ]=min(distances) if distances else None
checks['every_input_class_overlaps']=all(v is not None and v<.25 for v in together.values());detail['nearest_cross_task_event_seconds']=together
lifecycle=[]
for label,other in [('A','B'),('B','A')]:
    life=rows(run/label/'lifecycle.jsonl')
    for i,event in enumerate(life):
        if event['event']!='completed' or event['action'] not in ('stop','start'):continue
        # Only restart starts (generation > 1), and stops that precede a restart.
        if event['action']=='start' and event['result']['generation']==1:continue
        if event['action']=='stop' and not any(x['event']=='completed' and x['action']=='start' for x in life[i+1:]):continue
        t=event['time'];other_inputs=[e for e in inputs[other] if abs(e['time']-t)<2]
        before=[c for c in cap if c['event']=='capture_health' and c['label']==other and t-3<=c['wall_time']<=t]
        after=[c for c in cap if c['event']=='capture_health' and c['label']==other and t<=c['wall_time']<=t+3]
        increase=bool(before and after and after[-1]['frames']>before[0]['frames'])
        lifecycle.append(dict(label=label,action=event['action'],time=t,other_input_events=len(other_inputs),other_frames_increased=increase))
checks['independent_stop_restart']=len(lifecycle)==4 and all(e['other_input_events'] and e['other_frames_increased'] for e in lifecycle);detail['lifecycle']=lifecycle
notice=read(run/'continue-after-A-task-completed.json');post=[x for x in trials['B'] if x['event']=='batch_observed' and x.get('stage')=='after-A']
checks['B_after_actual_A_task_end']=len(post)>=3 and notice['completedAt']>=sessions['A']['closed']-1 and all(x['time']>notice['completedAt'] for x in post)
detail['after_task_completion']=dict(notice=notice,post_batches=post)
begin=min(e[0]['time'] for e in inputs.values());end=max(sessions[k]['closed'] for k in ('A','B'))
f=[e for e in fore if begin<=e['time']<=end];samples=[e for e in f if e['event']=='sample'];expected=sessions['Foreground']['pid']
checks['foreground_not_stolen']=bool(samples) and all(e['front_pid']==expected for e in samples)
checks['native_foreground_input']=all(any(e['event']==typ for e in f) for typ in ('mouse_move','click','key')) and all(e['code']==0 and e['action']['require_focus'] for e in actions)
checks['foreground_probe_covers_trial']=min(e['time'] for e in fore)<=begin and max(e['time'] for e in fore)>=end
# Check Shift/Control/Option/Command bits defined by local CGEventTypes.h;
# raw flags also contain non-key state and are not limited to 0 or 256.
checks['no_stuck_modifiers']=all(e['flags'] & 0x1e0000 == 0 for e in samples)
checks['system_clipboard_unchanged']=len({e['clipboard_revision'] for e in samples})==1
detail['foreground']=dict(automated_not_human=True,samples=len(samples),events={t:sum(e['event']==t for e in f) for t in ('mouse_move','click','key')},pids=sorted({e['front_pid'] for e in samples}),flags=sorted({e['flags'] for e in samples}),interval=[begin,end])
checks['capture_all_valid']=not any(e['event'] in ('capture_failed','target_failed','target_finalize_failed') for e in cap) and all(e['valid'] for e in cap if e['event']=='writer_finished')
checks['corrected_decode_validation']=all(v['valid'] for v in read(run/'decode-revalidation.json'))
handoff=None
if args.queue_handoff:
    handoff=read(run/'queue-handoff.json')
    prep=handoff['preparation'];foreground=handoff['foreground']
    seconds=lambda value:datetime.datetime.fromisoformat(value).timestamp()
    release=seconds(prep['released_at']);acquired=seconds(foreground['acquired_at']);released=seconds(foreground['released_at'])
    checks['preparation_released_before_all_formal_input']=handoff['admitted_at']<=release<begin and release<=acquired
    checks['different_real_task_acquired_queue']=prep['thread_id']!=foreground['thread_id'] and foreground['thread_id']==sessions['Foreground']['thread_id'] and prep['lease_id']!=foreground['lease_id']
    checks['new_lease_covers_background_and_cleanup']=acquired<=begin and released>=end and sessions['Foreground']['lease_id']==foreground['lease_id']
    snapshots=handoff['snapshots']
    checks['background_cleanup_preserves_new_owner']=any(x['stage']=='after_group_finish' and x['time']>=end and x['queue']['current']['lease_id']==foreground['lease_id'] for x in snapshots)
    checks['queue_owner_received_real_input']=all(acquired<=e['start']<=e['end']<=released for e in actions)
    logs=list((run/'Foreground').glob('record-*.jsonl'))
    foreground_capture=rows(logs[0]) if len(logs)==1 else []
    checks['independent_foreground_recorder_finished']=any(e.get('event')=='capture_finished' for e in foreground_capture) and not any(e.get('event')=='capture_failed' or 'error' in e for e in foreground_capture)
result=dict(queue_handoff=handoff,scenario_checks_passed=all(checks.values()),original_runner_passed=all(detail[k]['result'] for k in ('A','B')),checks=checks,detail=detail)
(run/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(scenario_checks_passed=result['scenario_checks_passed'],original_runner_passed=result['original_runner_passed'],checks=checks),ensure_ascii=False,indent=2))
