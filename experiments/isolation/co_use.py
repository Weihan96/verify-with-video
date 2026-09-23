"""Finite active-system-mouse interference probe. Keep the shared lease.

Uses a task-owned foreground AppKit receiver and existing experimental event
sender. All paths, lease and scenario names are explicit; no global resets.
"""
import argparse,importlib.util,json,pathlib,subprocess,sys,time
p=argparse.ArgumentParser();p.add_argument('run',type=pathlib.Path);p.add_argument('--lease-id',required=True);p.add_argument('--scenario-module',type=pathlib.Path,required=True);p.add_argument('--desktop',type=pathlib.Path,required=True);p.add_argument('--case',choices=['drag','popup','debug-drag','debug-popup'],required=True);a=p.parse_args()
spec=importlib.util.spec_from_file_location('scenario',a.scenario_module);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
s.IMAGE_HEIGHT=803;s.POINTS=dict(text=(895,567),value=(866,591),enabled=(760,616),increment=(861,642),popup=(859,666))
a.run=a.run.resolve();events=[]
def note(kind,**extra):
 row=dict(time=time.time(),event=kind,case=a.case,**extra);events.append(row);print(json.dumps(row),flush=True)
def native(action):
 command=[sys.executable,str(a.desktop),'action','--session',str(a.run/'Foreground/session.json'),'--action',json.dumps(action)]
 r=subprocess.run(command,capture_output=True,text=True);note('native_action',action=action,code=r.returncode)
 (a.run/f'{a.case}-native-{len(events)}.log').write_text(r.stdout+r.stderr)
 if r.returncode:raise RuntimeError(r.stdout+r.stderr)
def send(k,es):
 s.send(a.run/k,a.lease_id,es,time.time()+.2)
 time.sleep(.4+sum(e.get('delay',.12) for e in es))
def latest():
 rows=[json.loads(l) for l in (a.run/'Foreground/foreground.jsonl').read_text().splitlines()]
 return next(r for r in reversed(rows) if r['event']=='sample')
try:
 if a.case.startswith('debug'):
  for k in 'AB':
   t=a.run/k/'marker-control.tmp';t.write_text(json.dumps({'action':'debug-on'}));t.replace(a.run/k/'marker-control.json')
  time.sleep(.5)
 native(dict(op='move',x=.25,y=.65));note('before',sample=latest())
 if 'drag' in a.case:
  send('A',[s.move(866,591),dict(type='LEFTMOUSE',value='PRESS',delay=.15),s.move(885,591,.3),s.move(905,591,.3),s.move(915,591,.3)])
 else:
  send('A',s.click('popup'))
 note('background_modal_open',sample=latest(),worker=json.loads((a.run/'A/state.json').read_text())['value'])
 # Independent worker B receives text while A remains in its modal interaction.
 send('B',s.text('independent-B'))
 native(dict(op='move',x=.75,y=.65));native(dict(op='text',text='x'))
 note('foreground_moved',sample=latest())
 if 'drag' in a.case:send('A',[dict(type='LEFTMOUSE',value='RELEASE',delay=.1)])
 else:send('A',s.key('ESC'))
 time.sleep(1)
 note('after_release',sample=latest())
finally:
 # Narrow cleanup only in the two simulated-input workers, regardless of focus.
 for k in 'AB':
  try:send(k,[dict(type='LEFTMOUSE',value='RELEASE',delay=.1)]+s.key('ESC'))
  except Exception as e:note('cleanup_failed',label=k,error=str(e))
 (a.run/(a.case+'-result.json')).write_text(json.dumps(events,indent=2))
