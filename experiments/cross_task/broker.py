"""Coordinator-owned finite recording service for explicitly admitted real tasks."""
import argparse,hashlib,json,pathlib,subprocess,time
import access as a
import desktop
p=argparse.ArgumentParser();p.add_argument('--group',type=pathlib.Path,required=True);p.add_argument('--foreground',type=pathlib.Path);p.add_argument('--seconds',type=float,default=1200);args=p.parse_args()
g=a.read(args.group);a.coordinator(g)
a.require(0<args.seconds<=1800 and g['phase']=='formal','Bounded formal experiment required')
sessions=[]
for label,m in g['members'].items():
    a.require(m['state']=='ready','Participant not ready');path=pathlib.Path(m['session']);s=json.loads(path.read_text())
    a.require(s['thread_id']==m['thread_id'] and s['pid']==m['pid'] and s['window']==m['window'] and s['identity']==m['identity'],'Member/session binding changed')
    receipt=desktop.load_launch(pathlib.Path(m['run'])/'launch.json',m['thread_id'])
    a.require(receipt['pid']==s['pid'] and receipt['identity']==s['identity'],'Launch receipt mismatch')
    a.require(pathlib.Path(s['registry'])==desktop.registry_path(s['thread_id'],s['pid'],s['identity']),'Registry path mismatch')
    a.require(not json.loads(pathlib.Path(s['registry']).read_text()).get('recording'),'Existing participant recorder')
    sessions.append((label,path,s))
if args.foreground:
    fore=desktop.load_session(args.foreground);a.require(not json.loads(pathlib.Path(fore['registry']).read_text()).get('recording'),'Existing foreground recorder');sessions.append(('Foreground',args.foreground,fore))
run=pathlib.Path(g['run'])/'capture';a.require(not run.exists(),'New capture directory required');run.mkdir()
root=a.ROOT;source=(root/'scripts/native.swift').read_text().split('@main struct Main')[0].replace('"event":"first_frame",','"event":"first_frame","output":writer.outputURL.path,')+pathlib.Path(__file__).with_suffix('.swift').read_text()
digest=hashlib.sha256(source.encode()+(root/'scripts/capture_guard.swift').read_bytes()).hexdigest()[:16];build=root/'.build';build.mkdir(exist_ok=True)
src=build/('cross-broker-'+digest+'.swift');binary=build/('cross-broker-'+digest);src.write_text(source)
if not binary.exists():subprocess.run(['swiftc','-parse-as-library','-import-objc-header',str(root/'scripts/native-process.h'),str(root/'scripts/capture_guard.swift'),str(src),'-o',str(binary)],check=True)
targets=[]
for label,path,s in sessions:
    targets.append(dict(label=label,pid=s['pid'],window=s['window'],executable=s['executable'],output=str(run/(label+'.mp4'))))
    desktop.dump(run/('desired-'+label+'.json'),dict(generation=0,active=label=='Foreground'))
stop=run/'stop';request=run/'request.json';desktop.dump(request,dict(targets=targets,control=str(run),stop=str(stop),seconds=args.seconds))
logfile=run/'capture.jsonl'
with logfile.open('wb',buffering=0) as log:proc=subprocess.Popen([str(binary),str(request)],stdout=log,stderr=log)
base=dict(pid=proc.pid,identity=desktop.identity(proc.pid),stop=str(stop),log=str(logfile),output=str(run),cross_task_broker=True,group=str(args.group.resolve()))
desktop.dump(run/'broker.json',dict(base,coordinator=a.own()))
for label,path,s in sessions:
    record=dict(base,label=label,generation=0)
    s['isolation_broker']=record;s['recording']=record if label=='Foreground' else None
    desktop.dump(s['registry'],dict(recording=s['recording']));desktop.dump(path,s)
for _ in range(150):
    rows=a.read_rows(logfile)
    ready=(any(x['event']=='first_frame' and x.get('output')==str(run/'Foreground.mp4') for x in rows) if args.foreground else all(any(x['event']=='target_stopped' and x.get('label')==label and x.get('generation')==0 for x in rows) for label in g['members']))
    if ready:break
    if proc.poll() is not None:raise RuntimeError(logfile.read_text())
    time.sleep(.1)
else:stop.touch();raise RuntimeError('Broker readiness timeout; collect it before continuing')
print(json.dumps(dict(ready=True,pid=proc.pid,log=str(logfile))),flush=True)
code=proc.wait();a.require(code==0,'Broker failed; retain failure log: '+logfile.read_text());print(json.dumps(dict(finished=True,log=str(logfile))),flush=True)
