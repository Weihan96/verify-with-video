"""Own target lifecycle; failures remain failures while independent cleanup is allowed."""
import argparse,json,pathlib,subprocess,time,uuid
import access as a
import desktop
from decode import validate as validate_video

def input_control(run,participant,action):
    request=str(uuid.uuid4());desktop.dump(run/'input-control.json',dict(id=request,thread_id=a.own(),token=participant['token'],action=action))
    for _ in range(100):
        state=json.loads((run/'state.json').read_text())
        if state.get('control_ack')==request:
            a.require(action!='drain' or state['drained'] and state['pending']==0 and not state['held'],'Input drain incomplete');return state
        time.sleep(.05)
    raise ValueError('Worker did not acknowledge input lifecycle; retain own instance and evidence')

def alive(record):
    try:return desktop.identity(record['pid'])==record['identity']
    except subprocess.CalledProcessError as error:
        if error.returncode==1:return False
        raise

def _control(p,g,m,action):
    run=pathlib.Path(p['run']);desktop.isolation_context(p['group'],'record-control');s=desktop.load_session(run/'session.json');r=s['isolation_broker']
    a.require(r['label']==m['label'] and pathlib.Path(r['group'])==pathlib.Path(p['group']),'Broker membership mismatch')
    registry=json.loads(pathlib.Path(s['registry']).read_text());active=registry.get('recording')
    a.require((action=='start' and not active) or (action in ('stop','collect') and active),'Recorder already in requested state')
    if action!='start':input_control(run,p,'drain')
    broker_alive=alive(r);a.require(broker_alive or action=='collect','Broker exited; use scoped collect to preserve failure and clean own registration')
    rows=a.read_rows(r['log']);baseline=len(rows);ack=None;generation=None
    if broker_alive:
        demand=pathlib.Path(r['output'])/('desired-'+m['label']+'.json');previous=json.loads(demand.read_text());generation=previous['generation']+1
        desktop.dump(demand,dict(generation=generation,active=action=='start'))
        for _ in range(200):
            rows=a.read_rows(r['log']);new=rows[baseline:]
            failures=[x for x in new if x.get('label')==m['label'] and x['event'] in ('target_failed','target_finalize_failed')]
            if failures:
                if action=='collect':ack=failures[-1];break
                raise ValueError('Target capture failed: '+str(failures))
            ack=next((x for x in reversed(new) if x.get('label')==m['label'] and x.get('generation')==generation),None)
            if action=='start' and ack and ack['event']=='capture_started' and any(x['event']=='first_frame' and x.get('output')==ack['output'] for x in new):break
            if action!='start' and ack and ack['event']=='target_stopped':break
            if not alive(r):
                if action=='collect':rows=a.read_rows(r['log']);break
                raise ValueError('Broker exited during request; collect failed recording')
            time.sleep(.1)
        else:raise ValueError('Target capture lifecycle timed out; retain own instance and evidence')
    validation=[];valid=True
    if action!='start':
        starts=[(i,x) for i,x in enumerate(rows) if x.get('label')==m['label'] and x['event']=='capture_started']
        a.require(starts,'Missing recorder start evidence; do not infer target shutdown')
        begin,started=starts[-1]
        failures=[x for x in rows[begin:] if x['event']=='capture_failed' or x.get('label')==m['label'] and x['event'] in ('target_failed','target_finalize_failed')]
        finished=[x for x in rows[begin:] if x['event']=='writer_finished' and x.get('output')==started['output']]
        valid=bool(finished and finished[-1]['valid'] and finished[-1]['frames']>0 and not failures and broker_alive)
        output=pathlib.Path(started['output'])
        decoding=validate_video(output)
        valid=valid and decoding['valid'] and decoding['decoded_frames']==finished[-1]['frames']
        validation.append(dict(**decoding,writer=finished[-1] if finished else None,failures=failures))
        if action=='stop':a.require(valid,'Capture finalization/decoding failed; use collect for failed own evidence: '+str(validation))
    s['recording']=dict(r,generation=generation) if action=='start' else None
    desktop.dump(s['registry'],dict(recording=s['recording']));desktop.dump(run/'session.json',s)
    if action=='start':input_control(run,p,'resume')
    return dict(time=time.time(),thread_id=a.own(),label=m['label'],action=action,generation=generation,ack=ack,capture_valid=valid,validation=validation)

def control(participant_file,action):
    p,g,m=a.participant(participant_file,'record-control');run=pathlib.Path(p['run']);request_id=str(uuid.uuid4())
    def log(event,**fields):
        with (run/'lifecycle.jsonl').open('a') as f:f.write(json.dumps(dict(time=time.time(),event=event,request_id=request_id,thread_id=a.own(),action=action,**fields))+'\n')
    log('requested')
    try:
        result=_control(p,g,m,action);log('completed',result=result);return result
    except BaseException as error:log('failed',reason=str(error));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('participant',type=pathlib.Path);parser.add_argument('action',choices=['start','stop','collect']);args=parser.parse_args()
    print(json.dumps(control(args.participant,args.action)),flush=True)
