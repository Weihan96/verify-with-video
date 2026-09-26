#!/usr/bin/env python3
"""Single-task entry to the same scoped Blender input and capture lifecycle."""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments/cross_task'))
import access


def call(script, *args, capture=True):
    command = [sys.executable, str(ROOT / script), *map(str, args)]
    if not capture:
        subprocess.run(command, check=True)
        return None
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def context(run):
    receipt = json.loads((run / 'background.json').read_text())
    group = pathlib.Path(receipt['group'])
    g = access.read(group)
    access.require(g.get('mode') == 'solo' and g['coordinator'] == access.own(),
                   'Single-task session belongs to another task or mode')
    access.require(pathlib.Path(g['run']).resolve() == run, 'Run binding changed')
    access.validate_members(g)
    return group, g, run / 'A/participant.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'admit', 'serve', 'start', 'send', 'stop', 'collect', 'close', 'status'])
    parser.add_argument('--run', type=pathlib.Path, required=True)
    parser.add_argument('--lease')
    scene = parser.add_mutually_exclusive_group()
    scene.add_argument('--blend', type=pathlib.Path)
    scene.add_argument('--fixture', action='store_true')
    parser.add_argument('--blender', type=pathlib.Path)
    parser.add_argument('--seconds', type=float, default=1200)
    parser.add_argument('--events', help='JSON array of supported Window.event_simulate events')
    args = parser.parse_args()
    run = args.run.resolve()
    if args.command == 'prepare':
        access.require(args.lease, 'Preparation requires the current desktop lease')
        if args.blend:access.require(args.blend.is_file(), 'Blend workfile missing')
        if args.blender:access.require(args.blender.is_file(), 'Blender executable missing')
        created = call('experiments/cross_task/group.py', 'create', '--solo', '--lease', args.lease, '--run', run)
        access.queue.atomic_json(run / 'background.json', created)
        group = created['group']
        call('experiments/cross_task/group.py', 'grant', '--group', group, '--label', 'A')
        options = []
        if args.blend:options += ['--blend', args.blend.resolve()]
        if args.fixture:options += ['--fixture']
        if args.blender:options += ['--blender', args.blender.resolve()]
        call('experiments/cross_task/prepare.py', group, *options, capture=False)
        return dict(**created, screenshot=str(run / 'A/prepared.png'),
                    next='Inspect screenshot, file, Perspective and coordinates; then admit. Keep preparation lease until admitted or cleaned up.')
    group, g, participant = context(run)
    if args.command == 'status':return g
    if args.command == 'admit':
        # A retry after admission can complete an interrupted queue handoff.
        if g['phase'] == 'preparing':
            if g['members']['A']['state'] != 'ready':
                call('experiments/cross_task/group.py', 'ready', '--group', group)
            call('experiments/cross_task/group.py', 'formal', '--group', group)
        else:access.coordinator(g)
        handoff = access.queue.execute(access.shared(), 'release', access.own(), g['reservation'])
        return dict(admitted=True, group=str(group), handoff=handoff,
                    next='Deliver any handoff.notify, then serve in a retained execution session. No foreground lease needed for this background group.')
    if args.command == 'serve':
        call('experiments/cross_task/broker.py', '--group', group, '--seconds', args.seconds, capture=False)
        return dict(finished=True)
    if args.command in ('start', 'stop', 'collect'):
        return call('experiments/cross_task/control.py', participant, args.command)
    if args.command == 'send':
        access.require(args.events, '--events required')
        return call('experiments/cross_task/send.py', participant, '--events', args.events)
    if args.command == 'close':
        if g['phase'] == 'closed':return dict(closed=True, already_closed=True)
        # Does not discard an active recording. The caller must stop/collect it first.
        if g['members']['A']['state'] != 'closed':
            session = run / 'A/session.json'
            if session.exists() and not json.loads(session.read_text()).get('closed'):
                call('scripts/desktop.py', 'close', '--isolation-group', group, '--session', session)
            elif not session.exists() and (run / 'A/launch.json').exists():
                p = json.loads(participant.read_text())
                call('scripts/desktop.py', 'close', '--isolation-group', group,
                     '--lease-id', p['token'], '--launch-record', run / 'A/launch.json', '--work', run / 'A')
            call('experiments/cross_task/group.py', 'closed', '--group', group)
        if (run / 'capture/broker.json').exists():
            call('experiments/cross_task/shutdown.py', group)
        call('experiments/cross_task/group.py', 'finish', '--group', group)
        return dict(closed=True, capture_outcome=access.read(group).get('capture_outcome','not_started'),
                    preparation_lease_retained=g['phase']=='preparing')


if __name__ == '__main__':
    try:
        print(json.dumps(main(), ensure_ascii=False, indent=2), flush=True)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        detail = (error.stderr or error.stdout) if isinstance(error, subprocess.CalledProcessError) else str(error)
        print(json.dumps(dict(error=detail, action='Inspect retained run and receipts; do not retry input blindly')), file=sys.stderr)
        sys.exit(1)
