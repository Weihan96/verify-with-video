"""Each real task runs this finite trial itself with its own participant receipt.

The common wall clock synchronizes independent clients; actual receiver logs,
not this planned schedule, are the acceptance evidence.
"""
import argparse,json,pathlib,subprocess,sys,time
import access as a
import control
import send
import desktop
p=argparse.ArgumentParser();p.add_argument('participant',type=pathlib.Path);p.add_argument('--start-at',type=float,required=True);args=p.parse_args()
participant,g,m=a.participant(args.participant,'record-control');run=pathlib.Path(participant['run']);root=pathlib.Path(g['run']);label=m['label'];points=json.loads((run/'points.json').read_text());sequence=0;records=[]
def note(event,**fields):
    row=dict(time=time.time(),event=event,thread_id=a.own(),label=label,**fields);records.append(row)
    with (run/'trial.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    print(json.dumps(row),flush=True)
def state():return json.loads((run/'state.json').read_text())
def wait_until(t):
    while True:
        if (root/'abort').exists():raise RuntimeError('Coordinator aborted experiment')
        remaining=t-time.time()
        if remaining<=0:return
        time.sleep(min(.15,remaining))
def key(name,**kw):return [dict(type=name,value=v,delay=.10,**kw) for v in ('PRESS','RELEASE')]
def move(point,delay=.12):
    x,y=point;scale=points['pixel_scale'];return dict(type='MOUSEMOVE',value='NOTHING',x=round(x*scale),y=round((points['image_height']-y)*scale),delay=delay)
def click(name):return [move(points['points'][name])]+key('LEFTMOUSE')
def cycle(stage):
    global sequence
    sequence+=1;text=f'{label}-{stage}-{sequence}';before=state();events=click('text')+key('A',ctrl=True)
    for c in text:events += [dict(type='A',value='PRESS',unicode=c,delay=.035),dict(type='A',value='RELEASE',delay=.025)]
    events+=key('RET')+click('enabled')+click('increment')
    x,y=points['points']['value'];sign=1 if sequence%2 else -1
    events += [move((x,y)),dict(type='LEFTMOUSE',value='PRESS',delay=.12),move((x+sign*15,y),.2),move((x+sign*30,y),.2),move((x+sign*45,y),.2),dict(type='LEFTMOUSE',value='RELEASE',delay=.12)]
    v=points['points']['viewport'];end=points['points']['viewport_end']
    if sequence%2==0:v,end=end,v
    events += [move(v),dict(type='MIDDLEMOUSE',value='PRESS',delay=.12),move(((v[0]+end[0])/2,(v[1]+end[1])/2),.25),move(end,.25),dict(type='MIDDLEMOUSE',value='RELEASE',delay=.12)]
    sent=send.send(args.participant,events,time.time()+.15);note('batch_sent',stage=stage,command=sent,expected_text=text)
    deadline=time.monotonic()+30;target=before['sequence']+len(events)
    while time.monotonic()<deadline:
        now=state()
        if now['sequence']>=target and now['pending']==0:break
        if now['drained']:raise RuntimeError('Worker unexpectedly drained; inspect errors')
        time.sleep(.1)
    else:raise RuntimeError('Worker batch did not complete')
    time.sleep(.3);after=state()
    a.require(after['text']==text and after['clicks']==before['clicks']+1 and after['enabled']!=before['enabled'],'UI text/button state did not match own actions')
    a.require(after['value']!=before['value'],'Numeric drag did not change value')
    views=lambda st:[ar for w in st['windows'] for ar in w['areas'] if ar['type']=='VIEW_3D']
    a.require(views(after)[0]['perspective']=='PERSP' and views(after)[0]['view_rotation']!=views(before)[0]['view_rotation'],'Perspective orbit did not change')
    note('batch_observed',stage=stage,command_id=sent['command_id'],text=after['text'],clicks=after['clicks'],value=after['value'],view_rotation=views(after)[0]['view_rotation'])
def work_until(offset,stage):
    while time.time()<args.start_at+offset:wait_until(time.time());cycle(stage)
def stop_and_guard():
    result=control.control(args.participant,'stop');note('record_stopped',result=result)
    try:send.send(args.participant,key('ESC'))
    except ValueError as error:note('stopped_input_rejected',reason=str(error))
    else:raise RuntimeError('Input incorrectly accepted without own recorder')
def close():
    subprocess.run([sys.executable,str(a.ROOT/'scripts/desktop.py'),'close','--isolation-group',participant['group'],'--session',str(run/'session.json')],check=True)
    subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('group.py')),'closed','--group',participant['group']],check=True)
    note('owned_instance_closed')
success=False
try:
    note('starting',planned_start=args.start_at);control.control(args.participant,'start');note('record_ready')
    wait_until(args.start_at);work_until(20,'both')
    if label=='A':
        wait_until(args.start_at+22);stop_and_guard();wait_until(args.start_at+30);control.control(args.participant,'start');note('record_restarted');work_until(100,'live')
        stop_and_guard();close();success=True;note('participant_finished')
    else:
        work_until(62,'live');stop_and_guard();wait_until(args.start_at+70);control.control(args.participant,'start');note('record_restarted');work_until(105,'live')
        deadline=args.start_at+420
        while not (root/'continue-after-A-task-completed.json').exists():
            a.require(time.time()<deadline,'Timed out awaiting actual A task completion');wait_until(time.time());cycle('await-A')
        notice=json.loads((root/'continue-after-A-task-completed.json').read_text());note('A_task_completion_observed',notice=notice)
        for _ in range(3):cycle('after-A')
        stop_and_guard();close();success=True;note('participant_finished')
except BaseException as error:
    note('trial_failed',reason=str(error));(run/'trial-failed.json').write_text(json.dumps(dict(reason=str(error),time=time.time())))
    try:
        s=json.loads((run/'session.json').read_text())
        if json.loads(pathlib.Path(s['registry']).read_text()).get('recording'):
            try:control.control(args.participant,'stop')
            except BaseException:control.control(args.participant,'collect')
        close()
    except BaseException as cleanup:note('cleanup_failed',reason=str(cleanup))
    raise
finally:
    (run/'trial-result.json').write_text(json.dumps(dict(success=success,thread_id=a.own(),label=label,planned_start=args.start_at,records=records,final_state=state()),indent=2))
