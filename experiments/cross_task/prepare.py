"""Serial preparation, executed by each real participant under its own grant."""
import argparse,json,pathlib,shutil,subprocess,sys,time
import access as a
p=argparse.ArgumentParser();p.add_argument('group',type=pathlib.Path)
p.add_argument('--blender',type=pathlib.Path,default=pathlib.Path('/Applications/Blender.app/Contents/MacOS/Blender'))
mode=p.add_mutually_exclusive_group();mode.add_argument('--blend',type=pathlib.Path);mode.add_argument('--fixture',action='store_true')
args=p.parse_args()
a.require(args.blender.is_file(),'Blender executable missing')
if args.blend:a.require(args.blend.is_file(),'Blend workfile missing')
root=a.ROOT;desktop=root/'scripts/desktop.py';group=root/'experiments/cross_task/group.py'
subprocess.run([sys.executable,str(group),'enroll','--group',str(args.group)],check=True)
g=a.read(args.group);m=a.member(g,a.own());run=pathlib.Path(m['run']);participant=json.loads((run/'participant.json').read_text());token=participant['token']
def call(command,*rest):
 result=subprocess.run([sys.executable,str(desktop),command,'--isolation-group',str(args.group),*map(str,rest)],capture_output=True,text=True)
 if result.returncode:raise RuntimeError(result.stdout+result.stderr)
 return json.loads(result.stdout)
shared=['--lease-id',token,'--work',run,'--launch-record',run/'launch.json']
call('launch',*shared,'--executable',args.blender.resolve(),'--',*([str(args.blend.resolve())] if args.blend else []),'--no-window-focus','--window-fullscreen','--enable-event-simulate','--python',root/'experiments/cross_task/worker.py','--','--probe-dir',run,'--probe-label',m['label'],*([] if args.fixture else ['--preserve-scene']))
for _ in range(100):
 if (run/'state.json').exists():break
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
