"""Finite recorder guard, per-process clipboard and actual transform checks."""
import argparse,json,pathlib,subprocess,sys,time
import scenarios as s
p=argparse.ArgumentParser();p.add_argument('run',type=pathlib.Path);p.add_argument('--lease-id',required=True);a=p.parse_args();r=a.run.resolve()
s.IMAGE_HEIGHT=803;s.POINTS=dict(text=(895,567),value=(866,591),enabled=(760,616),increment=(861,642),popup=(859,666))
here=pathlib.Path(__file__).resolve().parent;result=[]
def note(event,**kw):
 row=dict(time=time.time(),event=event,**kw);result.append(row);print(json.dumps(row),flush=True);(r/'final-checks.json').write_text(json.dumps(result,indent=2))
def send(k,es):s.send(r/k,a.lease_id,es,time.time()+.2);time.sleep(.5+sum(e.get('delay',.12) for e in es))
def control(action):
 out=subprocess.check_output([sys.executable,str(here/'control.py'),str(r/'A/session.json'),action],text=True);note('control',data=json.loads(out))
def state(k):return json.loads((r/k/'state.json').read_text())
note('begin');control('stop')
blocked=subprocess.run([sys.executable,str(here/'send.py'),str(r/'A'),'--lease-id',a.lease_id,'--events',json.dumps(s.key('ESC'))],capture_output=True,text=True)
note('input_without_recorder',code=blocked.returncode,message=blocked.stderr)
assert blocked.returncode and 'Target recorder is not active' in blocked.stderr
send('B',s.text('B-guard-live'));assert state('B')['text']=='B-guard-live';note('other_target_survived',text=state('B')['text'])
control('start')
for k in 'BA':
 send(k,s.text(k+'-local-clip'))
 send(k,s.click('text')+s.key('A',ctrl=True)+s.key('C',ctrl=True)+s.key('RET'))
for k in 'AB':
 send(k,s.text('replace-me'))
 send(k,s.click('text')+s.key('A',ctrl=True)+s.key('V',ctrl=True)+s.key('RET'))
 note('clipboard_readback',label=k,actual=state(k)['text']);assert state(k)['text']==k+'-local-clip'
# Visually located Blender Transform > Location X, expressed in current mm units.
es=[s.move(850,143)]+s.key('LEFTMOUSE')+s.key('A',ctrl=True)
for c in '1000':es += [dict(type='A',value='PRESS',unicode=c,delay=.1),dict(type='A',value='RELEASE',delay=.05)]
send('A',es+s.key('RET'));note('transform_entered',label='A',location_x_mm=1000)
send('B',[s.move(620,360),dict(type='MIDDLEMOUSE',value='PRESS',delay=.1),s.move(655,390,.3),s.move(690,420,.3),dict(type='MIDDLEMOUSE',value='RELEASE',delay=.1)]);note('orbit_completed',label='B')
for k in 'AB':send(k,s.key('S',oskey=True));note('save_requested',label=k)
time.sleep(2);note('end')
