"""Experimental shared-process capture for a finite set of owned windows.

Retains the normal shared lease and per-target identity guard. A single process remains alive while prebound targets independently stop/restart.
Experimental clients share one actual task lease; this is not a multi-task API.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import desktop

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('run', type=pathlib.Path)
p.add_argument('--session', action='append', type=pathlib.Path, required=True)
p.add_argument('--seconds', type=float, default=120)
a = p.parse_args()
desktop.require(0 < a.seconds <= 600, 'Bounded experiment required')
sessions = [desktop.load_session(path) for path in a.session]
desktop.require(len({s['pid'] for s in sessions}) == len(sessions), 'Use distinct owned processes')
for s in sessions:
    desktop.require(s.get('launch'), 'Experiment requires task-owned launch records')
    desktop.load_launch(pathlib.Path(s['work']) / 'launch.json', s['thread_id'])
    desktop.require(not json.loads(pathlib.Path(s['registry']).read_text())['recording'], 'Recorder already running')
a.run = a.run.resolve()
desktop.require(not a.run.exists(), 'New capture directory required')
a.run.mkdir(parents=True)
source = (ROOT / 'scripts/native.swift').read_text().split('@main struct Main')[0]
source = source.replace('"event":"first_frame",', '"event":"first_frame","output":writer.outputURL.path,')
source += pathlib.Path(__file__).with_suffix('.swift').read_text()
build = ROOT / '.build'
build.mkdir(exist_ok=True)
digest = hashlib.sha256(source.encode() + (ROOT / 'scripts/capture_guard.swift').read_bytes()).hexdigest()[:16]
src = build / ('multi-' + digest + '.swift')
binary = build / ('multi-recorder-' + digest)
src.write_text(source)
if not binary.exists():
    subprocess.run(['swiftc', '-parse-as-library', '-import-objc-header', str(ROOT / 'scripts/native-process.h'),
                    str(ROOT / 'scripts/capture_guard.swift'), str(src), '-o', str(binary)], check=True)
targets = []
for s in sessions:
    label = pathlib.Path(s['work']).name
    targets.append(dict(label=label, pid=s['pid'], window=s['window'], executable=s['executable'],
                        output=str(a.run / (label + '.mp4'))))
stop = a.run / 'stop'
request = a.run / 'request.json'
for t in targets:
    desktop.dump(a.run / ('desired-' + t['label'] + '.json'), dict(generation=0, active=True))
desktop.dump(request, dict(targets=targets, stop=str(stop), seconds=a.seconds, control=str(a.run)))
logfile = a.run / 'capture.jsonl'
with logfile.open('wb', buffering=0) as log:
    proc = subprocess.Popen([str(binary), str(request)], stdout=log, stderr=log)
record = dict(pid=proc.pid, identity=desktop.identity(proc.pid), stop=str(stop), log=str(logfile),
              output=str(a.run), batch_targets=targets, experimental_broker=True)
for path, s in zip(a.session, sessions):
    s['recording'] = record
    desktop.dump(s['registry'], dict(recording=record))
    desktop.dump(path, s)
for _ in range(150):
    rows = [json.loads(line) for line in logfile.read_text().splitlines() if line.startswith('{')]
    if len({r.get('output') for r in rows if r.get('event') == 'first_frame'}) == len(targets):
        print(json.dumps(dict(all_first_frames=True, recording=record)), flush=True)
        break
    if proc.poll() is not None:
        raise RuntimeError(logfile.read_text())
    time.sleep(.1)
else:
    stop.touch()
    raise RuntimeError('Readiness timeout; keep lease and collect recorder before continuing')
code = proc.wait()
desktop.require(code == 0 and '"event":"capture_finished"' in logfile.read_text(), logfile.read_text())
print(json.dumps(dict(finished=True, run=str(a.run))), flush=True)
