"""Coordinator finalization after every participant has stopped and closed itself."""
import argparse,json,pathlib,subprocess,time
import access as a
import desktop
p=argparse.ArgumentParser();p.add_argument('group',type=pathlib.Path);args=p.parse_args()
g=a.read(args.group)
a.require(g['coordinator']==a.own(),'Only coordinator may stop the shared recorder')
desktop.check(g['reservation'])
a.require(all(m['state']=='closed' for m in g['members'].values()),'Participants must finish their own stop and close first')
r=json.loads((pathlib.Path(g['run'])/'capture/broker.json').read_text())
a.require(r['coordinator']==a.own() and pathlib.Path(r['group']).resolve()==args.group.resolve(),'Broker ownership mismatch')
try:
    running=desktop.identity(r['pid'])==r['identity']
except subprocess.CalledProcessError as error:
    if error.returncode!=1:raise
    running=False
rows=a.read_rows(r['log'])
a.require(not any(x['event']=='capture_failed' for x in rows),'Recorder failed; retain raw evidence and inspect')
if not running:
    a.require(any(x['event']=='capture_finished' for x in rows),'Broker exited or changed without successful finalization')
    print(json.dumps(dict(stopped=True,already_finished=True,log=r['log'])));raise SystemExit
pathlib.Path(r['stop']).touch()
for _ in range(200):
    rows=a.read_rows(r['log'])
    if any(x['event']=='capture_finished' for x in rows):
        print(json.dumps(dict(stopped=True,log=r['log'])));break
    a.require(not any(x['event']=='capture_failed' for x in rows),'Recorder failed; retain raw evidence and inspect')
    time.sleep(.1)
else:raise ValueError('Recorder shutdown timeout; retain reservation')
