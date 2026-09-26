"""Coordinator finalization after every participant has stopped and closed itself."""
import argparse,json,pathlib,subprocess,time
import access as a
import desktop
p=argparse.ArgumentParser();p.add_argument('group',type=pathlib.Path);args=p.parse_args()
g=a.read(args.group)
a.require(g['coordinator']==a.own(),'Only coordinator may stop the shared recorder')
a.active(g)
a.require(all(m['state']=='closed' for m in g['members'].values()),'Participants must finish their own stop and close first')
r=json.loads((pathlib.Path(g['run'])/'capture/broker.json').read_text())
a.require(r['coordinator']==a.own() and pathlib.Path(r['group']).resolve()==args.group.resolve(),'Broker ownership mismatch')
try:
    running=desktop.identity(r['pid'])==r['identity']
except subprocess.CalledProcessError as error:
    if error.returncode!=1:raise
    running=False
rows=a.read_rows(r['log'])
if not running:
    a.require(any(x['event'] in ('capture_finished','capture_failed') for x in rows),'Broker exited or changed without finalization evidence')
    print(json.dumps(dict(stopped=True,already_finished=True,capture_valid=not any(x['event']=='capture_failed' for x in rows),log=r['log'])));raise SystemExit
pathlib.Path(r['stop']).touch()
for _ in range(200):
    rows=a.read_rows(r['log'])
    if any(x['event']=='capture_finished' for x in rows):
        print(json.dumps(dict(stopped=True,log=r['log'])));break
    if any(x['event']=='capture_failed' for x in rows):
        try:still_running=desktop.identity(r['pid'])==r['identity']
        except subprocess.CalledProcessError as error:
            if error.returncode!=1:raise
            still_running=False
        if not still_running:
            print(json.dumps(dict(stopped=True,capture_valid=False,log=r['log'])));break
    time.sleep(.1)
else:raise ValueError('Recorder shutdown timeout; retain broker evidence and report')
