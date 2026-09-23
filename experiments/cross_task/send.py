"""Finite sender scoped to the actual caller and admitted Blender window."""
import argparse,json,pathlib,time,uuid
import access as a
import desktop
def send(participant_file,events,start_at=0):
    p,g,m=a.participant(participant_file,'simulate');run=pathlib.Path(p['run'])
    desktop.isolation_context(p['group'],'simulate');session=desktop.load_session(run/'session.json');receipt=desktop.load_launch(run/'launch.json',a.own())
    a.require(receipt['pid']==session['pid']==m['pid'] and session['window']==m['window'],'Target binding changed')
    a.recording(session);state=json.loads((run/'state.json').read_text())
    a.require(state['pid']==session['pid'] and state['thread_id']==a.own() and time.time()-state['time']<3,'Worker identity or heartbeat invalid')
    a.require(not state['drained'] and len(state['windows'])==1 and state['windows'][0]['pointer']==m['blender_window'],'Worker window not admitted')
    a.require(isinstance(events,list) and 0<len(events)<=1000,'Finite event batch required')
    for event in events:
        a.require(event.get('type') in ('A','C','V','RET','ESC','MOUSEMOVE','LEFTMOUSE','MIDDLEMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE') and event.get('value') in ('PRESS','RELEASE','NOTHING') and not event.get('oskey'),'Event outside scoped experiment')
        a.require(0<=event.get('delay',.12)<=10,'Invalid delay');event.setdefault('window',m['blender_window']);a.require(event['window']==m['blender_window'],'Foreign Blender window')
    a.require(sum(e.get('delay',.12) for e in events)<=120 and start_at<=time.time()+120,'Bounded scheduling required')
    command_id=str(uuid.uuid4());path=run/('command-'+str(time.time_ns())+'-'+command_id+'.json')
    desktop.dump(path,dict(id=command_id,thread_id=a.own(),token=p['token'],epoch=state['input_epoch'],start_at=start_at,events=events))
    return dict(command_id=command_id,thread_id=a.own(),event_count=len(events),start_at=start_at)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('participant',type=pathlib.Path);parser.add_argument('--events',required=True);parser.add_argument('--start-at',type=float,default=0);args=parser.parse_args()
    print(json.dumps(send(args.participant,json.loads(args.events),args.start_at)),flush=True)
