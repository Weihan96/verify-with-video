"""Admit fixed background sessions while holding the shared preparation lease."""
import argparse,json,pathlib,uuid
import access as a
import desktop
p=argparse.ArgumentParser();p.add_argument('command',choices=['create','enroll','grant','ready','formal','closed','finish','status']);p.add_argument('--group',type=pathlib.Path);p.add_argument('--lease');p.add_argument('--run',type=pathlib.Path);p.add_argument('--member',action='append');p.add_argument('--label');args=p.parse_args()
if args.command=='create':
    desktop.check(args.lease);a.require(args.run and args.member,'Run and participants required')
    run=args.run.resolve();a.require(not run.exists(),'New experiment run required');run.mkdir(parents=True)
    members={}
    for value in args.member:
        label,thread=value.split('=',1);a.require(label in ('A','B') and label not in members and thread!=a.own(),'Distinct real participants required')
        members[label]=dict(label=label,thread_id=thread,run=str(run/label),state='invited')
    a.require(len(members)==2 and len({m['thread_id'] for m in members.values()})==2,'Exactly two distinct invited tasks required')
    g=dict(id=str(uuid.uuid4()),coordinator=a.own(),reservation=args.lease,run=str(run),phase='preparing',preparing=None,members=members)
    directory=a.shared()/'isolation-groups';directory.mkdir(exist_ok=True)
    path=directory/(g['id']+'.json');a.queue.atomic_json(path,g);a.audit(g,'created');print(json.dumps(dict(group=str(path),run=str(run))))
elif args.command=='status':print(json.dumps(a.read(args.group),indent=2))
else:
    def change(g):
        if args.command in ('grant','formal','finish'):
            a.require(g['coordinator']==a.own(),'Only coordinator controls experiment phases')
            if args.command=='grant':
                a.require(g['phase']=='preparing','Preparation already ended')
                previous=g['preparing'];a.require(previous is None or g['members'][previous]['state']=='ready','Previous preparation has not completed')
                a.require(args.label in g['members'],'Unknown label');g['preparing']=args.label
            elif args.command=='formal':
                a.admit(g)
            else:
                a.finish(g)
            a.audit(g,args.command,label=args.label);return dict(phase=g['phase'],preparing=g['preparing'])
        m=a.member(g,a.own());run=pathlib.Path(m['run'])
        if args.command=='enroll':
            a.require(m['state']=='invited','Participant already enrolled');run.mkdir()
            token=str(uuid.uuid4());m['token_hash']=a.digest(token);m['state']='enrolled'
            receipt=dict(group=str(args.group.resolve()),thread_id=a.own(),token=token,run=str(run),label=m['label'])
            a.queue.atomic_json(run/'participant.json',receipt)
        elif args.command=='ready':
            a.require(g['phase']=='preparing' and g['preparing']==m['label'] and m['state']=='enrolled','Preparation grant mismatch')
            session=json.loads((run/'session.json').read_text());state=json.loads((run/'state.json').read_text())
            a.require(session['thread_id']==a.own() and session['pid']==state['pid'],'Owned session/worker mismatch')
            desktop.load_launch(run/'launch.json',a.own());a.require(len(state['windows'])==1,'Exactly one Blender window required')
            full=json.loads((run/'native-fullscreen.json').read_text())
            a.require(full['fullscreen'] is True and full['pid']==session['pid'] and full['window']==session['window'] and full['thread_id']==a.own(),'Verified native fullscreen required')
            m.update(state='ready',session=str(run/'session.json'),pid=session['pid'],window=session['window'],identity=session['identity'],blender_window=state['windows'][0]['pointer'])
        else:
            if (run/'session.json').exists():
                session=json.loads((run/'session.json').read_text());a.require(session['thread_id']==a.own() and session.get('closed'),'Verified own app closure required')
                a.require(not json.loads(pathlib.Path(session['registry']).read_text()).get('recording'),'Own recorder still registered')
            elif (run/'launch.json').exists():
                receipt=json.loads((run/'launch.json').read_text());a.require(receipt['thread_id']==a.own() and receipt.get('closed'),'Unbound app has not been verified closed')
            else:a.require(g['phase']=='preparing','Missing formal launch receipt')
            m['state']='closed'
        a.audit(g,args.command,label=m['label']);return dict(label=m['label'],state=m['state'],participant=str(run/'participant.json'))
    print(json.dumps(a.mutate(args.group,change)))
