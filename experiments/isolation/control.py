"""One-shot control client for the bounded, prebound experimental broker."""
import argparse,json,pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
import desktop
p=argparse.ArgumentParser();p.add_argument('session',type=pathlib.Path);p.add_argument('action',choices=['start','stop']);a=p.parse_args()
s=desktop.load_session(a.session);r=json.loads(pathlib.Path(s['registry']).read_text())['recording']
desktop.require(r and r.get('experimental_broker'),'Experimental broker session required')
desktop.require(desktop.identity(r['pid'])==r['identity'],'Broker identity changed')
label=pathlib.Path(s['work']).name
desktop.require(any(t['label']==label and t['pid']==s['pid'] and t['window']==s['window'] for t in r['batch_targets']),'Target not prebound')
path=pathlib.Path(r['output'])/('desired-'+label+'.json')
previous=json.loads(path.read_text());generation=previous['generation']+1
desktop.dump(path,dict(generation=generation,active=a.action=='start'))
for _ in range(150):
    rows=[json.loads(line) for line in pathlib.Path(r['log']).read_text().splitlines() if line.startswith('{')]
    ack=next((row for row in reversed(rows) if row.get('label')==label and row.get('generation')==generation),None)
    if ack:
        if a.action=='stop' and ack['event']=='target_stopped':break
        if a.action=='start' and ack['event']=='capture_started' and any(row.get('event')=='first_frame' and row.get('output')==ack['output'] for row in rows):break
    time.sleep(.1)
else:raise RuntimeError('Broker did not acknowledge request; retain lease and inspect')
print(json.dumps(dict(action=a.action,label=label,generation=generation,ack=ack)),flush=True)
