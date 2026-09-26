"""Serial preparation, executed by each real participant under its own grant."""
import argparse,hashlib,json,pathlib,shutil,subprocess,sys,time
import access as a
import scene_options
p=argparse.ArgumentParser();p.add_argument('group',type=pathlib.Path)
scene_options.add_arguments(p)
args=p.parse_args()
scene_options.validate(args)
root=a.ROOT;desktop=root/'scripts/desktop.py';group=root/'experiments/cross_task/group.py'
subprocess.run([sys.executable,str(group),'enroll','--group',str(args.group)],check=True)
g=a.read(args.group);m=a.member(g,a.own());run=pathlib.Path(m['run']);participant=json.loads((run/'participant.json').read_text());token=participant['token']
def call(command,*rest):
 result=subprocess.run([sys.executable,str(desktop),command,'--isolation-group',str(args.group),*map(str,rest)],capture_output=True,text=True)
 if result.returncode:raise RuntimeError(result.stdout+result.stderr)
 return json.loads(result.stdout)
shared=['--lease-id',token,'--work',run,'--launch-record',run/'launch.json']
worker=root/'experiments/cross_task/worker.py'
before_hash=hashlib.sha256(args.ifc.read_bytes()).hexdigest() if args.ifc else None
if args.ifc:
 receipt=call('launch',*shared,'--executable',args.blender.resolve(),'--bonsai-launcher',root/'scripts/bonsai_background_launcher.ts','--worktree',args.worktree.resolve(),'--',
              '--launcher',args.bonsai_launcher.resolve(),'--ifc',args.ifc.resolve(),'--worker',worker,'--run',run,'--label',m['label'],
              *(['--prepare-script',args.prepare_script.resolve()] if args.prepare_script else []),*(['--task-title',args.task_title] if args.task_title else []))
else:
 receipt=call('launch',*shared,'--executable',args.blender.resolve(),'--',*([str(args.blend.resolve())] if args.blend else []),'--no-window-focus','--window-fullscreen','--enable-event-simulate','--python',worker,'--','--probe-dir',run,'--probe-label',m['label'],*([] if args.fixture else ['--preserve-scene']))
deadline=time.monotonic()+args.prepare_timeout
while time.monotonic()<deadline:
 ready=scene_options.ifc_ready(pathlib.Path(receipt['receipt']['log']),args.ifc,receipt['pid'],before_hash) if args.ifc else True
 if ready and (run/'state.json').exists():
  if args.ifc:a.queue.atomic_json(run/'ifc-ready.json',ready)
  break
 time.sleep(.2)
else:raise RuntimeError('Worker preparation timed out; own launch receipt retained for cleanup')
windows=call('windows',*shared)['windows'];candidates=[w for w in windows if w['bounds']['width']>500 and w['bounds']['height']>400]
a.require(len(candidates)==1,'Ambiguous main window; inspect before binding')
call('bind',*shared,'--window',candidates[0]['window'],'--session',run/'session.json')
full=call('fullscreen','--session',run/'session.json')
restored=call('restore','--session',run/'session.json')
shutil.copyfile(restored['evidence'],run/'prepared.png')
(run/'prepared.png.json').write_text(json.dumps(restored,indent=2)+'\n')
print(json.dumps(dict(run=str(run),fullscreen=full,screenshot=str(run/'prepared.png'),next='Visually inspect own screenshot, measure points.json, then group ready. No automatic ready.'),indent=2))
