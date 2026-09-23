"""Coordinator's native input probe; no refocus/retry masks a foreground failure."""
import argparse,json,pathlib,subprocess,sys,time
p=argparse.ArgumentParser();p.add_argument('run',type=pathlib.Path);p.add_argument('--desktop',type=pathlib.Path,required=True);p.add_argument('--seconds',type=float,default=600);args=p.parse_args()
run=args.run.resolve();begin=time.time();index=0
with (run/'foreground-input.jsonl').open('a') as log:
    while time.time()-begin<args.seconds and not (run/'stop-foreground-input').exists():
        for action in [dict(op='move',x=.25 if index%2==0 else .75,y=.65),dict(op='click',x=.5,y=.6),dict(op='text',text='p')]:
            action['require_focus']=True
            started=time.time();r=subprocess.run([sys.executable,str(args.desktop),'action','--session',str(run/'Foreground/session.json'),'--action',json.dumps(action)],capture_output=True,text=True)
            row=dict(start=started,end=time.time(),index=index,action=action,code=r.returncode)
            if r.returncode:row['error']=r.stdout+r.stderr
            log.write(json.dumps(row)+'\n');log.flush()
            if r.returncode:
                (run/'abort').write_text(json.dumps(row));raise RuntimeError('Foreground input failed; no activation retry: '+r.stdout+r.stderr)
        index+=1;time.sleep(1)
print(json.dumps(dict(finished=True,actions=index*3,duration=time.time()-begin)),flush=True)
