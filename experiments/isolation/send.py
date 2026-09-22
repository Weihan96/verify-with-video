"""Send a finite input batch to one task-owned experimental Blender bridge."""
import argparse
import json
import os
import pathlib
import sys
import time
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts'))
import desktop

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('run', type=pathlib.Path)
p.add_argument('--events', required=True, help='JSON array of Window.event_simulate arguments')
p.add_argument('--start-at', type=float, default=0)
p.add_argument('--lease-id', required=True)
a = p.parse_args()
owner = desktop.check(a.lease_id)
record = desktop.load_launch(a.run / 'launch.json', owner)
session_path = a.run / 'session.json'
if session_path.exists():
    session = desktop.load_session(session_path)
    registry = json.loads(pathlib.Path(session['registry']).read_text())
    desktop.recording_health(registry['recording'])
    recording = registry['recording']
    if recording and recording.get('experimental_broker'):
        desktop.require(desktop.identity(recording['pid']) == recording['identity'], 'Broker identity changed')
        rows = [json.loads(line) for line in pathlib.Path(recording['log']).read_text().splitlines() if line.startswith('{')]
        label = pathlib.Path(session['work']).name
        lifecycle = [row for row in rows if row.get('label') == label and row.get('event') in
                     ('capture_started', 'target_stopped', 'target_failed', 'target_finalize_failed')]
        desktop.require(lifecycle and lifecycle[-1]['event'] == 'capture_started', 'Target recorder is not active')
        desktop.require(any(row.get('event') == 'first_frame' and row.get('output') == lifecycle[-1]['output'] for row in rows),
                        'Target recorder has no first frame')
state = json.loads((a.run / 'state.json').read_text())
desktop.require(state['pid'] == record['pid'], 'Bridge PID does not match launch')
desktop.require(time.time() - state['time'] < 3, 'Bridge heartbeat stale')
events = json.loads(a.events)
desktop.require(isinstance(events, list) and 0 < len(events) <= 1000, 'Finite batch required')
window = state['windows'][0]['pointer']
for event in events:
    desktop.require(isinstance(event, dict) and event.get('type') and event.get('value'), 'Input event required')
    desktop.require(0 <= event.get('delay', .12) <= 10, 'Event delay must be between 0 and 10 seconds')
    event.setdefault('window', window)
    desktop.require(event['window'] in [w['pointer'] for w in state['windows']], 'Unknown window')
desktop.require(sum(e.get('delay', .12) for e in events) <= 120, 'Batch must finish within two minutes')
command_id = str(uuid.uuid4())
out = a.run / ('command-' + str(time.time_ns()) + '-' + command_id + '.json')
desktop.dump(out, dict(id=command_id, thread_id=os.environ['CODEX_THREAD_ID'],
                      start_at=a.start_at, events=events))
print(json.dumps(dict(command_id=command_id, file=str(out), event_count=len(events))))
