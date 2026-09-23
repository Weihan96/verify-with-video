#!/usr/bin/env python3
"""Native macOS desktop evidence CLI. Queue membership is coordination, not an OS lock."""
import argparse, hashlib, json, os, pathlib, subprocess, sys, time, uuid
import desktop_queue as queue

ROOT = pathlib.Path(__file__).resolve().parent
ISOLATION_CONTEXT = None

def isolation_context(path, operation):
    """Opt-in experimental child capability; default queue checks are unchanged."""
    global ISOLATION_CONTEXT
    sys.path.insert(0,str(ROOT.parent/'experiments/cross_task'))
    import access
    ISOLATION_CONTEXT = (pathlib.Path(path), operation, access)

def require(ok, message):
    if not ok:
        raise ValueError(message)

def dump(path, value):
    queue.atomic_json(pathlib.Path(path), value)

def identity(pid):
    r = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart=', '-o', 'comm='], text=True, capture_output=True, check=True)
    require(bool(r.stdout.strip()), 'Process not alive')
    return r.stdout.strip()

def shared_state():
    return pathlib.Path(os.environ.get('CODEX_HOME', str(pathlib.Path.home()/'.codex')))/'state'/'computer-use'

def check(lease):
    own = os.environ.get('CODEX_THREAD_ID')
    require(own, 'CODEX_THREAD_ID required; use the actual task environment')
    if ISOLATION_CONTEXT:
        path,operation,access=ISOLATION_CONTEXT
        access.authorize(path,lease,own,operation)
    else:
        queue.execute(shared_state(), 'check', own, lease)
    return own

def binary(role="control"):
    source = ROOT/'native.swift'
    guard_source=ROOT/'capture_guard.swift'
    header=ROOT/'native-process.h'
    digest = hashlib.sha256(source.read_bytes()+guard_source.read_bytes()+header.read_bytes()).hexdigest()[:16]
    cache = ROOT.parent/'.build'
    cache.mkdir(exist_ok=True)
    out = cache/f'native-{role}-{digest}'
    if not out.exists():
        tmp = cache/f'{out.name}-{uuid.uuid4()}'
        subprocess.run(['swiftc','-parse-as-library','-import-objc-header',str(header),str(guard_source),str(source),'-o',str(tmp)], check=True)
        os.replace(tmp, out)
    return out

def native(request, directory):
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    p = directory/f'request-{uuid.uuid4()}.json'
    dump(p, request)
    r = subprocess.run([str(binary()), str(p)], text=True, capture_output=True)
    rows = [json.loads(l) for l in r.stdout.splitlines() if l.startswith('{')]
    require(r.returncode == 0, r.stdout + r.stderr)
    require(rows, 'Native tool returned no result')
    return rows[-1]

def load_session(path, lease=True):
    s = json.loads(pathlib.Path(path).read_text())
    require(s['thread_id'] == os.environ.get('CODEX_THREAD_ID'), 'Session belongs to another task')
    if lease:
        check(s['lease_id'])
    require(identity(s['pid']) == s['identity'], 'PID identity changed; do not input/close')
    return s

def target(s, command, **kwargs):
    return dict(command=command, pid=s['pid'], window=s['window'], executable=s['executable'], **kwargs)

def select_window(rows, pid, window, executable):
    matches = [w for w in rows if w['pid']==pid and w['window']==window and w['executable']==executable]
    require(len(matches)==1, 'Exact PID/window/executable match required')
    return matches[0]

def registry_path(thread_id, pid, process_identity):
    directory = pathlib.Path(os.environ.get('CODEX_HOME',str(pathlib.Path.home()/'.codex')))/'state'/'native-desktop'/thread_id
    return directory/('process-'+str(pid)+'-'+hashlib.sha256(process_identity.encode()).hexdigest()[:12]+'.json')


def process_executable(pid):
    value = subprocess.check_output(['ps','-p',str(pid),'-o','comm='],text=True).strip()
    return str(pathlib.Path(value).resolve())


def load_launch(path, own):
    record = json.loads(pathlib.Path(path).read_text())
    require(isinstance(record,dict), 'Invalid launch record')
    require(record.get('thread_id')==own, 'Launch record belongs to another task')
    require(type(record.get('pid')) is int and record['pid']>1 and record.get('identity') and record.get('executable'), 'Incomplete launch record; no process may be inferred')
    require(identity(record['pid'])==record['identity'], 'Launch process identity changed')
    require(process_executable(record['pid'])==record['executable'], 'Launch executable changed')
    if 'receipt' in record:
        receipt=record['receipt']
        require(isinstance(receipt,dict), 'Invalid launcher receipt')
        require(receipt.get('status')=='started' and receipt.get('pid')==record['pid'], 'Not a new-process launcher receipt')
        owner=receipt.get('owner')
        require(isinstance(owner,dict), 'Invalid launcher owner')
        basis=owner.get('basis')
        require(basis in ('codex_thread','explicit_task'), 'Launcher owner must identify this task')
        owner_id=hashlib.sha256(f'{basis}:{own}'.encode()).hexdigest()[:20]
        marker=owner.get('marker')
        require(owner.get('id')==owner_id and marker=='--codex-task-owner='+owner_id, 'Launcher owner belongs to another task')
        command=subprocess.check_output(['ps','-p',str(record['pid']),'-o','command='],text=True)
        require(marker and marker in command.split(), 'Launcher owner marker no longer matches')
    return record


def close_owned(record, registry, record_path):
    # No focus, window selection, or fabricated session is needed for termination.
    if registry.exists():
        require(not json.loads(registry.read_text()).get('recording'), 'Stop recorder before closing')
    require(identity(record['pid'])==record['identity'], 'Launch identity changed before signal')
    require(process_executable(record['pid'])==record['executable'], 'Launch executable changed before signal')
    os.kill(record['pid'],15)
    identity_changed=False
    for _ in range(100):
        try:
            current=identity(record['pid'])
        except subprocess.CalledProcessError as error:
            require(error.returncode==1, 'Cannot verify process exit; retain lease')
            record['closed']=time.time();dump(record_path,record)
            return {'closed':record['pid'],'identity':record['identity'],'verified_exited':True,'saved_before_close':'caller must verify persistence or authorize discard before close'}
        # ps can briefly report a zombie name during normal termination. Poll only;
        # never signal again, including if a new process has reused this PID.
        identity_changed = identity_changed or current!=record['identity']
        time.sleep(.1)
    raise ValueError(('PID identity changed after signal; ' if identity_changed else 'Owned process did not exit; ')+'no further signal or force-kill; retain lease for inspection')


def recording_health(recording):
    if not recording:
        return
    text = pathlib.Path(recording['log']).read_text()
    require('"error"' not in text and '"event":"capture_finished"' not in text,
            'Recording ended or failed; stop/collect it before further input: '+text)
    require(identity(recording['pid']) == recording['identity'], 'Recorder exited or identity changed')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['build','windows','launch','bind','snapshot','restore','action','record','stop','close','fullscreen'])
    p.add_argument('--lease-id');p.add_argument('--session', type=pathlib.Path)
    p.add_argument('--work', type=pathlib.Path);p.add_argument('--executable')
    p.add_argument('--pid',type=int);p.add_argument('--window',type=int)
    p.add_argument('--after-session',type=pathlib.Path,help='Evidence target after an expected dialog/window closure')
    p.add_argument('--action', help='JSON: op, normalized x/y, macOS code, modifiers, text, delta')
    p.add_argument('--output',type=pathlib.Path);p.add_argument('--display',type=int)
    p.add_argument('--seconds',type=float,default=120);p.add_argument('--scale',type=int,choices=[1,2],default=2)
    p.add_argument('--launch-record',type=pathlib.Path)
    p.add_argument('--bonsai-launcher',type=pathlib.Path)
    p.add_argument('--worktree',type=pathlib.Path)
    p.add_argument('--isolation-group',type=pathlib.Path,help='Scoped participant authorization after serialized preparation')
    a, extras = p.parse_known_args()
    if a.isolation_group:
        require(a.command not in ('action','record','stop'),'Parallel participants must use scoped experiment clients')
        isolation_context(a.isolation_group,a.command)
    require(a.command=='launch' or not extras, 'Unexpected arguments: '+str(extras))
    a.arguments = extras
    if a.command == 'build':
        return {'binary':str(binary())}
    if a.command == 'close' and not a.session:
        own=check(a.lease_id)
        require(a.launch_record, '--launch-record required when closing without a session')
        if ISOLATION_CONTEXT:
            path,op,access=ISOLATION_CONTEXT
            group,member=access.authorize(path,a.lease_id,own,op)
            run=pathlib.Path(member['run'])
            require(group['phase']=='preparing' and member['state']=='enrolled' and not (run/'session.json').exists(),'Unbound cleanup only during preparation')
            require(a.launch_record.resolve()==run/'launch.json','Use own registered launch receipt')
        record=load_launch(a.launch_record,own)
        return close_owned(record,registry_path(own,record['pid'],record['identity']),a.launch_record)
    if a.command in ('windows','launch','bind'):
        own = check(a.lease_id)
        require(a.work, '--work required for launch/bind/windows')
        if ISOLATION_CONTEXT:
            path,op,access=ISOLATION_CONTEXT
            _,member=access.authorize(path,a.lease_id,own,op)
            require(a.work.resolve()==pathlib.Path(member['run']).resolve(),'Preparation outside own registered run')
            require(a.launch_record and a.launch_record.resolve()==a.work.resolve()/'launch.json','Use own registered launch receipt')
        a.work = a.work.resolve();a.work.mkdir(parents=True,exist_ok=True)
        if a.command == 'launch':
            require(a.executable and a.launch_record, '--executable and --launch-record required')
            require(not a.launch_record.exists(), 'Launch record exists; use a new path')
            a.launch_record.parent.mkdir(parents=True, exist_ok=True)
            dump(a.launch_record, dict(thread_id=own,status='launching'))
            executable = str(pathlib.Path(a.executable).resolve(strict=True))
            args = a.arguments[1:] if a.arguments[:1]==['--'] else a.arguments
            if a.bonsai_launcher:
                require(a.worktree, '--worktree required with --bonsai-launcher')
                require(not os.environ.get('PROJECT_CONTROL_TASK_ID') or os.environ['PROJECT_CONTROL_TASK_ID'].strip()==own, 'Launcher task override conflicts with current task')
                require(not any(arg=='--task-id' or arg.startswith('--task-id=') for arg in args), 'Do not override current task identity in launcher arguments')
                receipt = json.loads(subprocess.check_output(['bun',str(a.bonsai_launcher),'--worktree',str(a.worktree.resolve()),'--blender',executable,*args],text=True))
                require(receipt['status']=='started','Launcher returned existing process; inspect and attach without close ownership')
                pid=receipt['pid']
                data = dict(thread_id=own,pid=pid,identity=identity(pid),executable=executable,receipt=receipt,created=time.time())
                try:
                    dump(a.launch_record,data)
                except BaseException:
                    # Receipt is issued by the task-aware launcher, never infer ownership by app name.
                    if identity(pid)==data['identity']:
                        os.kill(pid,15)
                    raise
            else:
                log = open(a.work/'application.log','ab',buffering=0)
                process = subprocess.Popen([executable,*args], stdout=log,stderr=log,start_new_session=True)
                log.close()
                try:
                    time.sleep(.25)
                    data = dict(thread_id=own,pid=process.pid,identity=identity(process.pid),executable=executable,arguments=args,created=time.time())
                    dump(a.launch_record,data)
                except BaseException:
                    process.terminate()
                    process.wait(timeout=10)
                    raise
            return data
        owned = load_launch(a.launch_record,own) if a.launch_record else None
        if owned:
            require(a.pid is None or a.pid==owned['pid'], 'Requested PID conflicts with launch record')
            require(a.executable is None or str(pathlib.Path(a.executable).resolve())==owned['executable'], 'Requested executable conflicts with launch record')
            a.pid=owned['pid'];a.executable=owned['executable']
        if a.command=='bind':
            require(a.session and not a.session.exists(), 'New --session path required')
            require(a.pid and a.window and a.executable, 'bind requires exact window and PID/executable or launch record')
        query={'command':'windows'}
        if a.pid is not None:
            require(a.pid>1 and a.executable, '--pid requires the exact --executable (or use --launch-record)')
            executable=str(pathlib.Path(a.executable).resolve(strict=True))
            process_identity=identity(a.pid)
            require(process_executable(a.pid)==executable,'Requested process executable does not match')
            query.update(pid=a.pid,executable=executable,include_hidden=True)
        else:
            require(not a.executable, '--executable requires --pid')
        rows=native(query,a.work)
        if a.pid is not None:
            require(identity(a.pid)==process_identity,'Process identity changed during window discovery')
            rows['identity']=process_identity
        if a.command=='windows':
            return rows
        w=select_window(rows['windows'],a.pid,a.window,executable)
        registry=registry_path(own,a.pid,process_identity)
        registry.parent.mkdir(parents=True,exist_ok=True)
        if not registry.exists():
            dump(registry,dict(recording=None))
        s = dict(registry=str(registry),thread_id=own,lease_id=a.lease_id,pid=a.pid,window=a.window,executable=executable,identity=process_identity,work=str(a.work),launch=owned,recording=None)
        dump(a.session,s)
        return dict(session=str(a.session),target=w,owned=owned is not None)
    require(a.session, '--session required')
    # Stopping one's existing recorder remains possible after lease loss.
    s = load_session(a.session, lease=a.command!='stop') if a.command!='stop' else json.loads(a.session.read_text())
    require(s['thread_id']==os.environ.get('CODEX_THREAD_ID'),'Wrong task')
    work = pathlib.Path(s['work'])
    registry = pathlib.Path(s['registry'])
    process_state = json.loads(registry.read_text())
    s['recording'] = process_state['recording']
    if a.command == 'fullscreen':
        require(ISOLATION_CONTEXT,'Fullscreen setup is experimental and requires an exclusive preparation grant')
        require(not s.get('recording'),'Fullscreen preparation cannot change a recording window')
        result=native(target(s,'fullscreen'),work)
        dump(work/'native-fullscreen.json',dict(result,thread_id=s['thread_id'],time=time.time()))
        return result
    if a.command == 'restore':
        recording_health(s.get('recording'))
        key=f'{time.time_ns()}-restored'
        result=native(target(s,'restore'),work)
        evidence=work/f'{key}.png'
        result['snapshot']=native(target(s,'snapshot',output=str(evidence),scale=1),work)
        result['evidence']=str(evidence)
        dump(work/f'{key}.json',result)
        return result
    if a.command == 'snapshot':
        require(a.output and not a.output.exists(),'New --output required')
        result = native(target(s,'snapshot',output=str(a.output.resolve()),scale=a.scale,**({'display':a.display} if a.display else {})),work)
        dump(str(a.output)+'.json',result)
        return result
    if a.command == 'action':
        action = json.loads(a.action)
        after_target = load_session(a.after_session) if a.after_session else s
        require(after_target['pid']==s['pid'] and after_target['identity']==s['identity'], 'After target must belong to the same process')
        key = f'{time.time_ns()}-{uuid.uuid4().hex[:6]}'
        before,after = work/f'{key}-before.png',work/f'{key}-after.png'
        entry = dict(start=time.time(),action=action,before=str(before),after=str(after),ui_verified=False)
        try:
            recording_health(s.get('recording'))
            native(target(s,'snapshot',output=str(before),scale=1),work)
            entry['sent_at'] = time.time()
            entry['result'] = native(target(s,'action',action=action),work)
            native(target(after_target,'snapshot',output=str(after),scale=1),work)
            recording_health(s.get('recording'))
        except BaseException as error:
            entry['error'] = str(error)
            raise
        finally:
            entry['end'] = time.time()
            with (work/'actions.jsonl').open('a') as f:
                f.write(json.dumps(entry,ensure_ascii=False)+'\n')
        return entry
    if a.command == 'record':
        require(not s.get('recording'),'Recorder already registered; stop/collect it first')
        require(a.output and not a.output.exists(),'New --output required')
        require(0<a.seconds<=3600,'seconds must be in (0,3600]')
        stem=work/f'record-{uuid.uuid4()}'
        request=target(s,'record',output=str(a.output.resolve()),stop=str(stem)+'.stop',seconds=a.seconds,scale=a.scale,**({'display':a.display} if a.display else {}))
        dump(str(stem)+'.json',request)
        log=open(str(stem)+'.jsonl','wb',buffering=0)
        proc=subprocess.Popen([str(binary('recorder')),str(stem)+'.json'],stdout=log,stderr=log,start_new_session=True);log.close()
        try:
            s['recording']=dict(pid=proc.pid,identity=identity(proc.pid),stop=request['stop'],log=str(stem)+'.jsonl',output=request['output'])
            dump(registry,dict(recording=s['recording']))
            dump(a.session,s)
        except BaseException:
            pathlib.Path(request['stop']).touch()
            proc.wait(timeout=15)
            raise
        for _ in range(100):
            text=pathlib.Path(s['recording']['log']).read_text()
            if '"event":"first_frame"' in text:
                print(json.dumps(dict(recording=s['recording'],first_frame=True)),flush=True)
                code=proc.wait()
                text=pathlib.Path(s['recording']['log']).read_text()
                require(code==0 and '"event":"capture_finished"' in text,'Recorder failed: '+text)
                return dict(finished=True,recording=s['recording'])
            if proc.poll() is not None:
                raise ValueError('Recorder exited; collect with stop: '+text)
            time.sleep(.1)
        pathlib.Path(request['stop']).touch()
        raise ValueError('No first frame; stop requested, use stop to collect evidence')
    if a.command == 'stop':
        rec=s.get('recording');require(rec,'No recorder registered')
        if rec.get('cross_task_broker'):
            sys.path.insert(0,str(ROOT.parent/'experiments/cross_task'))
            import access
            group=access.read(rec['group'])
            require(group['coordinator']==os.environ.get('CODEX_THREAD_ID'),'Shared broker stop is coordinator-only; use scoped control stop/collect')
        pathlib.Path(rec['stop']).touch()
        for _ in range(150):
            text=pathlib.Path(rec['log']).read_text()
            if '"event":"capture_finished"' in text:
                s['recording']=None;dump(registry,dict(recording=None));dump(a.session,s)
                return dict(stopped=True,recording=rec,log=text)
            try:
                alive=identity(rec['pid'])==rec['identity']
            except subprocess.CalledProcessError:
                alive=False
            if not alive:
                s['recording']=None;dump(registry,dict(recording=None));dump(a.session,s)
                raise ValueError('Recorder ended without successful finalization: '+text)
            time.sleep(.1)
        raise ValueError('Recorder has not stopped; keep queue lease and inspect log')
    if a.command == 'close':
        require(s.get('launch'), 'Refuse to close attached/user-owned application')
        require(not s.get('recording'), 'Stop recorder before closing')
        record=s['launch']
        require(record['pid']==s['pid'] and record['identity']==s['identity'] and record['thread_id']==s['thread_id'], 'Session launch ownership mismatch')
        if ISOLATION_CONTEXT:
            state=json.loads((work/'state.json').read_text())
            require(state.get('drained') and state.get('pending')==0 and not state.get('held'),'Drain simulated input before closing')
        else:
            native(target(s,'release-input'),work)
        # Persist closure on the session, retaining the original launch receipt.
        result=close_owned(record,registry,work/f'closed-{s["pid"]}.json')
        s['closed']=record['closed'];dump(a.session,s)
        return result

if __name__=='__main__':
    try:
        print(json.dumps(main(),ensure_ascii=False,indent=2))
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as error:
        print(json.dumps({'error':str(error),'action':'Stop and inspect; do not retry input blindly'},ensure_ascii=False),file=sys.stderr)
        sys.exit(1)
