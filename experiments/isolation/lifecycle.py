"""Record four overlapping input/capture lifecycle cases in owned full-screen windows.

Coordinates are for the visually inspected 1280 x 803 Retina fixture only.
The foreground native receiver substitutes for a human for repeatability.
"""
import argparse,json,pathlib,subprocess,sys,time
import scenarios as s
p=argparse.ArgumentParser();p.add_argument('run',type=pathlib.Path);p.add_argument('--lease-id',required=True);a=p.parse_args();a.run=a.run.resolve()
ROOT=pathlib.Path(__file__).resolve().parents[2]
s.IMAGE_HEIGHT=803;s.POINTS=dict(text=(895,567),value=(866,591),enabled=(760,616),increment=(861,642),popup=(859,666))
results=[]
def state(k):return json.loads((a.run/k/'state.json').read_text())
def sample():return next(json.loads(l) for l in reversed((a.run/'Foreground/foreground.jsonl').read_text().splitlines()) if json.loads(l)['event']=='sample')
def native(action):
 z=subprocess.run([sys.executable,str(ROOT/'scripts/desktop.py'),'action','--session',str(a.run/'Foreground/session.json'),'--action',json.dumps(action)],capture_output=True,text=True)
 if z.returncode:raise RuntimeError(z.stdout+z.stderr)
for k in 'AB':
 t=a.run/k/'marker-control.tmp';t.write_text(json.dumps(dict(action='enable')));t.replace(a.run/k/'marker-control.json')
time.sleep(.5)
for idx,(changed,action,other) in enumerate([('A','stop','B'),('A','start','B'),('B','stop','A'),('B','start','A')]):
 text=f'{other}-{idx+1}-live';es=s.text(text)
 before=sample();start=time.time();s.send(a.run/other,a.lease_id,es,start+.3)
 # This separate one-shot client exits without terminating the capture broker.
 client=subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('control.py')),str(a.run/changed/'session.json'),action],capture_output=True,text=True)
 if client.returncode:raise RuntimeError(client.stdout+client.stderr)
 native(dict(op='move',x=.25 if idx%2==0 else .75,y=.65));native(dict(op='text',text=str(idx+1)))
 time.sleep(sum(e.get('delay',.12) for e in es)+1)
 after=sample();current=state(other)
 row=dict(start=start,end=time.time(),changed=changed,action=action,operating=other,expected=text,actual=current['text'],before=before,after=after,ack=json.loads(client.stdout))
 results.append(row);print(json.dumps(row),flush=True)
 (a.run/'lifecycle-result.json').write_text(json.dumps(results,indent=2))
 assert current['text']==text,row
 assert before['front_pid']==after['front_pid']==json.loads((a.run/'Foreground/launch.json').read_text())['pid'],row
 assert before['clipboard_revision']==after['clipboard_revision'] and before['flags']==after['flags'],row
