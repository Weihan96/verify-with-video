"""Explicit child capabilities under one existing global desktop reservation.

This is cooperative authorization, not an OS security boundary. It never changes
the queue owner, caller task identity, queue directory or global installation.
"""
import hashlib,json,os,pathlib,sys,time,uuid
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import desktop_queue as queue

def require(ok,message):
    if not ok:raise ValueError(message)

def shared():return pathlib.Path(os.environ.get('CODEX_HOME',str(pathlib.Path.home()/'.codex')))/'state/computer-use'
def own():
    value=os.environ.get('CODEX_THREAD_ID');require(bool(value),'Actual CODEX_THREAD_ID required');return value
def read(path):
    path=pathlib.Path(path).resolve()
    require(path.parent==(shared()/'isolation-groups').resolve(),'Group must be subordinate to the existing shared queue')
    return json.loads(path.read_text())
def reservation(group):
    with queue.locked(shared()):q,_=queue.load(shared())
    c=q['current']
    require(c and c['thread_id']==group['coordinator'] and c['lease_id']==group['reservation'],'Coordinator no longer holds the global reservation')
    require(group['phase']!='closed','Experiment group closed')
def member(group,thread):
    matches=[m for m in group['members'].values() if m['thread_id']==thread]
    require(len(matches)==1,'Actual task is not an invited participant');return matches[0]
def digest(token):return hashlib.sha256(token.encode()).hexdigest()
def authorize(path,token,thread,operation):
    require(thread==own(),'Caller task differs from actual environment')
    g=read(path);reservation(g);m=member(g,thread)
    require(token and m.get('token_hash')==digest(token),'Participant capability mismatch')
    require(m['state']!='closed','Participant already closed')
    if operation in ('launch','windows','bind','restore','snapshot','fullscreen'):
        require(g['phase']=='preparing' and g['preparing']==m['label'],'Exclusive preparation grant required')
    elif operation in ('simulate','record-control','record-read'):
        require(g['phase']=='formal' and m['state']=='ready','Participant not admitted to formal operation')
    elif operation=='close':
        require(m['state'] in ('enrolled','ready'),'Invalid cleanup state')
    else:raise ValueError('System-level operation is not granted to parallel participants: '+operation)
    return g,m
def participant(path,operation):
    p=json.loads(pathlib.Path(path).read_text());require(p['thread_id']==own(),'Participant file belongs to another task')
    g,m=authorize(p['group'],p['token'],own(),operation)
    require(pathlib.Path(p['run']).resolve()==pathlib.Path(m['run']).resolve(),'Participant run mismatch')
    return p,g,m
def recording(session):
    r=json.loads(pathlib.Path(session['registry']).read_text()).get('recording')
    require(r and r.get('cross_task_broker'),'Own target has no active recorder')
    import desktop
    require(desktop.identity(r['pid'])==r['identity'],'Broker exited or changed identity')
    rows=read_rows(r['log']);label=r['label']
    require(not any(x['event'] in ('capture_finished','capture_failed') for x in rows),'Broker ended')
    relevant=[x for x in rows if x.get('label')==label and x['event'] in ('capture_started','target_stopped','target_failed','target_finalize_failed')]
    require(relevant and relevant[-1]['event']=='capture_started','Own target recorder stopped or failed')
    require(relevant[-1].get('generation')==r['generation'],'Recorder generation changed')
    require(any(x['event']=='first_frame' and x.get('output')==relevant[-1]['output'] for x in rows),'Own recorder not ready')
    return r,relevant[-1]
def read_rows(path):
    data=pathlib.Path(path).read_text();lines=data.splitlines()
    if data and not data.endswith('\n'):lines=lines[:-1]
    return [json.loads(s) for s in lines if s.startswith('{')]
def audit(group,event,**fields):
    with (pathlib.Path(group['run'])/'admission.jsonl').open('a') as f:f.write(json.dumps(dict(time=time.time(),event=event,actor=own(),**fields))+'\n')
def mutate(path,fn):
    path=pathlib.Path(path)
    with queue.locked(path.parent):
        g=read(path);reservation(g);result=fn(g);queue.atomic_json(path,g);return result
