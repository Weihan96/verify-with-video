"""Disposable Blender UI input probe. Run with --enable-event-simulate.

Commands are JSON files in a private run directory, consumed on Blender's main
thread. UI actions use window events; direct assignments only prepare fixtures.
Not a production remote-control server. The shared desktop lease is still held.
"""
import bpy
import blf
import json
import os
import pathlib
import sys
import time

args = sys.argv[sys.argv.index('--') + 1:]
run = pathlib.Path(args[args.index('--probe-dir') + 1]).resolve()
label = args[args.index('--probe-label') + 1]
run.mkdir(parents=True, exist_ok=True)
pending = []
cursor = [100, 100]
sequence = 0
last_state = None


def write(name, data):
    tmp = run / (name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    tmp.replace(run / name)


def log(data):
    with (run / 'events.jsonl').open('a') as f:
        f.write(json.dumps(dict(time=time.time(), pid=os.getpid(), **data)) + '\n')


class ProbeProperties(bpy.types.PropertyGroup):
    text: bpy.props.StringProperty(name='Text', default='ready')
    value: bpy.props.FloatProperty(name='Value', default=1.0)
    enabled: bpy.props.BoolProperty(name='Enabled', default=False)
    clicks: bpy.props.IntProperty(default=0)


class PROBE_OT_increment(bpy.types.Operator):
    bl_idname = 'probe.increment'
    bl_label = 'Increment'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.input_probe.clicks += 1
        log({'event': 'button_executed', 'clicks': context.scene.input_probe.clicks})
        return {'FINISHED'}


class PROBE_OT_popup(bpy.types.Operator):
    bl_idname = 'probe.popup'
    bl_label = 'Probe Popup'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=260)

    def draw(self, context):
        self.layout.label(text='Popup in instance ' + label)
        self.layout.prop(context.scene.input_probe, 'text')

    def execute(self, context):
        log({'event': 'popup_confirmed'})
        return {'FINISHED'}


class PROBE_PT_panel(bpy.types.Panel):
    bl_label = 'Input isolation ' + label
    bl_idname = 'PROBE_PT_input'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Item'
    bl_order = -1000

    def draw(self, context):
        p = context.scene.input_probe
        self.layout.label(text='Instance ' + label + ' | PID ' + str(os.getpid()))
        self.layout.prop(p, 'text')
        self.layout.prop(p, 'value')
        self.layout.prop(p, 'enabled')
        self.layout.operator('probe.increment', text='Increment: ' + str(p.clicks))
        self.layout.operator('probe.popup')


for cls in [ProbeProperties, PROBE_OT_increment, PROBE_OT_popup, PROBE_PT_panel]:
    bpy.utils.register_class(cls)
bpy.types.Scene.input_probe = bpy.props.PointerProperty(type=ProbeProperties)
bpy.context.scene.name = 'Input probe ' + label
bpy.context.scene.input_probe.text = 'ready-' + label


# Release candidate imported directly; fixture UI is test preparation only.
import importlib.util
candidate = pathlib.Path(__file__).resolve().parents[2] / 'scripts/blender_cursor.py'
spec = importlib.util.spec_from_file_location('release_cursor', candidate)
marker_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(marker_module)
marker = marker_module.enable(bpy.context.window, label)


def state():
    p = bpy.context.scene.input_probe
    return dict(pid=os.getpid(), label=label, text=p.text, value=p.value,
                enabled=p.enabled, clicks=p.clicks, filepath=bpy.data.filepath,
                windows=[dict(pointer=str(w.as_pointer()), width=w.width, height=w.height,
                              areas=[dict(type=a.type, x=a.x, y=a.y, width=a.width, height=a.height,
                                          perspective=a.spaces.active.region_3d.view_perspective
                                          if a.type == 'VIEW_3D' else None,
                                          regions=[dict(type=r.type, x=r.x, y=r.y, width=r.width, height=r.height)
                                                   for r in a.regions]) for a in w.screen.areas])
                         for w in bpy.context.window_manager.windows])


def tick():
    global sequence, last_state, marker
    try:
        for path in sorted(run.glob('command-*.json')):
            cmd = json.loads(path.read_text())
            path.rename(path.with_suffix('.accepted'))
            start = max(time.time(), cmd.get('start_at', 0))
            for event in cmd['events']:
                start += event.get('delay', 0.12)
                pending.append((start, cmd['id'], event))
        control = run / 'marker-control.json'
        if control.exists():
            action = json.loads(control.read_text())['action']
            control.unlink()
            w = bpy.context.window_manager.windows[0]
            if action == 'debug-on':
                bpy.app.debug = True
            elif action == 'debug-off':
                bpy.app.debug = False
            elif action == 'replace':
                old = marker
                marker = marker_module.enable(w, label)
                assert old.closed
                marker.update(w, *cursor)
            elif action == 'hide':
                marker.hide()
            elif action == 'stop':
                marker.stop()
                marker.stop()
            elif action == 'enable':
                marker = marker_module.enable(w, label)
                marker.update(w, *cursor)
            elif action == 'load-check':
                assert marker.closed, 'Load failed to close old marker'
                marker = marker_module.enable(w, label)
                marker.update(w, *cursor)
            elif action == 'wrong-window':
                class Wrong:
                    def as_pointer(self): return -1
                try:
                    marker.update(Wrong(), 100, 100)
                    raise AssertionError('Accepted wrong window')
                except ValueError:
                    pass
            else:
                raise ValueError(action)
            log({'event': 'marker_check', 'action': action, 'closed': marker.closed,
                 'handles': len(marker._handles), 'position': marker.position})
        now = time.time()
        while pending and pending[0][0] <= now:
            _, command_id, spec = pending.pop(0)
            w = next(w for w in bpy.context.window_manager.windows
                     if str(w.as_pointer()) == spec['window'])
            kwargs = {k: v for k, v in spec.items() if k not in ('delay', 'window')}
            kwargs.setdefault('x', cursor[0])
            kwargs.setdefault('y', cursor[1])
            w.event_simulate(**kwargs)
            cursor[:] = [kwargs['x'], kwargs['y']]
            if not marker.closed:
                marker.update(w, *cursor)
            sequence += 1
            log({'event': 'injected', 'command_id': command_id, 'sequence': sequence, 'input': kwargs})
            for area in w.screen.areas:
                area.tag_redraw()
        current = state()
        if current != last_state:
            log({'event': 'state_changed', 'state': current})
            last_state = current
        write('state.json', dict(time=time.time(), sequence=sequence, pending=len(pending), **current))
    except Exception as e:
        log({'event': 'error', 'error': repr(e)})
        pending.clear()
    return 0.03


def prepare():
    for w in bpy.context.window_manager.windows:
        for area in w.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'PERSP'
                area.spaces.active.show_region_ui = True
                for region in area.regions:
                    if region.type == 'UI':
                        try:
                            region.active_panel_category = 'Item'
                        except Exception:
                            pass
    # Fixture saving is preparation, not claimed as an input/save test.
    bpy.ops.wm.save_as_mainfile(filepath=str(run / ('fixture-' + label + '.blend')))
    log({'event': 'prepared', 'state': state(), 'blender': bpy.app.version_string})
    bpy.app.timers.register(tick, persistent=True)
    return None


bpy.app.timers.register(prepare, first_interval=2.0)
