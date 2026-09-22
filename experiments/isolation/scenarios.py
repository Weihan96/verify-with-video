"""Finite scenarios for the visually located 640x708 probe fixture on Retina.

Coordinates must be remeasured for a different window/layout/DPI. This is an
experiment, not a general coordinate-finding or unattended acceptance tool.
"""
import json
import pathlib
import subprocess
import sys
import time

POINTS = dict(text=(375, 176), value=(360, 201), enabled=(250, 227),
              increment=(357, 252), popup=(360, 278))
IMAGE_HEIGHT = 708


def move(x, y, delay=0.12):
    return dict(type='MOUSEMOVE', value='NOTHING', x=round(x * 2),
                y=round((IMAGE_HEIGHT - y) * 2), delay=delay)


def key(code, **modifiers):
    return [dict(type=code, value=v, delay=0.12, **modifiers) for v in ['PRESS', 'RELEASE']]


def click(name):
    return [move(*POINTS[name]), *key('LEFTMOUSE')]


def text(value):
    out = click('text') + key('A', ctrl=True)
    for char in value:
        out += [dict(type='A', value='PRESS', unicode=char, delay=0.15),
                dict(type='A', value='RELEASE', delay=0.04)]
    return out + key('RET')


def drag():
    x, y = POINTS['value']
    return [move(x, y), *key('LEFTMOUSE')[:1],
            *[move(x + n * 2, y, 0.2) for n in range(1, 35)],
            *key('LEFTMOUSE')[1:]]


def send(run, lease, events, start):
    subprocess.run([sys.executable, str(pathlib.Path(__file__).with_name('send.py')),
                    str(run), '--lease-id', lease, '--start-at', str(start),
                    '--events', json.dumps(events)], check=True)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('evidence', type=pathlib.Path)
    p.add_argument('--lease-id', required=True)
    p.add_argument('--round', type=int, choices=[1, 2, 3], required=True)
    p.add_argument('--fullscreen', action='store_true', help='Visually verified 1280x803 fixture geometry')
    a = p.parse_args()
    if a.fullscreen:
        IMAGE_HEIGHT = 803
        POINTS = {name: (x + 510, y - 28) for name, (x, y) in POINTS.items()}
    start = time.time() + 2
    if a.round == 1:
        plans = {'A': drag() + click('increment') + click('enabled'),
                 'B': text('bravo-one') + click('increment') + click('enabled')}
    elif a.round == 2:
        plans = {'A': text('alpha-two') + click('increment') + click('enabled'),
                 'B': drag() + click('increment') + click('enabled')}
    else:
        plans = {label: text(label.lower() + '-plain') + click('popup') for label in ['A', 'B']}
    for label, events in plans.items():
        send(a.evidence / label, a.lease_id, events, start)
    time.sleep(2 + max(sum(x.get('delay', .12) for x in events) for events in plans.values()) + 2)
    for label in plans:
        s = json.loads((a.evidence / label / 'state.json').read_text())
        print(label, json.dumps({k: s[k] for k in ['text', 'value', 'enabled', 'clicks', 'pending', 'sequence']}))
